import { useState } from "react";

import { useAuth } from "../auth.tsx";
import { Badge, ErrorNote, Field, Modal } from "../components/ui.tsx";
import { useAction, useLoad } from "../hooks.ts";
import { ROLE, dateTime } from "../lib/format.ts";
import type { Staff } from "../lib/api.ts";
import { manageableRoles } from "../lib/permissions.ts";

export function StaffPage() {
  const { api, staff: me } = useAuth();
  const list = useLoad<Staff[]>("/admin/v1/staff");
  const action = useAction();
  const [creating, setCreating] = useState(false);
  const [resetFor, setResetFor] = useState<Staff | null>(null);
  const roles = manageableRoles(me?.role ?? "");

  const patch = (s: Staff, body: Record<string, unknown>) =>
    action.run(async () => { await api.request("PATCH", `/admin/v1/staff/${s.id}`, body); list.reload(); });

  return (
    <section>
      <h1>Сотрудники</h1>
      <div className="toolbar"><button className="primary" onClick={() => setCreating(true)}>Добавить сотрудника</button></div>
      <ErrorNote text={list.error ?? action.error} />
      <table>
        <thead><tr><th>Логин</th><th>Имя</th><th>Роль</th><th>Последний вход</th><th>Статус</th><th /></tr></thead>
        <tbody>
          {list.data?.map((s) => {
            const manageable = s.id !== me?.id && roles.includes(s.role);
            return (
              <tr key={s.id}>
                <td>{s.login}</td><td>{s.display_name}</td><td>{ROLE[s.role] ?? s.role}</td>
                <td>{dateTime(s.last_login_at)}</td>
                <td><Badge text={s.is_active ? "Активен" : "Отключён"} tone={s.is_active ? "ok" : "bad"} /></td>
                <td className="right">
                  {manageable && (
                    <>
                      <select aria-label="Роль" value={s.role} disabled={action.busy} onChange={(e) => void patch(s, { role: e.target.value })}>
                        {roles.map((r) => <option key={r} value={r}>{ROLE[r]}</option>)}
                      </select>{" "}
                      <button disabled={action.busy} onClick={() => void patch(s, { is_active: !s.is_active })}>{s.is_active ? "Отключить" : "Включить"}</button>{" "}
                      <button disabled={action.busy} onClick={() => setResetFor(s)}>Сбросить пароль</button>
                    </>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {creating && <CreateModal roles={roles} onClose={() => setCreating(false)} onDone={() => { setCreating(false); list.reload(); }} />}
      {resetFor && <ResetModal staff={resetFor} onClose={() => setResetFor(null)} />}
    </section>
  );
}

function CreateModal({ roles, onClose, onDone }: { roles: string[]; onClose: () => void; onDone: () => void }) {
  const { api } = useAuth();
  const action = useAction();
  const [form, setForm] = useState({ login: "", display_name: "", role: roles[roles.length - 1] ?? "operator", password: "" });
  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }));
  const submit = () => action.run(async () => {
    await api.request("POST", "/admin/v1/staff", { ...form, login: form.login.trim(), display_name: form.display_name.trim() });
    onDone();
  });
  return (
    <Modal title="Новый сотрудник" onClose={onClose}>
      <Field label="Логин"><input value={form.login} onChange={(e) => set("login", e.target.value)} autoComplete="off" /></Field>
      <Field label="Имя"><input value={form.display_name} onChange={(e) => set("display_name", e.target.value)} /></Field>
      <Field label="Роль">
        <select value={form.role} onChange={(e) => set("role", e.target.value)}>
          {roles.map((r) => <option key={r} value={r}>{ROLE[r]}</option>)}
        </select>
      </Field>
      <Field label="Пароль (передайте сотруднику лично)"><input type="password" autoComplete="new-password" value={form.password} onChange={(e) => set("password", e.target.value)} /></Field>
      <ErrorNote text={action.error} />
      <button className="primary" disabled={action.busy || !form.login.trim() || !form.display_name.trim() || !form.password} onClick={() => void submit()}>Создать</button>
    </Modal>
  );
}

function ResetModal({ staff, onClose }: { staff: Staff; onClose: () => void }) {
  const { api } = useAuth();
  const action = useAction();
  const [password, setPassword] = useState("");
  const [done, setDone] = useState(false);
  const submit = () => action.run(async () => {
    await api.request("POST", `/admin/v1/staff/${staff.id}/reset-password`, { new_password: password });
    setDone(true);
  });
  return (
    <Modal title={`Новый пароль: ${staff.login}`} onClose={onClose}>
      {done ? <p className="ok">Пароль изменён, все сеансы сотрудника завершены.</p> : (
        <>
          <Field label="Новый пароль"><input type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} /></Field>
          <ErrorNote text={action.error} />
          <button className="primary" disabled={action.busy || !password} onClick={() => void submit()}>Сменить пароль</button>
        </>
      )}
    </Modal>
  );
}
