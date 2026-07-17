import json
from collections.abc import Iterator

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.api.search import _effective_collections
from app.core.db import SessionLocal
from app.core.deps import CurrentUser, DbSession, client_ip
from app.core.permissions import allowed_collection_ids
from app.core.settings_store import get_refusal_threshold
from app.models import AuditLog
from app.models.schemas import ChatRequest
from app.services import rag
from app.services.embeddings import get_embedder
from app.services.llm.base import get_llm_provider
from app.services.rag import ChatResult
from app.services.vectorstore import get_client

router = APIRouter(prefix="/chat", tags=["chat"])


def _sse(event: str, data: dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _final_payload(result: ChatResult) -> dict[str, object]:
    return {
        "answer_md": result.answer_md,
        "refusal": result.refusal,
        "citations": [
            {
                "n": c.n,
                "chunk_id": c.chunk_id,
                "document_id": c.document_id,
                "title": c.title,
                "lang": c.lang,
                "page": c.page,
                "bboxes": c.bboxes,
            }
            for c in result.citations
        ],
    }


@router.post("")
def chat(
    body: ChatRequest, request: Request, db: DbSession, user: CurrentUser
) -> StreamingResponse:
    if not any(m.role == "user" for m in body.messages):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="A user message is required"
        )

    allowed = _effective_collections(allowed_collection_ids(db, user), body.filters.collection_id)
    threshold = get_refusal_threshold(db)
    question = next(m.content for m in reversed(body.messages) if m.role == "user")
    db.add(
        AuditLog(
            user_id=user.id,
            action="chat",
            meta={"q": question},
            ip=client_ip(request),
        )
    )
    db.commit()

    messages = [{"role": m.role, "content": m.content} for m in body.messages]
    embedder = get_embedder()
    client = get_client()
    provider = get_llm_provider()

    def stream() -> Iterator[str]:
        # Own DB session: the request-scoped one may close once streaming starts.
        with SessionLocal() as chat_db:
            for kind, payload in rag.answer_stream(
                db=chat_db,
                embedder=embedder,
                client=client,
                provider=provider,
                messages=messages,
                allowed_collection_ids=allowed,
                refusal_threshold=threshold,
                lang=body.filters.lang,
                doc_type=body.filters.doc_type,
            ):
                if kind == "token":
                    yield _sse("token", {"text": payload})
                else:
                    yield _sse("final", _final_payload(payload))

    return StreamingResponse(stream(), media_type="text/event-stream")
