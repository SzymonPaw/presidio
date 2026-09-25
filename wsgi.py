"""WSGI entry point for Gunicorn."""

from src.app_factory import create_app


app = create_app()