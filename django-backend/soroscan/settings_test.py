"""
Test settings for SoroScan project.
"""
from datetime import timedelta
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = "django-insecure-test-key-for-testing-only"

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

ALLOWED_HOSTS = ["*"]
FRONTEND_BASE_URL = "http://localhost:3000"
SOFTWARE_VERSION = "1.0.0-test"

# Application definition
INSTALLED_APPS = [
    "django_prometheus",  # must be before django.contrib apps
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "corsheaders",
    "django_filters",
    "channels",
    # Local apps
    "soroscan.ingest",
]

MIDDLEWARE = [
    "django_prometheus.middleware.PrometheusBeforeMiddleware",
    "soroscan.middleware.GracefulShutdownMiddleware",
    "soroscan.middleware.RequestBodySizeMiddleware",
    "soroscan.middleware.MaintenanceModeMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "soroscan.cors_middleware.OrgCorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "soroscan.middleware.RequestIdMiddleware",
    "soroscan.middleware.PlatformVersionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "soroscan.middleware_gzip.CustomGZipMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "soroscan.middleware.ApiDeprecationMiddleware",
    "django_prometheus.middleware.PrometheusAfterMiddleware",
]

ROOT_URLCONF = "soroscan.urls_test"  # safe mirror — excludes strawberry/GDAL import

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "soroscan.wsgi.application"
ASGI_APPLICATION = "soroscan.asgi.application"

# Channels configuration for testing
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    },
}

# Database - use in-memory SQLite for tests
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# PostgreSQL statement timeout in milliseconds (issue #1007).
DATABASE_STATEMENT_TIMEOUT = 5000

# Password validation
AUTH_PASSWORD_VALIDATORS = []

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# In-memory cache for tests (query result caching — issue #131)
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "soroscan-test",
    }
}
QUERY_CACHE_TTL_SECONDS = 60
PACT_PROVIDER_STATES_ENABLED = True

# REST Framework
REST_FRAMEWORK = {
    "EXCEPTION_HANDLER": "soroscan.exceptions.custom_exception_handler",
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticatedOrReadOnly",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "1000/hour",
        "user": "10000/hour",
        "ingest": "100/hour",
        "graphql": "500/hour",
        "webhook_replay": "1000/hour",
        "contract_bulk_import": "1000/hour",
        "dedup_test": "1000/hour",
        "events_search": "1000/hour",
        "contract_stats": "1000/hour",
        "db_explain": "1000/hour",
        "unauthenticated_ip": "30/minute",
    },
}



SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# CORS
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOWED_ORIGINS = []

# Celery - Test settings (synchronous execution)
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
SHUTDOWN_TIMEOUT_SECONDS = 30
CELERY_WORKER_SOFT_SHUTDOWN_TIMEOUT = 30
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TIME_LIMIT = 600
CELERY_TASK_SOFT_TIME_LIMIT = 540
CELERY_BEAT_SCHEDULE = {}  # Disabled in tests — tasks run eagerly
REDIS_URL = "redis://localhost:6379/0"

# Stellar / Soroban Configuration
SOROBAN_RPC_URL = "https://soroban-testnet.stellar.org"
STELLAR_NETWORK_PASSPHRASE = "Test SDF Network ; September 2015"
SOROSCAN_CONTRACT_ID = "C" + "A" * 55
INDEXER_SECRET_KEY = ""

# Event Streaming Configuration (Disabled by default for tests)
EVENT_STREAMING = {
    "enabled": False,
    "backend": "kafka",
    "kafka": {
        "bootstrap_servers": ["localhost:9092"],
        "topic": "soroscan.events",
        "schema_registry_url": "",
    },
    "pubsub": {
        "project_id": "test-project",
        "topic": "soroscan.events",
    },
    "sqs": {
        "queue_url": "",
    },
}

# GraphQL Introspection — enabled in tests/dev
GRAPHQL_INTROSPECTION_ENABLED = True
GRAPHQL_MAX_COMPLEXITY = 1000
GRAPHQL_N1_DETECTION_ENABLED = False

# Fixed test seed for deterministic webhook signature tests.
WEBHOOK_ED25519_SIGNING_SEED = (
    "0000000000000000000000000000000000000000000000000000000000000001"
)

# Logging
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
    "loggers": {
        "soroscan.migrate": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": True,
        },
    },
}

MAX_REQUEST_BODY_SIZE = 10485760
DEPRECATED_ENDPOINTS = {}

# Issue #765 — webhook delivery log retention
WEBHOOK_DELIVERY_RETENTION_DAYS = 30
WEBHOOK_ESCALATION_TIMEOUT_SECONDS = 10
WEBHOOK_ESCALATION_DEDUP_SECONDS = 300
WEBHOOK_ESCALATION_SLACK_TARGET = ""

# Issue #778 — cache TTL for contract name warmer
CACHE_TTL_SECONDS = 300

# Issue #798 — contract state snapshot settings
CONTRACT_SNAPSHOT_INTERVAL = 1000
CONTRACT_SNAPSHOT_MAX_BYTES = 1_048_576

# Misc defaults needed by code under test
DEDUP_LOG_RETENTION_DAYS = 90
EVENT_RETENTION_DAYS = 30
ALERT_DEDUP_WINDOW_SECONDS = 300
WEBHOOK_MAX_RETRIES = 5
INDEXER_SECRET_KEY = ""
SENTRY_DSN = ""
LOG_FORMAT = ""
