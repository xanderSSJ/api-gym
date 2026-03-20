from __future__ import annotations

from celery.utils.log import get_task_logger

from app.workers.celery_app import celery_app

logger = get_task_logger(__name__)


@celery_app.task(name="maintenance.ping")
def ping() -> dict[str, str]:
    logger.info("Celery ping executed.")
    return {"status": "ok"}
