"""Celery task package for CounselIQ.

The configured Celery application lives in :mod:`app.tasks.celery_app`.
"""

from app.tasks.celery_app import celery_app

__all__ = ["celery_app"]
