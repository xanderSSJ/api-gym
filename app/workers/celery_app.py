from __future__ import annotations

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "gym_api_worker",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.task_serializer = "json"
celery_app.conf.result_serializer = "json"
celery_app.conf.accept_content = ["json"]
celery_app.conf.timezone = "UTC"
celery_app.conf.enable_utc = True

celery_app.autodiscover_tasks(["app.workers.tasks"])
