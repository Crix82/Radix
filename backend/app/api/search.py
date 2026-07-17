from fastapi import APIRouter, Query, Request

from app.core.deps import CurrentUser, DbSession
from app.core.permissions import allowed_collection_ids
from app.models import AuditLog
from app.models.schemas import SearchDocumentRef, SearchResultOut
from app.services import search as search_service
from app.services.embeddings import get_embedder
from app.services.vectorstore import get_client

router = APIRouter(prefix="/search", tags=["search"])


def _effective_collections(allowed: list[int] | None, requested: int | None) -> list[int] | None:
    """Combine the user's readable collections with an optional collection filter."""
    if requested is None:
        return allowed
    if allowed is None:  # admin: honor the requested filter
        return [requested]
    return [requested] if requested in allowed else []


@router.get("", response_model=list[SearchResultOut])
def search(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    q: str = Query(min_length=1),
    lang: str | None = Query(default=None),
    doc_type: str | None = Query(default=None),
    collection_id: int | None = Query(default=None),
) -> list[SearchResultOut]:
    allowed = _effective_collections(allowed_collection_ids(db, user), collection_id)

    results = search_service.hybrid_search(
        db=db,
        embedder=get_embedder(),
        client=get_client(),
        query=q,
        allowed_collection_ids=allowed,
        lang=lang,
        doc_type=doc_type,
    )

    db.add(
        AuditLog(
            user_id=user.id,
            action="search",
            meta={"q": q, "lang": lang, "doc_type": doc_type, "results": len(results)},
            ip=request.client.host if request.client else None,
        )
    )
    db.commit()

    return [
        SearchResultOut(
            chunk_id=r.chunk_id,
            document=SearchDocumentRef(
                id=r.document_id,
                title=r.title,
                lang=r.lang,
                doc_type=r.doc_type,
                rel_path=r.rel_path,
            ),
            page=r.page,
            snippet_html=r.snippet_html,
            score=r.score,
        )
        for r in results
    ]
