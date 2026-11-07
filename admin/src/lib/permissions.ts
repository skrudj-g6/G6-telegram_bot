export const P = {
  PLAYERS_VIEW: "players.view",
  PLAYERS_MODERATE: "players.moderate",
  REQUESTS_VIEW: "requests.view",
  REQUESTS_PROCESS: "requests.process",
  RECEIPTS_VIEW: "receipts.view",
  SETTINGS_VIEW: "settings.view",
  SETTINGS_EDIT: "settings.edit",
  STAFF_MANAGE: "staff.manage",
  AUDIT_VIEW: "audit.view",
} as const;

/** Кого может создавать/менять сотрудник данной роли (зеркало backend, окончательно решает сервер). */
export function manageableRoles(role: string): string[] {
  if (role === "owner") return ["owner", "admin", "operator", "finance"];
  if (role === "admin") return ["operator", "finance"];
  return [];
}
