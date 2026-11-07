import type { ReactNode } from "react";

export function Badge({ text, tone }: { text: string; tone?: "ok" | "bad" | "warn" | "info" | "muted" }) {
  return <span className={`badge ${tone ?? "muted"}`}>{text}</span>;
}

export function statusTone(status: string): "ok" | "bad" | "warn" | "info" | "muted" {
  if (status === "completed" || status === "approved" || status === "active") return "ok";
  if (status === "rejected" || status === "blocked") return "bad";
  if (status === "processing") return "info";
  if (status === "pending" || status === "awaiting_receipt") return "warn";
  return "muted";
}

export function ErrorNote({ text }: { text: string | null }) {
  return text ? <div className="error" role="alert">{text}</div> : null;
}

export function Pager(props: { total: number; limit: number; offset: number; onChange: (offset: number) => void }) {
  const { total, limit, offset, onChange } = props;
  const from = total === 0 ? 0 : offset + 1;
  return (
    <div className="pager">
      <button disabled={offset <= 0} onClick={() => onChange(Math.max(0, offset - limit))}>← Назад</button>
      <span>{from}–{Math.min(offset + limit, total)} из {total}</span>
      <button disabled={offset + limit >= total} onClick={() => onChange(offset + limit)}>Вперёд →</button>
    </div>
  );
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
    </label>
  );
}

export function Dl({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <dl className="dl">
      {rows.map(([k, v]) => (
        <div key={k}>
          <dt>{k}</dt>
          <dd>{v ?? "—"}</dd>
        </div>
      ))}
    </dl>
  );
}

export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  return (
    <div className="overlay" onClick={onClose}>
      <div className="modal" role="dialog" aria-label={title} onClick={(e) => e.stopPropagation()}>
        <header>
          <h2>{title}</h2>
          <button className="ghost" onClick={onClose} aria-label="Закрыть">✕</button>
        </header>
        {children}
      </div>
    </div>
  );
}

export interface PageData<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}
