import redis
from rq import Queue, Worker

from app.core.config import get_settings

QUEUE_NAME = "radix"


def main() -> None:
    connection = redis.Redis.from_url(get_settings().redis_url)
    worker = Worker([Queue(QUEUE_NAME, connection=connection)], connection=connection)
    worker.work()


if __name__ == "__main__":
    main()
