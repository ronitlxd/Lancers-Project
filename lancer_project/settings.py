import os
from pathlib import Path
from decouple import config, Csv

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config('SECRET_KEY', default='dev-secret-key-change-me-in-env')

DEBUG = config('DEBUG', default=True, cast=bool)

ALLOWED_HOSTS = config(
    'ALLOWED_HOSTS',
    default='127.0.0.1,localhost,testserver,lad91.pythonanywhere.com',
    cast=Csv()
)

# Redirects for authentication
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # django.contrib.sites is a hard requirement of allauth.
    'django.contrib.sites',
    'axes',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.microsoft',
    'accounts',
    'injuries',
    'injury_tracking',
]

SITE_ID = 1

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'axes.middleware.AxesMiddleware',
    # Must sit after AuthenticationMiddleware (IT Services Appendix A).
    'allauth.account.middleware.AccountMiddleware',
    # Prevent back-button re-entry after logout
    'lancer_project.middleware.NoCacheAuthenticatedMiddleware',
]

ROOT_URLCONF = 'lancer_project.urls'

# Friendly CSRF failure: redirect with a flash message instead of the debug 403 page.
CSRF_FAILURE_VIEW = 'accounts.views.csrf_failure'
CSRF_COOKIE_AGE = 60 * 60 * 24 * 365
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'lancer_project.wsgi.application'

# IT Services will host on University Kubernetes with SQLite (their response,
# section 1.5), backing up the database file and its write-ahead log from the
# application data directory.  DB_PATH therefore has to point at the mounted
# volume: a database inside the container image would be lost on restart.
#
# Appendix A runs Gunicorn with two workers against one SQLite file, so WAL
# plus a busy timeout are needed or concurrent writes surface as intermittent
# 'database is locked' errors.
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': config('DB_PATH', default=str(BASE_DIR / 'db.sqlite3')),
        'OPTIONS': {
            'timeout': 20,
            'init_command': 'PRAGMA journal_mode=WAL;',
        },
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_L10N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL = '/media/'

# Uploaded files live OUTSIDE BASE_DIR so that no static-file mapping or
# web-server rule can reach them: the only way to retrieve an injury photo is
# through the permission-checked view in accounts.views.serve_injury_photo.
# In the University Kubernetes deployment this is set to the mounted persistent
# volume -- container filesystems are ephemeral, so without a volume every
# uploaded photo is lost on pod restart.  (UWindsor IT review, Nov 2026.)
MEDIA_ROOT = Path(config('MEDIA_ROOT', default=str(BASE_DIR.parent / 'lancer_media')))

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

AUTH_USER_MODEL = 'accounts.CustomUser'

# Compat shim: Django 5.x passes `durations` to TextTestRunner, but that
# kwarg only exists in Python 3.12+.  The custom runner strips it on 3.11.
TEST_RUNNER = 'lancer_project.testrunner.CompatDiscoverRunner'

# Authentication backends -- axes must come first.
#
# NOTE, deliberate deviation from IT Services Appendix A: their example lists
# only ModelBackend and allauth.  We keep django-axes.  Their snippet is
# generic guidance rather than a review of this project's settings, and axes
# still protects whatever local password login remains (the break-glass admin
# account) once Entra handles everyone else.
AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesStandaloneBackend',
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

# ---------------------------------------------------------------------------
# Email -- OFF by default (UWindsor IT review, finding 4 / IT response 1.6)
#
# IT Services' deployment posture for this application is "no egress, and only
# ingress through the web interface, unless there is a documented and approved
# need" (25 Nov 2026).  They have paused on SMTP relay details until there is a
# clear functional case, so the application must not attempt an outbound
# connection: against a blocked network send_mail does not fail fast, it hangs
# until the socket times out, tying up a worker.
#
# Two independent guards:
#   1. NOTIFICATION_EMAIL_ENABLED (below) stops notify() from calling send_mail
#      at all.  Notifications stay in-app, which is where they already appear.
#   2. EMAIL_BACKEND defaults to the dummy backend, which discards messages
#      without opening a socket, so any future sender is also safe by default.
#
# To turn email on once a relay is approved, set NOTIFICATION_EMAIL_ENABLED and
# EMAIL_BACKEND (plus host, port and credentials) in the environment.
# ---------------------------------------------------------------------------
NOTIFICATION_EMAIL_ENABLED = config(
    'NOTIFICATION_EMAIL_ENABLED', default=False, cast=bool)

EMAIL_BACKEND = config(
    'EMAIL_BACKEND',
    default='django.core.mail.backends.dummy.EmailBackend'
)
EMAIL_HOST = config('EMAIL_HOST', default='')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
DEFAULT_FROM_EMAIL = config(
    'DEFAULT_FROM_EMAIL',
    default='LancersPulse <noreply@uwindsor.ca>'
)

# django-axes rate limiting: lock after 5 failures, cooloff 5 minutes
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 0.0833
AXES_LOCKOUT_TEMPLATE = 'accounts/lockout.html'
AXES_RESET_ON_SUCCESS = True
AXES_ENABLE_ADMIN = True
AXES_LOCKOUT_PARAMETERS = ['username', 'ip_address']

# Reverse proxy trust (UWindsor IT review, finding 4; Appendix A).
#
# The campus Gateway terminates TLS at the public hostname and forwards plain
# HTTP to port 8080.  Without these two settings Django sees an insecure
# request, and SECURE_SSL_REDIRECT below sends it back to https forever: an
# infinite redirect loop the moment staging goes up.
#
# Gated on BEHIND_PROXY so local development is unaffected.  Enabling this
# means trusting X-Forwarded-Proto, which is only safe because the Gateway
# strips client-supplied values -- stated as an assumption to IT Services.
if config('BEHIND_PROXY', default=False, cast=bool):
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    USE_X_FORWARDED_HOST = True

# Production-only security settings (auto-activate when DEBUG=False)
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    X_FRAME_OPTIONS = 'DENY'


# ---------------------------------------------------------------------------
# Audit logging (UWindsor IT review, finding 7)
#
# IT Services' response, section 1.7: write significant audit events to
# standard error, timestamped.  Kubernetes captures stderr and the platform
# pipeline forwards it to the University SIEM, so the application needs no
# SIEM client of its own.
#
# The 'lancerspulse.audit' logger uses a bare formatter on purpose: each record
# is already a complete JSON object (see lancer_project/audit.py) carrying its
# own ISO-8601 'ts' field, so prefixing it would break downstream parsing.
# Retention is set by the platform; one year is proposed for staging and is not
# yet confirmed by IT.
# ---------------------------------------------------------------------------
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'raw': {'format': '%(message)s'},
        'standard': {'format': '%(asctime)s %(levelname)s %(name)s %(message)s'},
    },
    'handlers': {
        'audit_stderr': {
            'class': 'logging.StreamHandler',
            'stream': 'ext://sys.stderr',
            'formatter': 'raw',
        },
        'stderr': {
            'class': 'logging.StreamHandler',
            'stream': 'ext://sys.stderr',
            'formatter': 'standard',
        },
    },
    'loggers': {
        'lancerspulse.audit': {
            'handlers': ['audit_stderr'],
            'level': 'INFO',
            'propagate': False,
        },
        'django': {
            'handlers': ['stderr'],
            'level': config('DJANGO_LOG_LEVEL', default='INFO'),
            'propagate': False,
        },
    },
}


# ---------------------------------------------------------------------------
# Microsoft Entra SSO (UWindsor IT review, finding 4)
#
# Follows Appendix A of the IT Services response.  Entra AUTHENTICATES ONLY:
# there are no Entra security groups for the dashboard roles and none are
# planned, so Django remains the sole authority on authorization (IT response
# sections 1.2, 1.3 and 3.6).
#
# Credentials arrive as environment variables.  In the hosted environment IT
# Services injects them from the Kubernetes Secret 'hk-mac-injury-entra-creds';
# locally they come from .env, which is gitignored.
# ---------------------------------------------------------------------------
SOCIALACCOUNT_PROVIDERS = {
    'microsoft': {
        'TENANT': config('ENTRA_TENANT_ID', default=''),
        'APP': {
            'client_id': config('ENTRA_CLIENT_ID', default=''),
            'secret': config('ENTRA_CLIENT_SECRET', default=''),
            'key': '',
        },
        'SCOPE': ['User.Read', 'openid', 'profile', 'email'],
    }
}

# No access by default.  Both adapters refuse to create accounts: a person who
# authenticates successfully against Entra but has no account provisioned here
# is turned away.  This is the mechanism behind IT response section 1.3.
ACCOUNT_ADAPTER = 'accounts.adapters.NoSelfSignupAccountAdapter'
SOCIALACCOUNT_ADAPTER = 'accounts.adapters.EntraSocialAccountAdapter'
SOCIALACCOUNT_AUTO_SIGNUP = False

# Sign-in and sign-out go over POST with CSRF protection (Appendix A).
ACCOUNT_LOGOUT_ON_GET = False
SOCIALACCOUNT_LOGIN_ON_GET = False
ACCOUNT_LOGOUT_REDIRECT_URL = '/login/'

# Entra has already verified the address; we never send verification mail.
ACCOUNT_EMAIL_VERIFICATION = 'none'

# We make no Graph calls after sign-in, so there is no reason to keep access
# or refresh tokens in the database where they would be one more thing to leak.
SOCIALACCOUNT_STORE_TOKENS = False


# ---------------------------------------------------------------------------
# Data retention (UWindsor IT review, finding 5)
#
# Agreed with CHPH (Dr. Sutherland) on 25 Nov 2026.
#
# CAVEAT WORTH KEEPING VISIBLE: these periods were proposed by the project team
# as sensible defaults and accepted as proposed.  They have NOT been checked
# against a University of Windsor records retention schedule, and retention of
# health-related records is often prescribed rather than chosen.  University
# Records Management should confirm them before this is treated as policy; the
# seven-year figure in particular is a common default, not a verified one.
#
# IT Services supports anonymising rather than deleting, so year-over-year
# injury trends survive, and deleting identifying photos when the related
# record is anonymised (their response, section 3.16).
#
# IMPORTANT (IT response, section 1.8): application deletions do NOT propagate
# to backups.  After any restore, re-run `purge_expired_data`, then
# `replay_purge_ledger` for anything deleted outside the retention rules.
# ---------------------------------------------------------------------------
# Injury records: anonymise seven years after the last activity on the record.
RETENTION_INJURY_RECORD_YEARS = config(
    'RETENTION_INJURY_RECORD_YEARS', default=7, cast=int)

# Injury photographs: one year, "or on recovery if later" - so both conditions
# must hold.  A photograph of an injury still being treated after a year is
# still clinically useful, and deleting it on the calendar alone would take a
# working record away from the therapist.
RETENTION_INJURY_PHOTO_DAYS = config(
    'RETENTION_INJURY_PHOTO_DAYS', default=365, cast=int)

# Appointment notes and wellness check-ins: same clock as injury records.
RETENTION_SUPPORTING_RECORD_YEARS = config(
    'RETENTION_SUPPORTING_RECORD_YEARS',
    default=config('RETENTION_INJURY_RECORD_YEARS', default=7, cast=int),
    cast=int)

# Emergency contact details: removed when the athlete leaves the programme.
# "Leaves" is approximated by the account being deactivated, since nothing
# else in the system records a departure.  PROCESS DEPENDENCY: this rule only
# fires if someone actually deactivates leavers' accounts.  Default 0 days
# means "as soon as the account is deactivated"; raise it for a grace period.
RETENTION_EMERGENCY_CONTACT_DAYS = config(
    'RETENTION_EMERGENCY_CONTACT_DAYS', default=0, cast=int)

RETENTION_PENDING_UPLOAD_DAYS = config(
    'RETENTION_PENDING_UPLOAD_DAYS', default=1, cast=int)
