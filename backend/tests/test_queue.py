import pytest

from app.core import queue


class FakeQueue:
    def __init__(self) -> None:
        self.jobs: list[tuple[str, tuple, dict]] = []

    def enqueue(self, func: str, *args, **kwargs) -> None:
        self.jobs.append((func, args, kwargs))


@pytest.fixture
def fake_queue(monkeypatch: pytest.MonkeyPatch) -> FakeQueue:
    q = FakeQueue()
    monkeypatch.setattr(queue, "get_queue", lambda: q)
    return q


@pytest.mark.parametrize(
    ("enqueue", "func"),
    [
        (queue.enqueue_parse_document, "worker.jobs.parse_document"),
        (queue.enqueue_embed_chunks, "worker.jobs.embed_chunks"),
    ],
)
def test_document_jobs_outlive_rq_default_timeout(fake_queue, enqueue, func) -> None:
    """RQ's 180 s default stopped long documents mid-parse (seen as 'Pipeline failed')."""
    enqueue(7)
    assert fake_queue.jobs == [(func, (7,), {"job_timeout": queue.DOCUMENT_JOB_TIMEOUT})]
    assert queue.DOCUMENT_JOB_TIMEOUT > 180


def test_source_sync_keeps_the_default_timeout(fake_queue) -> None:
    queue.enqueue_sync_source(3)
    assert fake_queue.jobs == [("worker.jobs.sync_source", (3,), {})]
