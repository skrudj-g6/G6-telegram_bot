import { useEffect, useState } from "react";

import { useAuth } from "./auth.tsx";
import { ROLE } from "./lib/format.ts";
import { P } from "./lib/permissions.ts";
import { AuditPage } from "./pages/Audit.tsx";
import { LoginPage } from "./pages/Login.tsx";
import { PlayersPage } from "./pages/Players.tsx";
import { RequestsPage } from "./pages/Requests.tsx";
import { SettingsPage } from "./pages/Settings.tsx";
import { StaffPage } from "./pages/Staff.tsx";

const ROUTES = [
  { id: "requests", title: "Заявки", permission: P.REQUESTS_VIEW, view: RequestsPage },
  { id: "players", title: "Игроки", permission: P.PLAYERS_VIEW, view: PlayersPage },
  { id: "settings", title: "Настройки", permission: P.SETTINGS_VIEW, view: SettingsPage },
  { id: "staff", title: "Сотрудники", permission: P.STAFF_MANAGE, view: StaffPage },
  { id: "audit", title: "Аудит", permission: P.AUDIT_VIEW, view: AuditPage },
] as const;

function currentRoute(): string {
  return window.location.hash.replace(/^#\/?/, "").split("/")[0];
}

export function App() {
  const { staff, ready, can, logout } = useAuth();
  const [route, setRoute] = useState(currentRoute());

  useEffect(() => {
    const onChange = () => setRoute(currentRoute());
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);

  if (!ready) return <div className="center muted">Загрузка…</div>;
  if (!staff) return <LoginPage />;

  const allowed = ROUTES.filter((r) => can(r.permission));
  const active = allowed.find((r) => r.id === route) ?? allowed[0];
  const View = active?.view;

  return (
    <div className="shell">
      <nav>
        <strong className="brand">Altyn Crown</strong>
        {allowed.map((r) => (
          <a key={r.id} href={`#/${r.id}`} className={r.id === active?.id ? "active" : ""}>
            {r.title}
          </a>
        ))}
        <div className="spacer" />
        <div className="me">
          {staff.display_name}
          <small>{ROLE[staff.role] ?? staff.role}</small>
        </div>
        <button className="ghost" onClick={() => void logout()}>Выйти</button>
      </nav>
      <main>{View ? <View /> : <p className="muted">Для вашей роли нет доступных разделов.</p>}</main>
    </div>
  );
}
