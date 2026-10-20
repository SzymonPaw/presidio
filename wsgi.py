"""Production entry point; keep the IT service target wsgi:app."""
import os

if os.environ.get("APP_ENV") != "production":
    raise RuntimeError("APP_ENV=production must be supplied by the service .env file")
if os.environ.get("FLASK_DEBUG", "0") != "0":
    raise RuntimeError("FLASK_DEBUG must be 0 in production")

from src.app_factory import create_app

app = create_app()
