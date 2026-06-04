from celery import Celery

celery_app = Celery(
    'image_processor',
    broker='amqp://guest:guest@rabbitmq:5672//',
    include=['tasks']
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Asia/Tehran',
    enable_utc=True,
    task_track_started=True,
    broker_connection_retry_on_startup=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    broker_connection_retry=True,
    broker_connection_max_retries=100,
    broker_connection_retry_delay=5,
)