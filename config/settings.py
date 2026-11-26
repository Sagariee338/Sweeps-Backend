"""LavishSweeps API settings. PostgreSQL is the only database."""
from pathlib import Path
from urllib.parse import urlparse
import os

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "unsafe-development-only-key-change-before-deploy")
DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"
DEMO_MODE = DEBUG and os.environ.get("DEMO_MODE", "0") == "1"
DOLLARPAY_DEV_MODE = os.environ.get("DOLLARPAY_DEV_MODE", "0") == "1"
PROVIDER_ACCOUNT_SETUP_ENABLED = os.environ.get("PROVIDER_ACCOUNT_SETUP_ENABLED", "0") == "1"
PROVIDER_VALUE_ACCOUNTS_ENABLED = os.environ.get("PROVIDER_VALUE_ACCOUNTS_ENABLED", "0") == "1"
PROVIDER_FREE_PLAY_ENABLED = os.environ.get("PROVIDER_FREE_PLAY_ENABLED", "0") == "1"
if not DEBUG and (SECRET_KEY.startswith(("unsafe-", "local-demo-")) or len(SECRET_KEY) < 50 or len(set(SECRET_KEY)) < 5):
    raise RuntimeError("DJANGO_SECRET_KEY must be set outside development")
ALLOWED_HOSTS = [x.strip() for x in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if x.strip()]

INSTALLED_APPS = [
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
    "corsheaders", "rest_framework", "drf_spectacular", "drf_spectacular_sidecar",
    "identity", "catalog", "wallet", "integrations", "provider_accounts", "demo", "ops", "support",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware", "config.middleware.ApiNoStoreMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware", "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware", "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware", "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
TEST_RUNNER = "config.test_runner.OfflineDiscoverRunner"
ROOT_URLCONF = "config.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates", "DIRS": [], "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.debug", "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth", "django.contrib.messages.context_processors.messages",
    ]},
}]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

db_url = os.environ.get("DATABASE_URL", "postgresql://lavish:lavish@localhost:5432/lavishsweeps")
parsed = urlparse(db_url)
if parsed.scheme not in {"postgres", "postgresql"}:
    raise RuntimeError("DATABASE_URL must be a PostgreSQL URL")
DATABASES = {"default": {
    "ENGINE": "django.db.backends.postgresql", "NAME": parsed.path.lstrip("/"),
    "USER": parsed.username or "", "PASSWORD": parsed.password or "",
    "HOST": parsed.hostname or "localhost", "PORT": parsed.port or 5432,
    "CONN_MAX_AGE": 60, "OPTIONS": {"sslmode": os.environ.get("DATABASE_SSLMODE", "prefer")},
}}

redis_url = os.environ.get("REDIS_URL", "")
if redis_url:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": redis_url}}
elif DEBUG:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
else:
    raise RuntimeError("REDIS_URL is required outside development for shared API throttling")

AUTH_USER_MODEL = "identity.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator", "OPTIONS": {"user_attributes": ("email", "display_name")}},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.AnonRateThrottle", "rest_framework.throttling.UserRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {
        "anon": os.environ.get("API_ANON_RATE", "600/hour"),
        "user": os.environ.get("API_USER_RATE", "1200/hour"),
        "auth": os.environ.get("API_AUTH_RATE", "10/minute"),
        "development_payments": "120/minute",
    },
}
SPECTACULAR_SETTINGS = {
    "TITLE": "LavishSweeps API",
    "DESCRIPTION": "Session-authenticated platform API. Local demo endpoints use fake credits and are available only in demo mode.",
    "VERSION": "1.0.0",
    "ENUM_NAME_OVERRIDES": {
        "ProviderPlayModeEnum": ["free_play", "value_play"],
        "ProviderLaunchModeEnum": ["free_play"],
    },
    "SERVE_INCLUDE_SCHEMA": False,
    "SWAGGER_UI_DIST": "SIDECAR",
    "SWAGGER_UI_FAVICON_HREF": "SIDECAR",
    "SWAGGER_UI_SETTINGS": {"persistAuthorization": False},
}
CORS_ALLOWED_ORIGINS = [x.strip() for x in os.environ.get("DJANGO_CORS_ORIGINS", "http://localhost:3000" if DEBUG else "").split(",") if x.strip()]
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = [x.strip() for x in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "http://localhost:3000" if DEBUG else "").split(",") if x.strip()]
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = not DEBUG
SECURE_REDIRECT_EXEMPT = [r"^health/$", r"^ready/$"]
if os.environ.get("DJANGO_TRUST_PROXY", "0") == "1":
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = False
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000").rstrip("/")
EMAIL_BACKEND = os.environ.get(
    "DJANGO_EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend" if DEBUG else "django.core.mail.backends.smtp.EmailBackend",
)
EMAIL_HOST = os.environ.get("DJANGO_EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.environ.get("DJANGO_EMAIL_PORT", "25"))
EMAIL_HOST_USER = os.environ.get("DJANGO_EMAIL_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("DJANGO_EMAIL_PASSWORD", "")
EMAIL_USE_TLS = os.environ.get("DJANGO_EMAIL_USE_TLS", "0") == "1"
DEFAULT_FROM_EMAIL = os.environ.get("DJANGO_FROM_EMAIL", "LavishSweeps <no-reply@localhost>")
PASSWORD_RESET_TIMEOUT = 86400
