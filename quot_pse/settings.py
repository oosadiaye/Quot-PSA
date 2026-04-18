"""
Quot PSE — Nigeria Government IFMIS
Settings for the quot_pse project.

A public sector SaaS ERP compliant with:
- Nigeria National Chart of Accounts (NCoA) — 52-digit, 6-segment
- IPSAS Accrual Accounting Standards
- Nigeria Governors Forum (NGF) requirements
- TSA (Treasury Single Account) architecture
- BPP Due Process procurement compliance
"""

import logging
import os
from pathlib import Path
from dotenv import load_dotenv
from django.core.exceptions import ImproperlyConfigured

# Load environment variables
load_dotenv()

# ─── Quot PSE Project Identity ─────────────────────────────────────────
PROJECT_NAME = "Quot PSE"
PROJECT_SUBTITLE = "Nigeria Government IFMIS"
PROJECT_VERSION = "1.0.0"
GOVERNMENT_MODE = True  # Disables all commercial features globally
DEFAULT_CURRENCY = "NGN"
DEFAULT_COUNTRY = "NG"

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    raise ImproperlyConfigured('SECRET_KEY environment variable is required')

DEBUG = os.getenv('DEBUG', 'False') == 'True'

ALLOWED_HOSTS_CONFIG = os.getenv('ALLOWED_HOSTS', '')
if ALLOWED_HOSTS_CONFIG:
    ALLOWED_HOSTS = [h.strip() for h in ALLOWED_HOSTS_CONFIG.split(',') if h.strip()]
elif DEBUG:
    # In development, allow all hosts so that django-tenants domain
    # rewriting (via TenantHeaderMiddleware) works correctly.
    # Tenant domains like *.dtsg.test would otherwise be rejected.
    ALLOWED_HOSTS = ['*']
else:
    raise ImproperlyConfigured(
        'ALLOWED_HOSTS must be configured for production. '
        'Set the ALLOWED_HOSTS environment variable with your domain names '
        '(comma-separated). Example: ALLOWED_HOSTS=erp.example.com,api.example.com'
    )

# Application definition

SHARED_APPS = [
    'django_tenants',  # mandatory
    'tenants',         # tenant models + UserTenantRole (public schema)

    'django.contrib.admin',
    'django.contrib.auth',          # users live in public schema (centralized)
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'rest_framework',
    'rest_framework.authtoken',     # tokens in public schema for centralized auth
    'drf_spectacular',               # P7-T1 — OpenAPI 3.1 schema
    'django_filters',
    'corsheaders',

    'core',
    'superadmin',
]

# Phase 2: Add django-celery-beat when installed (pip install django-celery-beat)
try:
    import django_celery_beat  # noqa: F401
    SHARED_APPS.insert(-2, 'django_celery_beat')  # Before 'core'
except ImportError:
    pass

TENANT_APPS = [
    'django.contrib.contenttypes',

    'core',
    'accounting',
    'budget',
    'procurement',
    'inventory',
    'workflow',
    'hrm',
    'simple_history',

    # Stub apps — deleted for public sector, kept for migration history only
    'sales',
    'production',
    # Note: django.contrib.auth and rest_framework.authtoken are in SHARED_APPS
    # only — users and tokens live in the public schema for centralized login.
    # User-to-tenant access is managed via tenants.UserTenantRole.
]

INSTALLED_APPS = list(dict.fromkeys(SHARED_APPS + TENANT_APPS))

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'core.middleware.TenantHeaderMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'core.middleware.LanguageDetectionMiddleware',  # IP-based language detection
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'core.middleware.TenantAccessMiddleware',  # validates user has access to tenant
    'core.middleware.OrganizationMiddleware',  # resolves active organization (MDA branch)
    'core.middleware.ForceDefaultLanguageMiddleware',  # force default for API endpoints
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'simple_history.middleware.HistoryRequestMiddleware',
    # P3-T1 — populates per-request logging context (tenant, user,
    # request_id, operation) read by the JSON formatter.
    'core.logging.RequestContextMiddleware',
]

ROOT_URLCONF = 'quot_pse.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'quot_pse.wsgi.application'

# Database
# https://docs.djangoproject.com/en/6.0/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django_tenants.postgresql_backend',
        'NAME': os.getenv('DB_NAME', 'quot_pse'),
        'USER': os.getenv('DB_USER', 'dtsg'),
        'PASSWORD': os.getenv('DB_PASSWORD', ''),
        'HOST': os.getenv('DB_HOST', 'localhost'),
        'PORT': os.getenv('DB_PORT', '5432'),
        'CONN_MAX_AGE': int(os.getenv('CONN_MAX_AGE', '60')),  # Phase 1: reduced from 600→60
        'CONN_HEALTH_CHECKS': True,  # Phase 1: verify connections before reuse
        'OPTIONS': {
            'connect_timeout': 10,
        },
    }
}

# Phase 3: Read replica for offloading reports, dashboards, list views
if os.getenv('DB_REPLICA_HOST'):
    DATABASES['replica'] = {
        'ENGINE': 'django_tenants.postgresql_backend',
        'NAME': os.getenv('DB_REPLICA_NAME', os.getenv('DB_NAME', 'quot_pse')),
        'USER': os.getenv('DB_REPLICA_USER', os.getenv('DB_USER', 'dtsg')),
        'PASSWORD': os.getenv('DB_REPLICA_PASSWORD', os.getenv('DB_PASSWORD', '')),
        'HOST': os.getenv('DB_REPLICA_HOST'),
        'PORT': os.getenv('DB_REPLICA_PORT', os.getenv('DB_PORT', '5432')),
        'CONN_MAX_AGE': int(os.getenv('CONN_MAX_AGE', '60')),
        'CONN_HEALTH_CHECKS': True,
        'OPTIONS': {
            'connect_timeout': 10,
        },
        'TEST': {
            'MIRROR': 'default',
        },
    }

DATABASE_ROUTERS = (
    'quot_pse.db_router.TenantAwareReadReplicaRouter',  # Phase 3: read replica routing
    'django_tenants.routers.TenantSyncRouter',
)

TENANT_MODEL = 'tenants.Client'
TENANT_DOMAIN_MODEL = 'tenants.Domain'

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Supported languages for i18n
LANGUAGES = [
    ('en', 'English'),
    ('fr', 'Français'),
    ('es', 'Español'),
    ('de', 'Deutsch'),
    ('pt', 'Português'),
    ('it', 'Italiano'),
    ('nl', 'Nederlands'),
    ('ar', 'العربية'),
    ('zh', '中文'),
    ('ja', '日本語'),
    ('ko', '한국어'),
    ('hi', 'हिन्दी'),
    ('ru', 'Русский'),
    ('tr', 'Türkçe'),
]

# Default language for new users
DEFAULT_LANGUAGE = 'en'

# RTL languages
RTL_LANGUAGES = ['ar', 'he', 'fa', 'ur']

# Static files
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [
    BASE_DIR / 'frontend' / 'dist',
]
STATICFILES_FINDERS = [
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
]

# Media files
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

# For production with Redis, use:
# CACHES = {
#     'default': {
#         'BACKEND': 'django.core.cache.backends.redis.RedisCache',
#         'LOCATION': os.getenv('REDIS_URL', 'redis://localhost:6379/1'),
#         'OPTIONS': {
#             'CLIENT_CLASS': 'django.core.cache.backends.redis.RedisCache',
#         },
#         'KEY_PREFIX': 'quot_pse',
#         'TIMEOUT': 300,  # 5 minutes default
#     }
# }

CACHE_TTL = {
    'default': 300,  # 5 minutes
    'user_permissions': 600,  # 10 minutes
    'dashboard_stats': 60,  # 1 minute
    'lookup_data': 3600,  # 1 hour
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# django-tenants test runner — creates an isolated tenant schema for each test
# class that extends TenantTestCase, mirroring production multi-tenant behaviour.
TEST_RUNNER = 'django_tenants.test.runner.TenantTestRunner'

FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:5173')

CORS_ALLOWED_ORIGINS = os.getenv(
    'CORS_ALLOWED_ORIGINS',
    'http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000'
).split(',')
CORS_ALLOW_ALL_ORIGINS = DEBUG  # Allow all origins in development only
CORS_ALLOW_CREDENTIALS = not DEBUG  # Credentials only in production (conflicts with ALLOW_ALL)
CORS_ALLOW_METHODS = [
    'GET',
    'POST',
    'PUT',
    'PATCH',
    'DELETE',
    'OPTIONS',
    'HEAD',
]
# django-cors-headers 4.x reads CORS_ALLOW_HEADERS (not CORS_ALLOWED_HEADERS)
# for the Access-Control-Allow-Headers response header.
CORS_ALLOW_HEADERS = [
    "accept",
    "accept-encoding",
    "authorization",
    "content-type",
    "dnt",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
    "x-tenant-domain",
    "x-organization-id",
]
CORS_EXPOSE_HEADERS = [
    "x-total-count",
    "x-page-count",
]
CORS_PREFLIGHT_MAX_AGE = 86400  # 24 hours

REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'core.permissions.RBACPermission',
    ],
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'core.authentication.ExpiringTokenAuthentication',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_THROTTLE_RATES': {
        # Global burst limits.
        'anon': '100/hour',
        'user': '1000/hour',
        # Per-endpoint scopes. Apply via
        #     throttle_classes = [ScopedRateThrottle]
        #     throttle_scope = '<name>'
        # on the relevant view/action.
        # Login throttle is env-configurable: prod stays strict at 3/min,
        # DEBUG defaults to 30/min so a dev with a fat-finger password
        # doesn't keep locking themselves out.
        'login':        os.getenv('LOGIN_THROTTLE_RATE', '30/min' if DEBUG else '3/min'),
        'signup':       '5/hour',
        'impersonate':  '20/hour',   # superadmin tenant impersonation
        # P1-T5 — tighter limits for mutating endpoints so a runaway
        # client can't DoS the posting pipeline. Applied via
        # throttle_scope='writes' on POST/PUT/PATCH/DELETE-only actions.
        'writes':       '300/hour',
        # Bulk imports are rate-limited separately since one call can
        # legitimately insert thousands of rows.
        'bulk_import':  '10/hour',
        # Approval actions — prevent approval-click spam.
        'approve':      '120/hour',
    },
    'DEFAULT_VERSION': 'v1',
    'VERSION_PARAM': 'version',
    'ALLOWED_VERSIONS': ['v1', 'v2'],
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

# P7-T1 — drf-spectacular configuration.
SPECTACULAR_SETTINGS = {
    'TITLE': 'Quot PSE API',
    'DESCRIPTION': (
        'Quot PSE — Public Sector ERP for the Office of the Accountant-General. '
        'Multi-tenant IPSAS-compliant GL, budget & appropriation, procurement, '
        'revenue, payroll, and statutory (FIRS / PENCOM) integrations. '
        'All endpoints are tenant-scoped via the X-Tenant-Schema header.'
    ),
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_REQUEST': True,
    'SCHEMA_PATH_PREFIX': r'/api/',
    'TAGS': [
        {'name': 'Accounting', 'description': 'GL, journals, ledgers, IPSAS reports'},
        {'name': 'Budget',     'description': 'Appropriations, warrants, virements, budget control'},
        {'name': 'Procurement','description': 'POs, GRN, vendors, 3-way matching'},
        {'name': 'Revenue',    'description': 'Revenue heads, invoices, collections'},
        {'name': 'HRM',        'description': 'Employees, payroll, pension, social benefits'},
        {'name': 'Core',       'description': 'Auth, tenants, notifications, health'},
        {'name': 'Statutory',  'description': 'FIRS WHT/VAT, PENCOM, NCoA exports'},
    ],
    'CONTACT': {'email': 'support@quotpse.ng'},
    'LICENSE': {'name': 'Proprietary'},
    'SERVERS': [
        {'url': 'https://api.quotpse.ng', 'description': 'Production'},
        {'url': 'http://localhost:8000',  'description': 'Local dev'},
    ],
    'AUTHENTICATION_WHITELIST': [
        'core.authentication.ExpiringTokenAuthentication',
    ],
    'ENUM_NAME_OVERRIDES': {
        # drf-spectacular otherwise warns on shared status enums.
        'JournalStatusEnum':     'accounting.models.gl.JournalHeader.STATUS_CHOICES',
        'AppropriationStatusEnum':'budget.models.Appropriation.STATUS_CHOICES',
    },
    'POSTPROCESSING_HOOKS': [
        'drf_spectacular.hooks.postprocess_schema_enums',
    ],
}

# Token expiration (in hours)
TOKEN_EXPIRATION_HOURS = int(os.getenv('TOKEN_EXPIRATION_HOURS', '24'))

# =============================================================================
# JWT SETTINGS
# =============================================================================
from datetime import timedelta

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=int(os.getenv('JWT_ACCESS_TOKEN_LIFETIME_MINUTES', '15'))),
    'REFRESH_TOKEN_LIFETIME': timedelta(hours=int(os.getenv('JWT_REFRESH_TOKEN_LIFETIME_HOURS', '24'))),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
    
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': os.getenv('JWT_SIGNING_KEY', SECRET_KEY),
    'VERIFYING_KEY': None,
    
    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
    
    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
    'TOKEN_TYPE_CLAIM': 'token_type',
    
    'JTI_CLAIM': 'jti',
}

# Centralized auth: always authenticate against public schema
AUTHENTICATION_BACKENDS = [
    'core.authentication.PublicSchemaBackend',
]

# =============================================================================
# ACCOUNTING MODULE CONFIGURATION
# =============================================================================

DEFAULT_GL_ACCOUNTS = {
    # ── Core Banking / Accounting ──────────────────────────────────────────────
    'CASH_ACCOUNT':               '10100000',   # Cash and Cash Equivalents
    'BANK_ACCOUNT':               '10101000',   # Cash in Bank - Operating

    # ── Receivables / Payables ────────────────────────────────────────────────
    'ACCOUNTS_RECEIVABLE':        '10200000',   # Accounts Receivable (control)
    'ACCOUNTS_PAYABLE':           '20100000',   # Accounts Payable (control)

    # ── Sales Module ──────────────────────────────────────────────────────────
    'SALES_REVENUE':              '40100000',   # Sales Revenue
    # COGS_EXPENSE: used by post_delivery_note() and post_stock_movement() for OUT
    'COGS_EXPENSE':               '50100000',   # Cost of Goods Sold
    # COST_OF_GOODS_SOLD: alias used by post_delivery_note() line 1171
    'COST_OF_GOODS_SOLD':         '50100000',   # Cost of Goods Sold (same account)

    # ── Inventory Module ──────────────────────────────────────────────────────
    # INVENTORY: the master inventory asset account (10300000 = "Inventory")
    'INVENTORY':                  '10300000',   # Inventory (control)
    # GOODS_IN_TRANSIT: clearing account for in-transit inter-warehouse transfers
    'GOODS_IN_TRANSIT':           '10500000',   # Goods in Transit
    # INVENTORY_ADJUSTMENT_INCOME: CR on positive (gain) ADJ stock movement
    'INVENTORY_ADJUSTMENT_INCOME':'41600000',   # Inventory Adjustment Income
    # INVENTORY_SHRINKAGE: DR on negative (loss) ADJ stock movement
    'INVENTORY_SHRINKAGE':        '80800000',   # Inventory Shrinkage

    # ── Procurement Module ────────────────────────────────────────────────────
    'PURCHASE_EXPENSE':           '50100000',   # maps to COGS / Purchase Expense
    # PPV: Purchase Price Variance — difference between PO price and invoice price
    'PPV':                        '50501000',   # Purchase Price Variance (dedicated)
    # GOODS_RECEIPT_CLEARING: GR/IR clearing account for 3-way match P2P workflow.
    # DR Inventory / CR GR/IR at GRN time; DR GR/IR / CR AP at invoice match time.
    'GOODS_RECEIPT_CLEARING':     '20601000',   # GR/IR Clearing Account

    # ── Production Module ─────────────────────────────────────────────────────
    'RAW_MATERIALS':              '10301000',   # Inventory - Raw Materials
    'WIP_INVENTORY':              '10302000',   # Inventory - Work in Progress
    'FINISHED_GOODS':             '10303000',   # Inventory - Finished Goods
    'LABOR_EXPENSE':              '50201000',   # Direct Labor - Wages
    'MANUFACTURING_OVERHEAD':     '50400000',   # Manufacturing Overhead

    # ── HRM / Payroll Module ──────────────────────────────────────────────────
    'SALARY_EXPENSE':             '60100000',   # Salaries and Wages
    'PAYROLL_LIABILITY':          '20200000',   # Accrued Expenses (payroll clearing)
    # TAX_PAYABLE: Sales Tax Payable / PAYE — used by payroll and sales tax postings
    'TAX_PAYABLE':                '20500000',   # Sales Tax Payable
    # PENSION_PAYABLE: pension contributions withheld from employees
    'PENSION_PAYABLE':            '20503000',   # Pension Payable

    # ── Service Module ────────────────────────────────────────────────────────
    'SERVICE_REVENUE':            '40200000',   # Service Revenue
    'SERVICE_EXPENSE':            '91500000',   # Service Expense

    # ── Quality Module ────────────────────────────────────────────────────────
    'QC_EXPENSE':                 '92100000',   # Quality Control Expense
    'SCRAP_EXPENSE':              '92200000',   # Scrap Expense

    # ── Assets Module ────────────────────────────────────────────────────────
    # Cost accounts (reconciliation accounts — balance must match asset register)
    'ASSET_LAND':                 '12100000',   # Land (non-depreciable)
    'ASSET_BUILDINGS':            '12200000',   # Buildings
    'ASSET_EQUIPMENT':            '12300000',   # Equipment & Machinery
    'ASSET_VEHICLES':             '12303000',   # Motor Vehicles
    'ASSET_FURNITURE':            '12305000',   # Furniture & Fixtures
    # Accumulated depreciation accounts (contra-asset, per category on BS)
    'ACCUM_DEPR_BUILDINGS':       '12202000',   # Accum Depr - Buildings
    'ACCUM_DEPR_EQUIPMENT':       '12306000',   # Accum Depr - Equipment
    'ACCUM_DEPR_VEHICLES':        '12307000',   # Accum Depr - Vehicles
    'ACCUM_DEPR_FURNITURE':       '12308000',   # Accum Depr - Furniture
    # Depreciation expense accounts (per category on P&L)
    'DEPR_EXPENSE_BUILDINGS':     '66101000',   # Depreciation - Buildings
    'DEPR_EXPENSE_EQUIPMENT':     '66102000',   # Depreciation - Equipment
    'DEPR_EXPENSE_VEHICLES':      '66103000',   # Depreciation - Vehicles
    'DEPR_EXPENSE_FURNITURE':     '66104000',   # Depreciation - Furniture
    # General expense & P&L accounts
    'MAINTENANCE_EXPENSE':        '61300000',   # Maintenance and Repairs
    'DEPRECIATION_EXPENSE':       '66100000',   # Depreciation Expense (parent/fallback)
    'GAIN_ON_DISPOSAL':           '41300000',   # Gain on Asset Disposal
    'LOSS_ON_DISPOSAL':           '67400000',   # Loss on Asset Disposal
}

INVENTORY_SETTINGS = {
    'ENABLE_BATCH_EXPIRY_ALERTS': True,
    'EXPIRY_ALERT_DAYS': 30,
    'ENABLE_SERIAL_NUMBER_TRACKING': True,
    'DEFAULT_VALUATION_METHOD': 'WA',
}

PROCUREMENT_SETTINGS = {
    'REQUIRE_THREE_WAY_MATCH': True,
    'ALLOW_PARTIAL_RECEIVING': True,
    'INVOICE_VARIANCE_THRESHOLD': 5.0,
}

SALES_SETTINGS = {
    'ENABLE_CREDIT_CHECK_ON_ORDER': True,
    'CREDIT_WARNING_THRESHOLD': 80,
    'REQUIRE_SALES_APPROVAL': True,
    'AUTO_GENERATE_INVOICE_ON_DELIVERY': True,
}

# =============================================================================
# SECURITY SETTINGS
# =============================================================================
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'
SECURE_CROSS_ORIGIN_OPENER_POLICY = 'same-origin'
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
PASSWORD_RESET_TIMEOUT = 3600

if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# =============================================================================
# CONTENT SECURITY POLICY (django.middleware.csp)
# =============================================================================
FRONTEND_ORIGIN = os.getenv('FRONTEND_URL', 'http://localhost:5173')

SECURE_CSP = {
    "default-src": ["'self'"],
    "script-src": ["'self'"],
    "style-src": ["'self'", "'unsafe-inline'"],  # inline styles used by antd
    "img-src": ["'self'", "data:", "blob:"],
    "font-src": ["'self'", "data:"],
    "connect-src": ["'self'", FRONTEND_ORIGIN],
    "frame-ancestors": ["'none'"],
    "base-uri": ["'self'"],
    "form-action": ["'self'"],
}

if DEBUG:
    # In development, allow Vite HMR websocket and dev server
    SECURE_CSP["connect-src"] += ["ws://localhost:*", "http://localhost:*"]
    SECURE_CSP["script-src"] += ["'unsafe-inline'"]  # Vite injects inline scripts

# =============================================================================
# EMAIL (P5-T3)
# =============================================================================
# Backend selection:
#   - If EMAIL_HOST is set (production/staging): use SMTP.
#   - If DEBUG and EMAIL_HOST unset: use console (mails print to stdout).
#   - If EMAIL_BACKEND_OVERRIDE set: honour it (tests use ``locmem``).
_email_override = os.getenv('EMAIL_BACKEND_OVERRIDE', '').strip()
if _email_override:
    EMAIL_BACKEND = _email_override
elif os.getenv('EMAIL_HOST', '').strip():
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
elif DEBUG:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
else:
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'

EMAIL_HOST = os.getenv('EMAIL_HOST', '')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '587'))
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'true').lower() in ('1', 'true', 'yes')
EMAIL_USE_SSL = os.getenv('EMAIL_USE_SSL', 'false').lower() in ('1', 'true', 'yes')
EMAIL_TIMEOUT = int(os.getenv('EMAIL_TIMEOUT', '10'))

DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'noreply@quotpse.ng')
SERVER_EMAIL = os.getenv('SERVER_EMAIL', DEFAULT_FROM_EMAIL)
SUPPORT_EMAIL = os.getenv('SUPPORT_EMAIL', 'support@quotpse.ng')

# =============================================================================
# CACHING — Phase 2: Redis (shared across workers), fallback to LocMem
# =============================================================================
REDIS_URL = os.getenv('REDIS_URL', '')

if REDIS_URL:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': REDIS_URL,
            'KEY_PREFIX': 'dtsg',
            'TIMEOUT': 300,
            'OPTIONS': {
                'socket_connect_timeout': 5,
                'socket_timeout': 5,
                'retry_on_timeout': True,
            },
        },
        'tenant_cache': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': REDIS_URL,
            'KEY_PREFIX': 'dtsg_tenant',
            'TIMEOUT': 900,  # 15 min for domain/access lookups
        },
        'session_cache': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': REDIS_URL,
            'KEY_PREFIX': 'dtsg_session',
            'TIMEOUT': 86400,
        },
    }
    # Phase 2: Use Redis for sessions when available
    SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
    SESSION_CACHE_ALIAS = 'session_cache'
    # Celery will connect to Redis
    CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'dtsg-erp-cache',
            'TIMEOUT': 300,
        },
        'tenant_cache': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'dtsg-tenant-cache',
            'TIMEOUT': 900,
        },
    }

# =============================================================================
# CELERY — Phase 2: Async task processing
# =============================================================================
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', REDIS_URL or 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', REDIS_URL or 'redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 600  # 10 min hard limit
CELERY_TASK_SOFT_TIME_LIMIT = 540  # 9 min soft limit
CELERY_WORKER_PREFETCH_MULTIPLIER = 1  # Fair scheduling for tenant tasks
CELERY_TASK_ACKS_LATE = True  # Re-queue on worker crash

# Celery Beat schedule for periodic tasks
CELERY_BEAT_SCHEDULE = {
    'cleanup-expired-sessions': {
        'task': 'tenants.tasks.cleanup_expired_sessions',
        'schedule': 3600,  # Every hour
    },
    'cleanup-expired-tokens': {
        'task': 'tenants.tasks.cleanup_expired_tokens',
        'schedule': 86400,  # Daily
    },
}

# =============================================================================
# SENTRY (P3-T2) — gated on SENTRY_DSN env var so dev environments and
# CI don't need the SDK installed. If SENTRY_DSN is set and sentry_sdk
# is importable, integrations are initialised below; otherwise the
# startup is silent.
# =============================================================================
SENTRY_DSN = os.getenv('SENTRY_DSN', '').strip()
if SENTRY_DSN:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.django import DjangoIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration

        sentry_sdk.init(
            dsn=SENTRY_DSN,
            environment=os.getenv('SENTRY_ENVIRONMENT', 'production'),
            release=os.getenv('SENTRY_RELEASE', ''),
            integrations=[
                DjangoIntegration(
                    transaction_style='url',
                    middleware_spans=True,
                    signals_spans=False,
                ),
                LoggingIntegration(
                    level=logging.INFO,        # breadcrumbs
                    event_level=logging.ERROR, # send errors as Sentry events
                ),
            ],
            # Traces — sample 10% by default (override via env).
            traces_sample_rate=float(os.getenv('SENTRY_TRACES_SAMPLE_RATE', '0.10')),
            # PII redaction — do NOT send personally identifiable info
            # unless explicitly enabled for a debugging session.
            send_default_pii=_truthy(os.getenv('SENTRY_SEND_PII', '0')),
            # before_send_transaction hook could redact tenant_domain,
            # JWT tokens, etc. — wire here when needed.
        )
    except ImportError:
        # sentry-sdk not installed — log once at startup, don't crash.
        import warnings
        warnings.warn(
            'SENTRY_DSN is set but sentry-sdk is not installed. '
            'Run: pip install "sentry-sdk[django]"',
            RuntimeWarning,
        )


def _truthy(v):
    if v is None:
        return False
    return str(v).strip().lower() in ('1', 'true', 'yes', 'on')


# =============================================================================
# LOGGING
# =============================================================================
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
        # P3-T1 — one JSON object per log record. Used in production
        # (DEBUG=False) so log aggregators (ELK, Datadog, CloudWatch)
        # can parse the fields without regex heuristics.
        'json': {
            '()': 'core.logging.JsonFormatter',
        },
    },
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse',
        },
        'require_debug_true': {
            '()': 'django.utils.log.RequireDebugTrue',
        },
        'sensitive_data': {
            '()': 'core.utils.SensitiveDataFilter',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            # JSON in production, plain text in DEBUG.
            'formatter': 'json' if not DEBUG else 'simple',
        },
        'security_file': {
            '()': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs' / 'security.log',
            'maxBytes': 10485760,  # 10MB
            'backupCount': 5,
            'formatter': 'verbose',
            'filters': ['sensitive_data'],
        },
        'error_file': {
            '()': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs' / 'django_error.log',
            'maxBytes': 10485760,  # 10MB
            'backupCount': 5,
            'formatter': 'verbose',
            'filters': ['sensitive_data'],
        },
        'django_file': {
            '()': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs' / 'django.log',
            'maxBytes': 10485760,  # 10MB
            'backupCount': 5,
            'formatter': 'verbose',
            'filters': ['sensitive_data'],
        },
        'mail_admins': {
            'level': 'ERROR',
            'filters': ['require_debug_false'],
            'class': 'django.utils.log.AdminEmailHandler',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'django_file'],
            'level': 'INFO' if DEBUG else 'WARNING',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['error_file', 'mail_admins'],
            'level': 'ERROR',
            'propagate': False,
        },
        'security': {
            'handlers': ['console', 'security_file'],
            'level': 'INFO',
            'propagate': False,
        },
        'dtsg': {
            'handlers': ['console', 'django_file'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        # P3-T1 — request-completion log line emitted by
        # core.logging.RequestContextMiddleware. One INFO line per
        # request with method + path + duration_ms.
        'quot_pse.request': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}
