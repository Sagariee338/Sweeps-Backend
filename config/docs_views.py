"""Development-only OpenAPI and Swagger endpoints."""
from django.conf import settings
from django.http import Http404
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView


class DebugDocsMixin:
    def dispatch(self, request, *args, **kwargs):
        if not settings.DEBUG:
            raise Http404
        return super().dispatch(request, *args, **kwargs)


class LocalSchemaView(DebugDocsMixin, SpectacularAPIView):
    pass


class LocalSwaggerView(DebugDocsMixin, SpectacularSwaggerView):
    pass
