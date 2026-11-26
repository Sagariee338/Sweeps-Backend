"""Run API tests without allowing outbound vendor HTTP requests.

Database and Redis connections remain real. Vendor contract tests must inject
httpx.MockTransport; a forgotten real transport fails before contacting a host.
"""

from unittest.mock import patch

from django.test.runner import DiscoverRunner


class OfflineDiscoverRunner(DiscoverRunner):
    def run_tests(self, test_labels, **kwargs):
        blocked = AssertionError(
            "Outbound HTTP is forbidden in automated tests; inject MockTransport"
        )
        with (
            patch("httpx.HTTPTransport.handle_request", side_effect=blocked),
            patch("httpx.AsyncHTTPTransport.handle_async_request", side_effect=blocked),
        ):
            return super().run_tests(test_labels, **kwargs)
