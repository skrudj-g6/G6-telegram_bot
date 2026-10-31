"""заявки на пополнение, настройки, причина блокировки (этап 3)

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-31
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Начальные значения настроек (Q-6, Q-9, Q-23); дальше владелец меняет их в панели.
_SETTINGS = {
    "deposit_min_amount": "1000",
    "deposit_max_amount": "2000000",
    "withdrawal_min_amount": "1000",
    "withdrawal_max_amount": "2000000",
    "deposit_receipt_timeout_minutes": "10",
    "receipt_retention_days": "7",
}


def upgrade() -> None:
    # Q-27: причина автоматической блокировки видна сотруднику.
    op.add_column("users", sa.Column("block_reason", sa.String(length=255), nullable=True))

    app_settings = op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", sa.String(length=255), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("updated_by_staff_id", sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_app_settings")),
    )
    op.bulk_insert(app_settings, [{"key": k, "value": v} for k, v in _SETTINGS.items()])

    op.create_table(
        "deposit_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("poker_account_id", sa.Integer(), nullable=False),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column(
            "status", sa.String(length=20), server_default="awaiting_receipt", nullable=False
        ),
        sa.Column("payment_details", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("receipt_filename", sa.String(length=64), nullable=True),
        sa.Column("receipt_content_type", sa.String(length=32), nullable=True),
        sa.Column("receipt_size", sa.Integer(), nullable=True),
        sa.Column("receipt_uploaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("receipt_deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("assigned_staff_id", sa.BigInteger(), nullable=True),
        sa.Column("reject_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('awaiting_receipt', 'pending', 'processing', 'completed',"
            " 'rejected', 'cancelled', 'expired')",
            name=op.f("ck_deposit_requests_status_valid"),
        ),
        sa.CheckConstraint(
            "method IN ('fiat', 'crypto')", name=op.f("ck_deposit_requests_method_valid")
        ),
        sa.CheckConstraint("amount > 0", name=op.f("ck_deposit_requests_amount_positive")),
        sa.CheckConstraint(
            "status <> 'rejected' OR reject_reason IS NOT NULL",
            name=op.f("ck_deposit_requests_reject_reason_required"),
        ),
        sa.ForeignKeyConstraint(
            ["poker_account_id"],
            ["poker_accounts.id"],
            name=op.f("fk_deposit_requests_poker_account_id_poker_accounts"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_deposit_requests_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_deposit_requests")),
        sa.UniqueConstraint(
            "user_id", "idempotency_key", name=op.f("uq_deposit_requests_user_idempotency")
        ),
    )
    op.create_index(op.f("ix_deposit_requests_user_id"), "deposit_requests", ["user_id"])
    op.create_index(
        op.f("ix_deposit_requests_status_expires_at"),
        "deposit_requests",
        ["status", "expires_at"],
    )

    op.create_table(
        "deposit_status_history",
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
            name=op.f("ck_deposit_status_history_actor_type_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["request_id"],
            ["deposit_requests.id"],
            name=op.f("fk_deposit_status_history_request_id_deposit_requests"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_deposit_status_history")),
    )
    op.create_index(
        op.f("ix_deposit_status_history_request_id"), "deposit_status_history", ["request_id"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_deposit_status_history_request_id"), table_name="deposit_status_history")
    op.drop_table("deposit_status_history")
    op.drop_index(op.f("ix_deposit_requests_status_expires_at"), table_name="deposit_requests")
    op.drop_index(op.f("ix_deposit_requests_user_id"), table_name="deposit_requests")
    op.drop_table("deposit_requests")
    op.drop_table("app_settings")
    # recreate="never": обычный ALTER ... DROP COLUMN (SQLite 3.35+ и PostgreSQL),
    # без пересоздания таблицы users вместе с её ограничениями и ссылками.
    with op.batch_alter_table("users", recreate="never") as batch:
        batch.drop_column("block_reason")
