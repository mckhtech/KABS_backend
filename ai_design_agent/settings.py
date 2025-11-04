import os
from decouple import config
from pathlib import Path
from dotenv import load_dotenv

load_dotenv() 

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config('SECRET_KEY', default='django-insecure-8&l+98ni0)q)&%+%l0di75$1mtliv+l5ebgag4kfkpp1*dp5uo')
DEBUG = config('DEBUG', default=True, cast=bool)
ALLOWED_HOSTS = ['localhost', '127.0.0.1','dogfish-primary-remarkably.ngrok-free.app' ,'*']

# PDF Processing Settings
PDF_DPI = 300  # DPI for PDF to image conversion
PDF_MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB max

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'corsheaders',    
    'rest_framework.authtoken',
    'design_agent',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'ai_design_agent.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
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

WSGI_APPLICATION = 'ai_design_agent.wsgi.application'

# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME', default='ai_design_db'),
        'USER': config('DB_USER', default='postgres'),
        'PASSWORD': config('DB_PASSWORD', default='om@123'),
        'HOST': config('DB_HOST', default='localhost'),
        'PORT': config('DB_PORT', default='5432'),
    }
}

# REST Framework
REST_FRAMEWORK = {
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
        'rest_framework.parsers.MultiPartParser',
        'rest_framework.parsers.FormParser',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
}



# CELERY Configuration (using Redis as broker)
CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'

# Add connection retry settings for reliability
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BROKER_CONNECTION_RETRY = True
CELERY_BROKER_CONNECTION_MAX_RETRIES = 10

# CELERY_TASK_ROUTES = {
#     'design_agent.tasks.process_pdf_to_images': {'queue': 'pdf_processing'},
#     'design_agent.tasks.extract_page_layout': {'queue': 'ai_extraction'},
#     'design_agent.tasks.generate_render_for_page': {'queue': 'rendering'},
# }
# Celery task timeouts
CELERY_TASK_TIME_LIMIT = 1200  # 10 minutes hard limit
CELERY_TASK_SOFT_TIME_LIMIT = 540  # 9 minutes soft limit

CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BROKER_CONNECTION_RETRY = True
CELERY_BROKER_CONNECTION_MAX_RETRIES = 10

# Static files
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
MEDIA_SUBDIRS = ['pdfs', 'pdf_pages', 'skus', 'renders']
for subdir in MEDIA_SUBDIRS:
    os.makedirs(os.path.join(MEDIA_ROOT, subdir), exist_ok=True)

# CORS
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = [
    'https://dogfish-primary-remarkably.ngrok-free.app',
    'http://localhost:5173',
]

CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
    'ngrok-skip-browser-warning',
]

CSRF_TRUSTED_ORIGINS = [
    'https://dogfish-primary-remarkably.ngrok-free.app',
    'http://localhost:5173',
]

# Custom settings
GEMINI_API_KEY = config('GEMINI_API_KEY', default='')
OPENAI_API_KEY = config('OPENAI_API_KEY', default='')  # ✅ FIXED


CHROMADB_PATH = os.path.join(BASE_DIR, 'chroma_db')
CATALOG_DATA_PATH = os.path.join(BASE_DIR, 'catalog_data')

# settings.py - Add these to your Django settings

# AWS Bedrock Settings
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
AWS_DEFAULT_REGION = os.getenv('AWS_DEFAULT_REGION', 'eu-north-1')

# Bedrock Model Configuration
# IMPORTANT: Use ARN for Claude 3.7 (MODEL_ID alone won't work)
BEDROCK_MODEL_ARN = os.getenv(
    'BEDROCK_MODEL_ARN',
    'arn:aws:bedrock:eu-north-1:774846457232:inference-profile/eu.anthropic.claude-3-7-sonnet-20250219-v1:0'
)

BEDROCK_MODEL_ID = os.getenv(
    'BEDROCK_MODEL_ID',
    'eu.anthropic.claude-3-7-sonnet-20250219-v1:0'
)

OPENAI_MODEL_ID = 'gpt-4o'  # Fallback

# Extraction service priority
EXTRACTION_SERVICE = "bedrock"  # 'bedrock' or 'openai'
# Logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': 'design_agent.log',
            'formatter': 'verbose',
        },
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'design_agent': {
            'handlers': ['file', 'console'],
            'level': 'DEBUG',
            'propagate': True,
        },
    },
}