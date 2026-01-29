import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-example-key-do-not-use-in-production",
)

DEBUG = True

ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "rest_framework",
    "myapi",
]

MIDDLEWARE = [
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "myapi.urls"

# Database — use DATABASE_URL env var if set, otherwise fall back to sqlite
_database_url = os.environ.get("DATABASE_URL", "")

if _database_url.startswith("postgres"):
    # Parse postgres://user:pass@host:port/dbname
    _parts = _database_url.replace("postgres://", "").split("@")
    _user_pass = _parts[0].split(":")
    _host_port_db = _parts[1].split("/")
    _host_port = _host_port_db[0].split(":")
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": _host_port_db[1],
            "USER": _user_pass[0],
            "PASSWORD": _user_pass[1],
            "HOST": _host_port[0],
            "PORT": _host_port[1] if len(_host_port) > 1 else "5432",
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
