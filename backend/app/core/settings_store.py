"""Runtime settings persisted in the `settings` table (SPEC §4.1).

These are tunables that change without a redeploy (e.g. the refusal threshold, calibrated
in M4). Env defaults come from `Settings`; the DB value, when present, wins.
"""

from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Setting

REFUSAL_THRESHOLD_KEY = "refusal_threshold"


def get_setting(db: Session, key: str, default: Any) -> Any:
    row = db.get(Setting, key)
    return row.value if row is not None and row.value is not None else default


def set_setting(db: Session, key: str, value: Any) -> None:
    row = db.get(Setting, key)
    if row is None:
        db.add(Setting(key=key, value=value))
    else:
        row.value = value
    db.commit()


def get_refusal_threshold(db: Session) -> float:
    return float(get_setting(db, REFUSAL_THRESHOLD_KEY, get_settings().refusal_threshold))
