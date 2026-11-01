"""Комиссия клуба на пополнение и вывод (Q-33)

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_KEYS = ("deposit_commission_percent", "withdrawal_commission_percent")


def upgrade() -> None:
    # Снимок комиссии на момент создания заявки: смена процента на старые заявки не влияет.
    op.add_column(
        "deposit_requests",
        sa.Column("commission_percent", sa.String(length=8), server_default="0", nullable=False),
    )
    op.add_column(
        "deposit_requests",
        sa.Column("commission_amount", sa.BigInteger(), server_default="0", nullable=False),
    )
    settings = sa.table("app_settings", sa.column("key", sa.String), sa.column("value", sa.String))
    op.bulk_insert(settings, [{"key": k, "value": "0"} for k in _KEYS])


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM app_settings WHERE key IN (:a, :b)").bindparams(a=_KEYS[0], b=_KEYS[1]))
    with op.batch_alter_table("deposit_requests", recreate="never") as batch:
        batch.drop_column("commission_amount")
        batch.drop_column("commission_percent")
