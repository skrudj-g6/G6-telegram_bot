"""USDT в заявках на пополнение; счётчик попыток занять чужой игровой ID

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-31
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Q-29: первая попытка занять чужой ID — предупреждение, вторая — блокировка.
    op.add_column(
        "users",
        sa.Column("duplicate_id_attempts", sa.Integer(), server_default="0", nullable=False),
    )
    # Пополнение криптой: сумма USDT в сотых и курс на момент создания заявки.
    op.add_column("deposit_requests", sa.Column("crypto_amount", sa.BigInteger(), nullable=True))
    op.add_column(
        "deposit_requests", sa.Column("exchange_rate", sa.String(length=32), nullable=True)
    )


def downgrade() -> None:
    # recreate="never": обычный ALTER ... DROP COLUMN (SQLite 3.35+ и PostgreSQL),
    # без пересоздания таблиц вместе с их ограничениями.
    with op.batch_alter_table("deposit_requests", recreate="never") as batch:
        batch.drop_column("exchange_rate")
        batch.drop_column("crypto_amount")
    with op.batch_alter_table("users", recreate="never") as batch:
        batch.drop_column("duplicate_id_attempts")
