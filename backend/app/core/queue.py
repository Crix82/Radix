"""RQ queue access shared by the API (producers) and the worker (consumer)."""

import redis
from rq import Queue

from app.core.config import get_settings

QUEUE_NAME = "radix"


def get_queue() -> Queue:
    return Queue(QUEUE_NAME, connection=redis.Redis.from_url(get_settings().redis_url))


# Jobs are referenced by dotted path so the API never imports worker code.
def enqueue_sync_source(source_id: int) -> None:
    get_queue().enqueue("worker.jobs.sync_source", source_id)


def enqueue_parse_document(document_id: int) -> None:
    get_queue().enqueue("worker.jobs.parse_document", document_id)


def enqueue_embed_chunks(document_id: int) -> None:
    get_queue().enqueue("worker.jobs.embed_chunks", document_id)
