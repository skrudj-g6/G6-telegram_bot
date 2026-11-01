"""Команды администратора сервера.

Первый Owner создаётся только здесь (в панели его создать некому):

    docker compose exec backend python -m app.cli create-staff --login owner --name "Иван" --role owner

Пароль запрашивается в терминале и в историю команд не попадает. Для автоматизации можно
передать его через переменную STAFF_PASSWORD.
"""

import argparse
import getpass
import os
import sys

from app.db.session import get_session_factory
from app.models import StaffRole
from app.services import staff
from app.services.errors import ServiceError

_MESSAGES = {
    "weak_password": "Пароль должен быть от 10 до 128 символов.",
    "login_taken": "Такой логин уже есть.",
    "invalid_staff_data": "Логин: 3–64 символа (a-z, 0-9, . _ -), имя: 1–100 символов.",
}


def _read_password() -> str:
    password = os.environ.get("STAFF_PASSWORD")
    if password:
        return password
    first = getpass.getpass("Пароль: ")
    if first != getpass.getpass("Повторите пароль: "):
        print("Пароли не совпадают.", file=sys.stderr)
        raise SystemExit(1)
    return first


def create_staff(args: argparse.Namespace) -> int:
    password = _read_password()
    try:
        with get_session_factory()() as db:
            created = staff.create_staff(
                db,
                actor=None,
                login=args.login,
                display_name=args.name,
                role=args.role,
                password=password,
            )
            print(f"Создан сотрудник {created.login} (роль {created.role}).")
    except ServiceError as exc:
        print(_MESSAGES.get(exc.code, f"Ошибка: {exc.code}"), file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create-staff", help="создать сотрудника (в том числе первого Owner)")
    create.add_argument("--login", required=True)
    create.add_argument("--name", required=True)
    create.add_argument("--role", required=True, choices=StaffRole.ALL)
    create.set_defaults(handler=create_staff)
    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
