"""API responses are private and fresh unless a future policy explicitly changes it."""
from django.utils.cache import patch_vary_headers


class ApiNoStoreMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith("/api/"):
            response["Cache-Control"] = "no-store"
            patch_vary_headers(response, ("Cookie",))
        return response
