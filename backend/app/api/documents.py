from fastapi import APIRouter, HTTPException, status

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("", include_in_schema=False)
def not_implemented() -> None:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Planned for milestone M2"
    )
