import { useEffect, useState } from "react";

import { useAuth } from "../auth.tsx";
import { Badge, Dl, ErrorNote, Modal, Pager, statusTone } from "../components/ui.tsx";
import type { PageData } from "../components/ui.tsx";
import { messageOf, useAction, useLoad } from "../hooks.ts";
import {
  DEPOSIT_STATUS, METHOD, WITHDRAWAL_STATUS, dateTime, money, percent, signed,
} from "../lib/format.ts";
import { P } from "../lib/permissions.ts";

type Kind = "deposits" | "withdrawals";

interface Player {
  user_id: number;
  telegram_id: number;
  username: string | null;
  first_name: string;
  player_id: string | null;
}
interface HistoryItem {
  from_status: string | null;
  to_status: string;
  actor_type: string;
  actor_id: number | null;
  comment: string | null;
  created_at: string;
}
export interface RequestRow {
  id: number;
  status: string;
  method: string;
  amount: number;
  commission_percent: string;
  commission_amount: number;
  credit_amount?: number;
  payout_amount?: number;
  usdt_amount?: string | null;
  exchange_rate?: string | null;
  holder_name?: string | null;
  bank_name?: string | null;
  payment_details: Record<string, unknown> | null;
  player: Player;
  assigned_staff_id: number | null;
  reject_reason: string | null;
  receipt?: { available: boolean; uploaded_at: string | null; content_type: string | null; size: number | null };
  expires_at?: string;
  created_at: string;
  updated_at: string;
  history?: HistoryItem[] | null;
}

const LABELS: Record<Kind, Record<string, string>> = { deposits: DEPOSIT_STATUS, withdrawals: WITHDRAWAL_STATUS };

export function playerName(p: Player): string {
  return `${p.first_name}${p.username ? ` (@${p.username})` : ""}`;
}

export function RequestsPage() {
  const [kind, setKind] = useState<Kind>("deposits");
  const [status, setStatus] = useState("");
  const [method, setMethod] = useState("");
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [oldest, setOldest] = useState(true);
  const [offset, setOffset] = useState(0);
  const [openId, setOpenId] = useState<number | null>(null);

  useEffect(() => {
    const t = setTimeout(() => setQuery(q.trim()), 300);
    return () => clearTimeout(t);
  }, [q]);
  useEffect(() => setOffset(0), [kind, status, method, query, oldest]);

  const params = new URLSearchParams({ limit: "50", offset: String(offset) });
  if (status) params.set("status", status);
  if (method) params.set("method", method);
  if (query) params.set("q", query);
  if (oldest) params.set("oldest_first", "true");
  const list = useLoad<PageData<RequestRow>>(`/admin/v1/${kind}?${params}`);

  // Новые заявки появляются без ручного обновления страницы.
  const { reload } = list;
  useEffect(() => {
    const t = setInterval(reload, 15000);
    return () => clearInterval(t);
  }, [reload]);

  const labels = LABELS[kind];
  return (
    <section>
      <h1>Заявки</h1>
      <div className="toolbar">
        <div className="tabs">
          {(["deposits", "withdrawals"] as Kind[]).map((k) => (
            <button key={k} className={k === kind ? "active" : ""} onClick={() => { setKind(k); setStatus(""); }}>
              {k === "deposits" ? "Пополнения" : "Выводы"}
            </button>
          ))}
        </div>
        <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Статус">
          <option value="">Все статусы</option>
          {Object.entries(labels).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <select value={method} onChange={(e) => setMethod(e.target.value)} aria-label="Способ">
          <option value="">Любой способ</option>
          <option value="fiat">Тенге</option>
          <option value="crypto">USDT</option>
        </select>
        <input placeholder="Поиск: ID игрока, имя, @username, №" value={q} onChange={(e) => setQ(e.target.value)} />
        <label className="check"><input type="checkbox" checked={oldest} onChange={(e) => setOldest(e.target.checked)} /> Сначала старые</label>
      </div>
      <ErrorNote text={list.error} />
      <table>
        <thead>
          <tr><th>№</th><th>Создана</th><th>Игрок</th><th>ID в клубе</th><th>Способ</th><th>Сумма</th><th>К {kind === "deposits" ? "зачислению" : "выплате"}</th><th>Статус</th></tr>
        </thead>
        <tbody>
          {list.data?.items.map((r) => (
            <tr key={r.id} className="click" onClick={() => setOpenId(r.id)}>
              <td>{r.id}</td>
              <td>{dateTime(r.created_at)}</td>
              <td>{playerName(r.player)}</td>
              <td>{r.player.player_id ?? "—"}</td>
              <td>{METHOD[r.method] ?? r.method}</td>
              <td>{money(r.amount)}</td>
              <td>{money((kind === "deposits" ? r.credit_amount : r.payout_amount) ?? r.amount)}</td>
              <td><Badge text={labels[r.status] ?? r.status} tone={statusTone(r.status)} /></td>
            </tr>
          ))}
          {list.data && list.data.items.length === 0 && <tr><td colSpan={8} className="muted">Заявок нет</td></tr>}
        </tbody>
      </table>
      {list.data && <Pager total={list.data.total} limit={list.data.limit} offset={list.data.offset} onChange={setOffset} />}
      {openId !== null && (
        <RequestModal kind={kind} id={openId} onClose={() => setOpenId(null)} onChanged={list.reload} />
      )}
    </section>
  );
}

function RequestModal({ kind, id, onClose, onChanged }: { kind: Kind; id: number; onClose: () => void; onChanged: () => void }) {
  const { can, api, staff } = useAuth();
  const item = useLoad<RequestRow>(`/admin/v1/${kind}/${id}`);
  const action = useAction();
  const [reason, setReason] = useState("");
  const [rejecting, setRejecting] = useState(false);
  const row = item.data;
  const labels = LABELS[kind];

  const act = (name: string, body?: unknown) =>
    action.run(async () => {
      const updated = await api.request<RequestRow>("POST", `/admin/v1/${kind}/${id}/${name}`, body);
      item.setData(updated);
      setRejecting(false);
      setReason("");
      onChanged();
    });

  const canProcess = can(P.REQUESTS_PROCESS);
  return (
    <Modal title={`${kind === "deposits" ? "Пополнение" : "Вывод"} №${id}`} onClose={onClose}>
      <ErrorNote text={item.error ?? action.error} />
      {!row && !item.error && <p className="muted">Загрузка…</p>}
      {row && (
        <>
          <div className="row"><Badge text={labels[row.status] ?? row.status} tone={statusTone(row.status)} />
            {row.assigned_staff_id !== null && <span className="muted">
              Взял в работу: {row.assigned_staff_id === staff?.id ? "вы" : `сотрудник №${row.assigned_staff_id}`}</span>}
          </div>
          <Dl rows={[
            ["Игрок", playerName(row.player)],
            ["Telegram ID", row.player.telegram_id],
            ["ID в клубе", row.player.player_id],
            ["Способ", METHOD[row.method] ?? row.method],
            ["Сумма", money(row.amount)],
            ...(row.usdt_amount ? [["USDT", `${row.usdt_amount} по курсу ${row.exchange_rate}`] as [string, string]] : []),
            ["Процент клуба", percent(row.commission_percent)],
            ["Бонус / комиссия", signed(row.commission_amount)],
            [kind === "deposits" ? "К зачислению на игровой счёт" : "К выплате игроку",
              money((kind === "deposits" ? row.credit_amount : row.payout_amount) ?? row.amount)],
            ...(kind === "withdrawals" ? [
              ["Получатель", row.holder_name] as [string, string | null | undefined],
              ["Банк", row.bank_name] as [string, string | null | undefined],
            ] : []),
            ["Реквизиты", row.payment_details ? <pre>{JSON.stringify(row.payment_details, null, 2)}</pre> : null],
            ["Создана", dateTime(row.created_at)],
            ...(row.expires_at ? [["Срок", dateTime(row.expires_at)] as [string, string]] : []),
            ["Причина отказа", row.reject_reason],
          ]} />
          {kind === "deposits" && row.receipt && can(P.RECEIPTS_VIEW) && <Receipt id={id} info={row.receipt} />}
          {canProcess && (
            <div className="actions">
              {row.status === "pending" && <button className="primary" disabled={action.busy} onClick={() => void act("take")}>Взять в работу</button>}
              {row.status === "processing" && (
                <>
                  <button className="primary" disabled={action.busy} onClick={() => {
                    if (window.confirm("Подтвердить выполнение? Игрок получит уведомление.")) void act("complete");
                  }}>Выполнено</button>
                  <button disabled={action.busy} onClick={() => void act("release")}>Вернуть в очередь</button>
                  <button className="danger" disabled={action.busy} onClick={() => setRejecting(true)}>Отклонить…</button>
                </>
              )}
            </div>
          )}
          {rejecting && (
            <div className="reject">
              <textarea placeholder="Причина (её увидит игрок)" maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} />
              <button className="danger" disabled={action.busy || !reason.trim()} onClick={() => void act("reject", { reason: reason.trim() })}>Отклонить заявку</button>
            </div>
          )}
          {row.history && row.history.length > 0 && (
            <>
              <h3>История</h3>
              <ul className="history">
                {row.history.map((h, i) => (
                  <li key={i}>
                    <span className="muted">{dateTime(h.created_at)}</span>{" "}
                    {h.from_status ? `${labels[h.from_status] ?? h.from_status} → ` : ""}{labels[h.to_status] ?? h.to_status}
                    {h.actor_type === "staff" && h.actor_id ? ` · сотрудник №${h.actor_id}` : h.actor_type !== "staff" ? ` · ${h.actor_type}` : ""}
                    {h.comment ? ` — ${h.comment}` : ""}
                  </li>
                ))}
              </ul>
            </>
          )}
        </>
      )}
    </Modal>
  );
}

function Receipt({ id, info }: { id: number; info: NonNullable<RequestRow["receipt"]> }) {
  const { api } = useAuth();
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Чек запрашивается только по нажатию: каждый просмотр пишется в аудит.
  const show = async () => {
    try {
      const blob = await api.blob(`/admin/v1/deposits/${id}/receipt`);
      setUrl(URL.createObjectURL(blob));
    } catch (e) {
      setError(messageOf(e));
    }
  };
  useEffect(() => () => { if (url) URL.revokeObjectURL(url); }, [url]);

  if (!info.available) return <p className="muted">Чек: не загружен или удалён по сроку хранения.</p>;
  return (
    <div className="receipt">
      <h3>Чек</h3>
      <ErrorNote text={error} />
      {!url && <button onClick={() => void show()}>Показать чек</button>}
      {url && (info.content_type === "application/pdf"
        ? <iframe src={url} title="Чек" />
        : <img src={url} alt="Чек об оплате" />)}
    </div>
  );
}
