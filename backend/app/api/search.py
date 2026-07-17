from fastapi import APIRouter, HTTPException, status

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", include_in_schema=False)
def not_implemented() -> None:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Planned for milestone M3"
    )
