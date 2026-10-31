"""baseline: пустая стартовая ревизия

Таблицы предметной области появятся в этапах 2+ отдельными миграциями.

Revision ID: 0001
Revises:
Create Date: 2026-10-31
"""
from typing import Sequence, Union

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
