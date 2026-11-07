import { useEffect, useState } from "react";

import { useAuth } from "../auth.tsx";
import { Dl, ErrorNote, Field } from "../components/ui.tsx";
import { useAction, useLoad } from "../hooks.ts";
import { changedFields, dateTime } from "../lib/format.ts";
import { P } from "../lib/permissions.ts";

const INT_FIELDS: [string, string][] = [
  ["deposit_min_amount", "Пополнение: минимум, ₸"],
  ["deposit_max_amount", "Пополнение: максимум, ₸"],
  ["withdrawal_min_amount", "Вывод: минимум, ₸"],
  ["withdrawal_max_amount", "Вывод: максимум, ₸"],
  ["deposit_receipt_timeout_minutes", "Время на отправку чека, мин"],
  ["receipt_retention_days", "Хранение чеков, дней"],
  ["usdt_rate_max_age_minutes", "Курс USDT устаревает через, мин"],
];
const PERCENT_FIELDS: [string, string][] = [
  ["deposit_commission_percent", "Процент клуба на пополнение (+ бонус фишками, − комиссия)"],
  ["withdrawal_commission_percent", "Процент клуба на вывод (+ бонус к выплате, − комиссия)"],
];
const INT_KEYS = INT_FIELDS.map(([k]) => k);
const FORM_KEYS = [...INT_KEYS, ...PERCENT_FIELDS.map(([k]) => k), "usdt_rate_mode"];

interface RateState { current: string | null; source: string | null; updated_at: string | null; usable: string | null }
type SettingsView = Record<string, unknown> & { usdt_rate: RateState };
interface BankRow { id: number; name: string; is_active: boolean; sort_order: number }

export function SettingsPage() {
  const { can } = useAuth();
  const editable = can(P.SETTINGS_EDIT);
  return (
    <section>
      <h1>Настройки</h1>
      <SettingsForm editable={editable} />
      <BanksBlock editable={editable} />
    </section>
  );
}

function SettingsForm({ editable }: { editable: boolean }) {
  const { api } = useAuth();
  const view = useLoad<SettingsView>("/admin/v1/settings");
  const action = useAction();
  const [form, setForm] = useState<Record<string, string>>({});
  const [manualRate, setManualRate] = useState("");
  const [saved, setSaved] = useState(false);

  const original: Record<string, string> = {};
  if (view.data) for (const k of FORM_KEYS) original[k] = String(view.data[k] ?? "");
  useEffect(() => {
    if (view.data) setForm({ ...original });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view.data]);

  if (!view.data) return <ErrorNote text={view.error} />;
  const set = (key: string, value: string) => { setSaved(false); setForm((f) => ({ ...f, [key]: value })); };

  const save = () =>
    action.run(async () => {
      const changes: Record<string, string | number> = changedFields(original, form, INT_KEYS);
      if (manualRate.trim()) changes.usdt_manual_rate = manualRate.trim();
      if (Object.keys(changes).length === 0) return;
      view.setData(await api.request<SettingsView>("PUT", "/admin/v1/settings", { settings: changes }));
      setManualRate("");
      setSaved(true);
    });

  const rate = view.data.usdt_rate;
  const manual = (form.usdt_rate_mode ?? original.usdt_rate_mode) === "manual";
  return (
    <div className="card">
      <h2>Лимиты и проценты</h2>
      <div className="grid">
        {INT_FIELDS.map(([key, label]) => (
          <Field key={key} label={label}>
            <input inputMode="numeric" disabled={!editable} value={form[key] ?? ""} onChange={(e) => set(key, e.target.value)} />
          </Field>
        ))}
        {PERCENT_FIELDS.map(([key, label]) => (
          <Field key={key} label={label}>
            <input inputMode="decimal" disabled={!editable} value={form[key] ?? ""} onChange={(e) => set(key, e.target.value)} />
          </Field>
        ))}
      </div>
      <h2>Курс USDT</h2>
      <Dl rows={[
        ["Текущий курс", rate.current ? `${rate.current} ₸` : null],
        ["Источник", rate.source],
        ["Обновлён", rate.updated_at ? dateTime(rate.updated_at) : null],
        ["Пополнение USDT", rate.usable ? "доступно" : "недоступно: курса нет или он устарел"],
      ]} />
      <div className="grid">
        <Field label="Режим курса">
          <select disabled={!editable} value={form.usdt_rate_mode ?? ""} onChange={(e) => set("usdt_rate_mode", e.target.value)}>
            <option value="auto">Автоматически (CoinGecko)</option>
            <option value="manual">Вручную</option>
          </select>
        </Field>
        {manual && (
          <Field label="Новый ручной курс, ₸ за 1 USDT">
            <input inputMode="decimal" disabled={!editable} value={manualRate} onChange={(e) => { setSaved(false); setManualRate(e.target.value); }} />
          </Field>
        )}
      </div>
      <ErrorNote text={action.error} />
      {editable && (
        <div className="actions">
          <button className="primary" disabled={action.busy} onClick={() => void save()}>Сохранить</button>
          {saved && <span className="ok">Сохранено</span>}
        </div>
      )}
    </div>
  );
}

function BanksBlock({ editable }: { editable: boolean }) {
  const { api } = useAuth();
  const banks = useLoad<BankRow[]>("/admin/v1/banks");
  const action = useAction();
  const [name, setName] = useState("");

  const patch = (id: number, body: Partial<BankRow>) =>
    action.run(async () => { await api.request("PATCH", `/admin/v1/banks/${id}`, body); banks.reload(); });
  const add = () =>
    action.run(async () => { await api.request("POST", "/admin/v1/banks", { name: name.trim() }); setName(""); banks.reload(); });

  return (
    <div className="card">
      <h2>Банки для вывода</h2>
      <ErrorNote text={banks.error ?? action.error} />
      <table>
        <thead><tr><th>Порядок</th><th>Название</th><th>Показывать игрокам</th></tr></thead>
        <tbody>
          {banks.data?.map((b) => (
            <tr key={b.id}>
              <td><SortInput value={b.sort_order} disabled={!editable || action.busy} onCommit={(v) => void patch(b.id, { sort_order: v })} /></td>
              <td><NameInput value={b.name} disabled={!editable || action.busy} onCommit={(v) => void patch(b.id, { name: v })} /></td>
              <td><input type="checkbox" checked={b.is_active} disabled={!editable || action.busy} onChange={(e) => void patch(b.id, { is_active: e.target.checked })} /></td>
            </tr>
          ))}
        </tbody>
      </table>
      {editable && (
        <div className="toolbar">
          <input placeholder="Новый банк" maxLength={100} value={name} onChange={(e) => setName(e.target.value)} />
          <button disabled={action.busy || !name.trim()} onClick={() => void add()}>Добавить</button>
        </div>
      )}
    </div>
  );
}

function NameInput({ value, disabled, onCommit }: { value: string; disabled: boolean; onCommit: (v: string) => void }) {
  const [text, setText] = useState(value);
  useEffect(() => setText(value), [value]);
  return <input value={text} disabled={disabled} maxLength={100} onChange={(e) => setText(e.target.value)}
    onBlur={() => { if (text.trim() && text.trim() !== value) onCommit(text.trim()); else setText(value); }} />;
}

function SortInput({ value, disabled, onCommit }: { value: number; disabled: boolean; onCommit: (v: number) => void }) {
  const [text, setText] = useState(String(value));
  useEffect(() => setText(String(value)), [value]);
  return <input className="narrow" inputMode="numeric" value={text} disabled={disabled} onChange={(e) => setText(e.target.value)}
    onBlur={() => { const n = Number(text); if (Number.isInteger(n) && n >= 0 && n !== value) onCommit(n); else setText(String(value)); }} />;
}
