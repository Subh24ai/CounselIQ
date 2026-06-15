"""Celery application factory and configuration.

Worker entrypoint::

    celery -A app.tasks.celery_app:celery_app worker --loglevel=info
"""

from __future__ import annotations

from celery import Celery

from app.config import settings

celery_app = Celery(
    "counseliq",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    result_expires=3600,
)

# Task modules are auto-discovered as they are added under ``app.tasks``.
celery_app.autodiscover_tasks(["app.tasks"])


@celery_app.task(name="counseliq.ping")
def ping() -> str:
    """Trivial health task used to verify the worker is alive."""
    return "pong"
