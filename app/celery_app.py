import os

from celery import Celery


celery_app = Celery(
    "controlplay",
    broker=os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0"),
    backend=os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/1"),
)

celery_app.conf.task_routes = {
    "tasks.*": {"queue": "controlplay"},
}
