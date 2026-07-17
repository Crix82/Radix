import logging
import threading

import redis
from rq import Queue, Worker
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.queue import QUEUE_NAME, enqueue_sync_source
from app.models import Source, SourceType

logger = logging.getLogger(__name__)


def sync_all_sources() -> None:
    """Enqueue a discover pass for every enabled filesystem-backed source."""
    with SessionLocal() as db:
        source_ids = db.scalars(
            select(Source.id).where(Source.enabled.is_(True), Source.type != SourceType.upload)
        ).all()
    for source_id in source_ids:
        enqueue_sync_source(source_id)


def watcher_loop(stop: threading.Event) -> None:
    """Periodic scan of all sources (SPEC §5: default every 5 minutes)."""
    interval = get_settings().sync_interval_min * 60
    while True:
        try:
            sync_all_sources()
        except Exception:  # noqa: BLE001 - the watcher must survive transient db/redis errors
            logger.exception("watcher: sync scheduling failed")
        if stop.wait(interval):
            return


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    stop = threading.Event()
    threading.Thread(target=watcher_loop, args=(stop,), daemon=True, name="watcher").start()
    connection = redis.Redis.from_url(get_settings().redis_url)
    worker = Worker([Queue(QUEUE_NAME, connection=connection)], connection=connection)
    try:
        worker.work()
    finally:
        stop.set()


if __name__ == "__main__":
    main()
