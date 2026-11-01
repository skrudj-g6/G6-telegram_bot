"""Права ролей (Q-10). Матрица в коде: её нельзя изменить из панели и забыть в миграции.

Owner и Admin видят всё и модерируют. Operator работает с заявками и видит реквизиты и
чеки. Finance только смотрит заявки и чеки (допущение, Q-40). Admin не управляет Owner'ами и
другими Admin'ами (Q-25, Q-41).
"""

from app.models import StaffRole

PLAYERS_VIEW = "players.view"
PLAYERS_MODERATE = "players.moderate"  # подтвердить/отклонить игрока, разблокировать
REQUESTS_VIEW = "requests.view"  # заявки на пополнение и вывод вместе с реквизитами
REQUESTS_PROCESS = "requests.process"  # взять в работу, выполнить, отклонить
RECEIPTS_VIEW = "receipts.view"
SETTINGS_VIEW = "settings.view"
SETTINGS_EDIT = "settings.edit"  # лимиты, проценты, курс, банки
STAFF_MANAGE = "staff.manage"
AUDIT_VIEW = "audit.view"

_ALL = {
    PLAYERS_VIEW,
    PLAYERS_MODERATE,
    REQUESTS_VIEW,
    REQUESTS_PROCESS,
    RECEIPTS_VIEW,
    SETTINGS_VIEW,
    SETTINGS_EDIT,
    STAFF_MANAGE,
    AUDIT_VIEW,
}

PERMISSIONS: dict[str, frozenset[str]] = {
    StaffRole.OWNER: frozenset(_ALL),
    StaffRole.ADMIN: frozenset(_ALL),
    StaffRole.OPERATOR: frozenset({PLAYERS_VIEW, REQUESTS_VIEW, REQUESTS_PROCESS, RECEIPTS_VIEW}),
    StaffRole.FINANCE: frozenset({PLAYERS_VIEW, REQUESTS_VIEW, RECEIPTS_VIEW}),
}

# Кем кто может управлять (создание, смена роли, отключение, сброс пароля).
MANAGEABLE_ROLES: dict[str, frozenset[str]] = {
    StaffRole.OWNER: frozenset(StaffRole.ALL),
    StaffRole.ADMIN: frozenset({StaffRole.OPERATOR, StaffRole.FINANCE}),
}


def has_permission(role: str, permission: str) -> bool:
    return permission in PERMISSIONS.get(role, frozenset())


def can_manage_role(actor_role: str, target_role: str) -> bool:
    return target_role in MANAGEABLE_ROLES.get(actor_role, frozenset())
