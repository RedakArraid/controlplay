from celery_app import celery_app
import tasks  # noqa: F401


if __name__ == "__main__":
    celery_app.start()
