"""Журнал аудита (D-11): только добавление записей."""

from sqlalchemy.orm import Session

from app.models import AuditLog


def record(
    db: Session,
    *,
    staff_id: int | None,
    action: str,
    entity_type: str | None = None,
    entity_id: int | str | None = None,
    details: dict | None = None,
    ip: str | None = None,
) -> None:
    """Добавляет запись в текущую транзакцию: коммитит вызывающий вместе с самим действием,
    поэтому действие и его след в журнале не могут разойтись."""
    db.add(
        AuditLog(
            staff_id=staff_id,
            action=action,
            entity_type=entity_type,
            entity_id=None if entity_id is None else str(entity_id),
            details=details,
            ip=ip,
        )
    )
