# Interview-System-Backend\interview_platform\config\settings.py
from pathlib import Path
import environ
from datetime import timedelta

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "AUTH_HEADER_TYPES": ("Bearer",),
    "AUTH_TOKEN_CLASSES": ("rest_framework_simplejwt.tokens.AccessToken",),
    "TOKEN_TYPE_CLAIM": "token_type",
    "BLACKLIST_AFTER_ROTATION": True,
}
BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY")

DEBUG = env.bool("DEBUG", default=False)

AUTH_USER_MODEL = "accounts.User"

# Use environment variable with fallback for development
FRONTEND_URL = env("FRONTEND_URL")

ALLOWED_HOSTS = ["*"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("DB_NAME"),
        "USER": env("DB_USER"),
        "PASSWORD": env("DB_PASSWORD"),
        "HOST": env("DB_HOST"),
        "PORT": env("DB_PORT"),
    }
}

ROOT_URLCONF = "config.urls"

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "apps.accounts.middleware_debug.AllauthDebugMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    #'django.middleware.csrf.CsrfViewMiddleware',
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "apps.accounts.middleware.RoleRequiredMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

INSTALLED_APPS = [
    "daphne",
    "corsheaders",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    # third-party
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "allauth.socialaccount.providers.linkedin_oauth2",
    # third-party API
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "drf_yasg",
    # local apps
    #'apps.accounts',
    "apps.profiles",
    "apps.interviews",
    "apps.notifications",
    "apps.credits",
    "apps.accounts.apps.AccountsConfig",
    # Django Channels for WebSocket support
    "channels",
]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
        #'rest_framework.authentication.BasicAuthentication',
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    # Global Pagination Configuration
    # Uses custom LimitOffsetPagination with ?limit= and ?offset= query params
    # - Default limit: 10 items per request
    # - Maximum limit: 100 items (prevents abuse)
    # - Response format: {count, next, previous, results}
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 9,
    "EXCEPTION_HANDLER": "apps.common.utils.custom_exception_handler",
    # JSON-only renderer
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        #'rest_framework.renderers.BrowsableAPIRenderer',
    ],
}

# Swagger/OpenAPI Settings - Enable JWT authentication in Swagger UI
# CRITICAL FIX: Corrected configuration for proper JWT Bearer token support
SWAGGER_SETTINGS = {
    "SECURITY_DEFINITIONS": {
        "Bearer": {
            "type": "apiKey",
            "name": "Authorization",
            "in": "header",
            "description": (
                "JWT Authorization header using the Bearer scheme.\n\n"
                '**IMPORTANT: You MUST include the word "Bearer" followed by a space!**\n\n'
                "**How to use:**\n"
                "1. Login via `/api/auth/login/` to get your access token\n"
                '2. Click the "Authorize" button (lock icon) at the top right\n'
                "3. In the value field, enter EXACTLY: `Bearer <your_access_token>`\n"
                '   - Include the word "Bearer" (capital B)\n'
                "   - Followed by a single space\n"
                "   - Then paste your access_token\n"
                '4. Click "Authorize" and then "Close"\n\n'
                "**Example:** `Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoiYWNjZXNzIi...`\n\n"
                "**Common Mistakes:**\n"
                '- ❌ Wrong: `eyJhbGciOiJIUzI1...` (missing "Bearer " prefix)\n'
                '- ❌ Wrong: `bearer eyJhbGci...` (lowercase "bearer")\n'
                "- ✅ Correct: `Bearer eyJhbGciOiJIUzI1...`"
            ),
        },
    },
    # Apply Bearer security to all endpoints by default
    "SECURITY_REQUIREMENTS": [{"Bearer": []}],
    # Removed USE_SESSION_AUTH to hide Django login/logout buttons in Swagger UI
    # JWT Bearer authentication via Authorize button is the only method users should use
    # UI Settings
    "JSON_EDITOR": True,
    "PERSIST_AUTH": True,  # Persist authorization across page refreshes
    "REFETCH_SCHEMA_WITH_AUTH": True,  # Refetch schema after auth to show protected endpoints
    "REFETCH_SCHEMA_ON_LOGOUT": True,  # Refetch on logout
    # DOC_EXPANSION controls the default state of operations
    "DOC_EXPANSION": "none",  # none, list, full
    # Operations sorter
    "OPERATIONS_SORTER": "alpha",
    "TAGS_SORTER": "alpha",
    # Validator
    "VALIDATOR_URL": None,  # Disable external validator
    # Deep linking
    "DEEP_LINKING": True,
}

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
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

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

SITE_ID = 2  # localhost:8000

AUTHENTICATION_BACKENDS = (
    "apps.accounts.backends.EmailBackend",
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
)

ACCOUNT_ALLOW_REGISTRATION = True

# Custom adapters for redirect handling
ACCOUNT_ADAPTER = "apps.accounts.adapters.CustomAccountAdapter"
SOCIALACCOUNT_ADAPTER = "apps.accounts.adapters.CustomSocialAccountAdapter"

# Custom signup form
ACCOUNT_FORMS = {
    "signup": "apps.accounts.forms.CustomSignupForm",
}

SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_LOGIN_ON_GET = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True

ACCOUNT_EMAIL_VERIFICATION = "mandatory"
# Add this to skip verification for social accounts
SOCIALACCOUNT_EMAIL_VERIFICATION = "none"  # ✅ Trust OAuth providers
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = False
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_AUTHENTICATION_METHOD = "email"
ACCOUNT_CONFIRM_EMAIL_ON_GET = False
LOGIN_ON_EMAIL_CONFIRMATION = False
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["username", "email*", "password1*"]
ACCOUNT_USER_MODEL_USERNAME_FIELD = "username"

LOGIN_REDIRECT_URL = "/api/auth/oauth-success/"
LOGOUT_REDIRECT_URL = "/login"

SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "SCOPE": [
            "profile",
            "email",
        ],
        "AUTH_PARAMS": {
            "access_type": "online",
            "prompt": "select_account",
        },
    },
    "linkedin_oauth2": {
        "SCOPE": [
            "openid",
            "profile",
            "email",
        ],
        "AUTH_PARAMS": {
            "prompt": "login",  # Force LinkedIn to always show login screen
            "approval_prompt": "force",  # Force approval screen (legacy parameter)
        },
        "PROFILE_FIELDS": [
            "id",
            "first-name",
            "last-name",
            "email-address",
            "picture-url",
            "public-profile-url",
        ],
    },
}

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Security Settings
SESSION_COOKIE_SECURE = not DEBUG  # Use secure cookies in production
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_SAVE_EVERY_REQUEST = True
# Session timeout (30 minutes)
SESSION_COOKIE_AGE = 1800
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

# Logging configuration - Enhanced for observability
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
        "structured": {
            # Structured format for parsing (timestamp, level, logger, message)
            "format": "{asctime} | {levelname:8} | {name} | {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "structured_console": {
            "class": "logging.StreamHandler",
            "formatter": "structured",
        },
    },
    "loggers": {
        "": {  # Root logger - catches everything
            "handlers": ["console"],
            "level": "INFO",
        },
        # === Interview System Loggers (Structured) ===
        "apps.interviews": {
            "handlers": ["structured_console"],
            "level": "INFO",
            "propagate": False,
        },
        "apps.interviews.tasks": {
            "handlers": ["structured_console"],
            "level": "INFO",
            "propagate": False,
        },
        "apps.interviews.finalize": {
            "handlers": ["structured_console"],
            "level": "INFO",
            "propagate": False,
        },
        "apps.interviews.livekit": {
            "handlers": ["structured_console"],
            "level": "INFO",
            "propagate": False,
        },
        # === Credits System Logger ===
        "apps.credits": {
            "handlers": ["structured_console"],
            "level": "INFO",
            "propagate": False,
        },
        # === Account and Auth Loggers ===
        "apps.accounts": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
        "allauth": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
        "allauth.socialaccount": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
        "allauth.socialaccount.providers.linkedin_oauth2": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
        "django.request": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
    },
}
ACCOUNT_CONFIRM_EMAIL_ON_GET = True
ACCOUNT_EMAIL_CONFIRMATION_ANONYMOUS_REDIRECT_URL = "/api/email-verified/"
ACCOUNT_EMAIL_CONFIRMATION_AUTHENTICATED_REDIRECT_URL = "/api/email-verified/"

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"

EMAIL_HOST = "smtp.gmail.com"
EMAIL_PORT = 587
EMAIL_USE_TLS = True

EMAIL_HOST_USER = env("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD")

DEFAULT_FROM_EMAIL = "Interview Platform <rockyvasee@gmail.com>"
CORS_ALLOWED_ORIGINS = [
    "*",
]
CORS_ALLOW_CREDENTIALS = True

CSRF_TRUSTED_ORIGINS = [
    "*",
]

LIVEKIT_API_KEY = env("LIVEKIT_API_KEY", default="")
LIVEKIT_API_SECRET = env("LIVEKIT_API_SECRET", default="")
LIVEKIT_URL = env("LIVEKIT_URL", default="wss://your-livekit-server.com")

# ========== DJANGO CHANNELS CONFIGURATION ==========
# ASGI application for WebSocket support
ASGI_APPLICATION = "config.asgi.application"

# Channel layer configuration
# For production, use Redis:
# CHANNEL_LAYERS = {
#     "default": {
#         "BACKEND": "channels_redis.core.RedisChannelLayer",
#         "CONFIG": {
#             "hosts": [env('REDIS_URL', default='redis://localhost:6379/0')],
#         },
#     },
# }

# For development (in-memory layer):
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

# Celery Beat Periodic Tasks Schedule
CELERY_BEAT_SCHEDULE = {
    # Main task: Finalize accepted interviews that have expired (20-min rule)
    "finalize-expired-interviews-every-5-min": {
        "task": "apps.interviews.tasks.finalize_expired_interviews",
        "schedule": 300.0,  # every 5 minutes
    },
    # Secondary task: Clean up pending interviews that were never accepted
    "cleanup-expired-pending-every-30-min": {
        "task": "apps.interviews.tasks.cleanup_expired_pending_interviews",
        "schedule": 1800.0,  # every 30 minutes
    },
}
