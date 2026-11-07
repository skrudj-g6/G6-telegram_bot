import { useEffect, useState } from "react";

import { ErrorNote, Pager } from "../components/ui.tsx";
import type { PageData } from "../components/ui.tsx";
import { useLoad } from "../hooks.ts";
import { dateTime } from "../lib/format.ts";

interface AuditRow {
  id: number;
  staff_id: number | null;
  action: string;
  entity_type: string | null;
  entity_id: string | null;
  details: Record<string, unknown> | null;
  ip: string | null;
  created_at: string;
}

export function AuditPage() {
  const [action, setAction] = useState("");
  const [entityType, setEntityType] = useState("");
  const [staffId, setStaffId] = useState("");
  const [offset, setOffset] = useState(0);
  useEffect(() => setOffset(0), [action, entityType, staffId]);

  const params = new URLSearchParams({ limit: "50", offset: String(offset) });
  if (action.trim()) params.set("action", action.trim());
  if (entityType) params.set("entity_type", entityType);
  if (/^\d+$/.test(staffId.trim())) params.set("staff_id", staffId.trim());
  const list = useLoad<PageData<AuditRow>>(`/admin/v1/audit?${params}`);

  return (
    <section>
      <h1>Журнал действий</h1>
      <div className="toolbar">
        <input placeholder="Действие (например, deposit.complete)" value={action} onChange={(e) => setAction(e.target.value)} />
        <select value={entityType} onChange={(e) => setEntityType(e.target.value)} aria-label="Объект">
          <option value="">Любой объект</option>
          <option value="deposit">Пополнение</option>
          <option value="withdrawal">Вывод</option>
          <option value="poker_account">Игровой ID</option>
          <option value="user">Игрок</option>
          <option value="staff">Сотрудник</option>
        </select>
        <input placeholder="Сотрудник №" value={staffId} onChange={(e) => setStaffId(e.target.value)} />
      </div>
      <ErrorNote text={list.error} />
      <table>
        <thead><tr><th>Время</th><th>Сотрудник</th><th>Действие</th><th>Объект</th><th>Подробности</th><th>IP</th></tr></thead>
        <tbody>
          {list.data?.items.map((r) => (
            <tr key={r.id}>
              <td>{dateTime(r.created_at)}</td>
              <td>{r.staff_id ?? "—"}</td>
              <td>{r.action}</td>
              <td>{r.entity_type ? `${r.entity_type} №${r.entity_id ?? ""}` : "—"}</td>
              <td><code>{r.details ? JSON.stringify(r.details) : ""}</code></td>
              <td>{r.ip ?? "—"}</td>
            </tr>
          ))}
          {list.data && list.data.items.length === 0 && <tr><td colSpan={6} className="muted">Записей нет</td></tr>}
        </tbody>
      </table>
      {list.data && <Pager total={list.data.total} limit={list.data.limit} offset={list.data.offset} onChange={setOffset} />}
    </section>
  );
}
