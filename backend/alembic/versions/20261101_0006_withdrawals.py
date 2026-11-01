"""Заявки на вывод и список банков (этап 4)

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Q-28: банки по ответу владельца. Дальше список редактируется в панели.
_BANKS = ["Kaspi Bank", "Halyk Bank", "Банк ЦентрКредит", "ForteBank", "Freedom Bank Kazakhstan"]


def upgrade() -> None:
    banks = op.create_table(
        "banks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_banks")),
        sa.UniqueConstraint("name", name=op.f("uq_banks_name")),
    )
    op.bulk_insert(
        banks,
        [{"name": n, "is_active": True, "sort_order": i} for i, n in enumerate(_BANKS, start=1)],
    )

    op.create_table(
        "withdrawal_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("poker_account_id", sa.Integer(), nullable=False),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("commission_percent", sa.String(length=8), server_default="0", nullable=False),
        sa.Column("commission_amount", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("holder_name", sa.String(length=120), nullable=True),
        sa.Column("bank_id", sa.Integer(), nullable=True),
        sa.Column("bank_name", sa.String(length=100), nullable=True),
        sa.Column("payment_details", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("assigned_staff_id", sa.BigInteger(), nullable=True),
        sa.Column("reject_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'rejected', 'cancelled')",
            name=op.f("ck_withdrawal_requests_status_valid"),
        ),
        sa.CheckConstraint(
            "method IN ('fiat', 'crypto')", name=op.f("ck_withdrawal_requests_method_valid")
        ),
        sa.CheckConstraint("amount > 0", name=op.f("ck_withdrawal_requests_amount_positive")),
        sa.CheckConstraint(
            "status <> 'rejected' OR reject_reason IS NOT NULL",
            name=op.f("ck_withdrawal_requests_reject_reason_required"),
        ),
        sa.ForeignKeyConstraint(
            ["bank_id"], ["banks.id"], name=op.f("fk_withdrawal_requests_bank_id_banks")
        ),
        sa.ForeignKeyConstraint(
            ["poker_account_id"],
            ["poker_accounts.id"],
            name=op.f("fk_withdrawal_requests_poker_account_id_poker_accounts"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_withdrawal_requests_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_withdrawal_requests")),
        sa.UniqueConstraint(
            "user_id", "idempotency_key", name=op.f("uq_withdrawal_requests_user_idempotency")
        ),
    )
    op.create_index(op.f("ix_withdrawal_requests_user_id"), "withdrawal_requests", ["user_id"])
    op.create_index(
        op.f("ix_withdrawal_requests_status_created_at"),
        "withdrawal_requests",
        ["status", "created_at"],
    )

    op.create_table(
        "withdrawal_status_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.Integer(), nullable=False),
        sa.Column("from_status", sa.String(length=20), nullable=True),
        sa.Column("to_status", sa.String(length=20), nullable=False),
        sa.Column("actor_type", sa.String(length=16), nullable=False),
        sa.Column("actor_id", sa.BigInteger(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "actor_type IN ('player', 'staff', 'system')",
            name=op.f("ck_withdrawal_status_history_actor_type_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["request_id"],
            ["withdrawal_requests.id"],
            name=op.f("fk_withdrawal_status_history_request_id_withdrawal_requests"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_withdrawal_status_history")),
    )
    op.create_index(
        op.f("ix_withdrawal_status_history_request_id"),
        "withdrawal_status_history",
        ["request_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_withdrawal_status_history_request_id"), table_name="withdrawal_status_history"
    )
    op.drop_table("withdrawal_status_history")
    op.drop_index(op.f("ix_withdrawal_requests_status_created_at"), table_name="withdrawal_requests")
    op.drop_index(op.f("ix_withdrawal_requests_user_id"), table_name="withdrawal_requests")
    op.drop_table("withdrawal_requests")
    op.drop_table("banks")
