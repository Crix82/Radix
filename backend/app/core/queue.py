"""RQ queue access shared by the API (producers) and the worker (consumer)."""

import redis
from rq import Queue

from app.core.config import get_settings

QUEUE_NAME = "radix"
# RQ stops a job after 180 s unless told otherwise, and the stop lands *inside* Docling, which
# records it as a failed page and ends the conversion as "Pipeline failed" — so any document
# that takes more than three minutes (a scanned book under OCR, a 481-page manual on CPU)
# errored with no hint of a timeout. Parsing and embedding get a bound sized for a large
# scanned book on CPU; source syncs keep the short default.
DOCUMENT_JOB_TIMEOUT = 6 * 3600  # seconds


def get_queue() -> Queue:
    return Queue(QUEUE_NAME, connection=redis.Redis.from_url(get_settings().redis_url))


# Jobs are referenced by dotted path so the API never imports worker code.
def enqueue_sync_source(source_id: int) -> None:
    get_queue().enqueue("worker.jobs.sync_source", source_id)


def enqueue_parse_document(document_id: int) -> None:
    get_queue().enqueue("worker.jobs.parse_document", document_id, job_timeout=DOCUMENT_JOB_TIMEOUT)


def enqueue_embed_chunks(document_id: int) -> None:
    get_queue().enqueue("worker.jobs.embed_chunks", document_id, job_timeout=DOCUMENT_JOB_TIMEOUT)
