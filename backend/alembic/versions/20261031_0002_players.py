"""игроки, клубы, игровые аккаунты (этап 2)

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-31
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    clubs = op.create_table(
        "clubs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("club_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_clubs")),
        sa.UniqueConstraint("club_id", name=op.f("uq_clubs_club_id")),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=True),
        sa.Column("first_name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("status IN ('active', 'blocked')", name=op.f("ck_users_status_valid")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("telegram_id", name=op.f("uq_users_telegram_id")),
    )

    op.create_table(
        "poker_accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("club_id", sa.Integer(), nullable=False),
        sa.Column("player_id", sa.String(length=9), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("reject_reason", sa.String(length=500), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name=op.f("ck_poker_accounts_status_valid"),
        ),
        sa.CheckConstraint(
            "length(player_id) = 9", name=op.f("ck_poker_accounts_player_id_length")
        ),
        sa.CheckConstraint(
            "status <> 'rejected' OR reject_reason IS NOT NULL",
            name=op.f("ck_poker_accounts_reject_reason_required"),
        ),
        sa.ForeignKeyConstraint(
            ["club_id"], ["clubs.id"], name=op.f("fk_poker_accounts_club_id_clubs")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_poker_accounts_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_poker_accounts")),
        sa.UniqueConstraint("club_id", "player_id", name=op.f("uq_poker_accounts_club_player")),
        sa.UniqueConstraint("user_id", name=op.f("uq_poker_accounts_user_id")),
    )
    op.create_index(
        op.f("ix_poker_accounts_status"), "poker_accounts", ["status"], unique=False
    )

    # Клуб Altyn Crown (ТЗ §2): справочные данные, а не демонстрационные.
    op.bulk_insert(clubs, [{"club_id": "692609", "name": "Altyn Crown"}])


def downgrade() -> None:
    op.drop_index(op.f("ix_poker_accounts_status"), table_name="poker_accounts")
    op.drop_table("poker_accounts")
    op.drop_table("users")
    op.drop_table("clubs")
