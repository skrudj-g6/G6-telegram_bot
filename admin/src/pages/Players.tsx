import { useEffect, useState } from "react";

import { useAuth } from "../auth.tsx";
import { Badge, Dl, ErrorNote, Modal, Pager, statusTone } from "../components/ui.tsx";
import type { PageData } from "../components/ui.tsx";
import { useAction, useLoad } from "../hooks.ts";
import { ACCOUNT_STATUS, DEPOSIT_STATUS, WITHDRAWAL_STATUS, dateTime, money } from "../lib/format.ts";
import { P } from "../lib/permissions.ts";
import type { RequestRow } from "./Requests.tsx";

interface PlayerRef {
  user_id: number;
  telegram_id: number;
  username: string | null;
  first_name: string;
  user_status: string;
  player_id: string | null;
  account_status: string | null;
}
interface Detail {
  player: PlayerRef;
  block_reason: string | null;
  duplicate_id_attempts: number;
  reject_reason: string | null;
  registered_at: string;
  deposits: RequestRow[];
  withdrawals: RequestRow[];
}

export function PlayersPage() {
  const [accountStatus, setAccountStatus] = useState("");
  const [userStatus, setUserStatus] = useState("");
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [openId, setOpenId] = useState<number | null>(null);

  useEffect(() => {
    const t = setTimeout(() => setQuery(q.trim()), 300);
    return () => clearTimeout(t);
  }, [q]);
  useEffect(() => setOffset(0), [accountStatus, userStatus, query]);

  const params = new URLSearchParams({ limit: "50", offset: String(offset) });
  if (accountStatus) params.set("account_status", accountStatus);
  if (userStatus) params.set("user_status", userStatus);
  if (query) params.set("q", query);
  const list = useLoad<PageData<PlayerRef>>(`/admin/v1/players?${params}`);

  return (
    <section>
      <h1>Игроки</h1>
      <div className="toolbar">
        <select value={accountStatus} onChange={(e) => setAccountStatus(e.target.value)} aria-label="Статус игрового ID">
          <option value="">Любой статус ID</option>
          {Object.entries(ACCOUNT_STATUS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <select value={userStatus} onChange={(e) => setUserStatus(e.target.value)} aria-label="Доступ">
          <option value="">Любой доступ</option>
          <option value="active">Активные</option>
          <option value="blocked">Заблокированные</option>
        </select>
        <input placeholder="Поиск: ID, имя, @username, Telegram ID" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      <ErrorNote text={list.error} />
      <table>
        <thead><tr><th>Игрок</th><th>Telegram ID</th><th>ID в клубе</th><th>Игровой ID</th><th>Доступ</th></tr></thead>
        <tbody>
          {list.data?.items.map((p) => (
            <tr key={p.user_id} className="click" onClick={() => setOpenId(p.user_id)}>
              <td>{p.first_name}{p.username ? ` (@${p.username})` : ""}</td>
              <td>{p.telegram_id}</td>
              <td>{p.player_id ?? "—"}</td>
              <td>{p.account_status ? <Badge text={ACCOUNT_STATUS[p.account_status] ?? p.account_status} tone={statusTone(p.account_status)} /> : "—"}</td>
              <td><Badge text={p.user_status === "blocked" ? "Заблокирован" : "Активен"} tone={statusTone(p.user_status)} /></td>
            </tr>
          ))}
          {list.data && list.data.items.length === 0 && <tr><td colSpan={5} className="muted">Игроков нет</td></tr>}
        </tbody>
      </table>
      {list.data && <Pager total={list.data.total} limit={list.data.limit} offset={list.data.offset} onChange={setOffset} />}
      {openId !== null && <PlayerModal id={openId} onClose={() => setOpenId(null)} onChanged={list.reload} />}
    </section>
  );
}

function PlayerModal({ id, onClose, onChanged }: { id: number; onClose: () => void; onChanged: () => void }) {
  const { api, can } = useAuth();
  const detail = useLoad<Detail>(`/admin/v1/players/${id}`);
  const action = useAction();
  const [reason, setReason] = useState("");
  const [rejecting, setRejecting] = useState(false);
  const d = detail.data;

  const act = (name: string, body?: unknown) =>
    action.run(async () => {
      detail.setData(await api.request<Detail>("POST", `/admin/v1/players/${id}/${name}`, body));
      setRejecting(false);
      setReason("");
      onChanged();
    });

  const moderate = can(P.PLAYERS_MODERATE);
  return (
    <Modal title={d ? d.player.first_name : "Игрок"} onClose={onClose}>
      <ErrorNote text={detail.error ?? action.error} />
      {d && (
        <>
          <Dl rows={[
            ["Telegram", `${d.player.telegram_id}${d.player.username ? ` · @${d.player.username}` : ""}`],
            ["ID в клубе", d.player.player_id],
            ["Игровой ID", d.player.account_status ? ACCOUNT_STATUS[d.player.account_status] ?? d.player.account_status : null],
            ["Доступ", d.player.user_status === "blocked" ? "Заблокирован" : "Активен"],
            ["Причина блокировки", d.block_reason],
            ["Попыток с занятым ID", d.duplicate_id_attempts],
            ["Причина отказа по ID", d.reject_reason],
            ["Зарегистрирован", dateTime(d.registered_at)],
          ]} />
          {moderate && (
            <div className="actions">
              {d.player.account_status === "pending" && (
                <>
                  <button className="primary" disabled={action.busy} onClick={() => void act("approve")}>Принять в клуб</button>
                  <button className="danger" disabled={action.busy} onClick={() => setRejecting(true)}>Отклонить…</button>
                </>
              )}
              {d.player.user_status === "blocked" && (
                <button disabled={action.busy} onClick={() => {
                  if (window.confirm("Разблокировать игрока?")) void act("unblock");
                }}>Разблокировать</button>
              )}
            </div>
          )}
          {rejecting && (
            <div className="reject">
              <textarea placeholder="Причина (её увидит игрок)" maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} />
              <button className="danger" disabled={action.busy || !reason.trim()} onClick={() => void act("reject", { reason: reason.trim() })}>Отклонить ID</button>
            </div>
          )}
          <h3>Пополнения</h3>
          <MiniTable rows={d.deposits} labels={DEPOSIT_STATUS} />
          <h3>Выводы</h3>
          <MiniTable rows={d.withdrawals} labels={WITHDRAWAL_STATUS} />
        </>
      )}
    </Modal>
  );
}

function MiniTable({ rows, labels }: { rows: RequestRow[]; labels: Record<string, string> }) {
  if (rows.length === 0) return <p className="muted">Нет заявок</p>;
  return (
    <table>
      <tbody>
        {rows.map((r) => (
          <tr key={r.id}>
            <td>№{r.id}</td><td>{dateTime(r.created_at)}</td><td>{money(r.amount)}</td>
            <td><Badge text={labels[r.status] ?? r.status} tone={statusTone(r.status)} /></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
