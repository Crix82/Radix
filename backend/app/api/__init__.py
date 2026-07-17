from fastapi import APIRouter

from app.api import (
    audit,
    auth,
    chat,
    collections,
    documents,
    health,
    indexing,
    search,
    sources,
    uploads,
    users,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(search.router)
api_router.include_router(chat.router)
api_router.include_router(documents.router)
api_router.include_router(sources.router)
api_router.include_router(uploads.router)
api_router.include_router(indexing.router)
api_router.include_router(collections.router)
api_router.include_router(users.router)
api_router.include_router(audit.router)
