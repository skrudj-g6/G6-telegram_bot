export function money(amount: number): string {
  return `${Math.trunc(amount).toLocaleString("ru-RU")} ₸`;
}

export function signed(amount: number): string {
  return `${amount > 0 ? "+" : ""}${Math.trunc(amount).toLocaleString("ru-RU")} ₸`;
}

export function dateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString("ru-RU", { dateStyle: "short", timeStyle: "medium" });
}

export function percent(value: string): string {
  const number = Number(value);
  if (!Number.isFinite(number)) return value;
  return `${number > 0 ? "+" : ""}${number}%`;
}

export const DEPOSIT_STATUS: Record<string, string> = {
  awaiting_receipt: "Ждёт чек",
  pending: "Новая",
  processing: "В работе",
  completed: "Выполнена",
  rejected: "Отклонена",
  cancelled: "Отменена игроком",
  expired: "Истекла",
};

export const WITHDRAWAL_STATUS: Record<string, string> = {
  pending: "Новая",
  processing: "В работе",
  completed: "Выполнена",
  rejected: "Отклонена",
  cancelled: "Отменена игроком",
};

export const ACCOUNT_STATUS: Record<string, string> = {
  pending: "Ждёт подтверждения",
  approved: "В клубе",
  rejected: "Отклонён",
};

export const ROLE: Record<string, string> = {
  owner: "Владелец",
  admin: "Администратор",
  operator: "Оператор",
  finance: "Финансы",
};

export const METHOD: Record<string, string> = { fiat: "Тенге", crypto: "USDT" };

const ERRORS: Record<string, string> = {
  invalid_credentials: "Неверный логин или пароль.",
  too_many_attempts: "Слишком много попыток входа. Подождите 15 минут.",
  invalid_refresh: "Сессия истекла. Войдите снова.",
  forbidden: "Недостаточно прав для этого действия.",
  request_not_found: "Заявка не найдена.",
  user_not_found: "Игрок не найден.",
  account_not_found: "У игрока нет игрового ID.",
  staff_not_found: "Сотрудник не найден.",
  invalid_transition: "Статус заявки уже изменился. Обновите список.",
  reason_required: "Укажите причину.",
  receipt_not_available: "Чек недоступен (не загружен или удалён по сроку хранения).",
  login_taken: "Такой логин уже занят.",
  weak_password: "Слишком простой пароль.",
  invalid_role: "Недопустимая роль.",
  invalid_staff_data: "Проверьте данные сотрудника.",
  cannot_modify_self: "Нельзя изменить собственную учётную запись.",
  last_owner: "Нельзя отключить последнего владельца.",
  bank_exists: "Такой банк уже есть.",
  bank_not_found: "Банк не найден.",
  invalid_bank_data: "Проверьте название банка.",
  invalid_setting: "Недопустимое значение настройки.",
  unknown_setting: "Неизвестная настройка.",
  invalid_limits: "Минимум не может быть больше максимума.",
  manual_rate_requires_manual_mode: "Ручной курс можно задать только в ручном режиме.",
  manual_rate_required: "Для ручного режима задайте курс.",
  validation_error: "Проверьте заполнение полей.",
  network_error: "Нет связи с сервером.",
};

export function errorText(code: string | undefined): string {
  if (!code) return "Что-то пошло не так.";
  if (code.startsWith("http_5")) return "Ошибка сервера. Попробуйте позже.";
  return ERRORS[code] ?? `Ошибка: ${code}`;
}

export interface SettingsView {
  [key: string]: unknown;
}

/** Оставляет в форме только изменённые значения: в API уходит минимум полей. */
export function changedFields(
  original: Record<string, string>,
  edited: Record<string, string>,
  integerKeys: readonly string[],
): Record<string, string | number> {
  const result: Record<string, string | number> = {};
  for (const [key, value] of Object.entries(edited)) {
    if (value.trim() === (original[key] ?? "")) continue;
    result[key] = integerKeys.includes(key) ? Number(value.trim()) : value.trim();
  }
  return result;
}
