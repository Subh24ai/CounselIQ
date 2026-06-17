"""Celery application factory and configuration.

Worker entrypoint::

    celery -A app.tasks.celery_app:celery_app worker --loglevel=info
"""

from __future__ import annotations

from celery import Celery
from kombu import Queue

from app.config import settings

celery_app = Celery(
    "counseliq",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    # Explicitly import the task modules at worker startup. Autodiscovery looks
    # for a ``tasks`` submodule per package and would miss these task modules,
    # leaving their tasks unregistered (and ``.delay()`` failing at runtime).
    include=[
        "app.tasks.extraction",
        "app.tasks.analysis",
        "app.tasks.embeddings",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_track_started=True,
    # Requeue tasks if a worker crashes mid-execution (important for long
    # Textract jobs) and only prefetch one task at a time per worker.
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    result_expires=3600,
    # Dedicated queues keep heavy extraction/analysis work off the default lane.
    task_default_queue="default",
    task_queues=(
        Queue("default"),
        Queue("extraction"),
        Queue("analysis"),
    ),
    task_routes={
        "app.tasks.extraction.*": {"queue": "extraction"},
        "app.tasks.analysis.*": {"queue": "analysis"},
    },
)

# Task modules are auto-discovered as they are added under ``app.tasks``.
celery_app.autodiscover_tasks(["app.tasks"])


@celery_app.task(name="counseliq.ping")
def ping() -> str:
    """Trivial health task used to verify the worker is alive."""
    return "pong"
