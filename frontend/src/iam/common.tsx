import { t } from "../i18n";
import { type ReactNode, useEffect, useId, useRef } from "react";
import { X } from "lucide-react";
import { type QueryResult, type useCursor, PAGE_SIZE } from "./data";

export function Feedback({ message }: { message?: { text: string; error: boolean } }) {
  return message && <p className={message.error ? "enterprise-error" : "enterprise-notice"} role={message.error ? "alert" : "status"}>{t(message.text)}</p>;
}

export function QueryState<T>({ result, children }: { result: QueryResult<T>; children: (data: T) => ReactNode }) {
  if (result.error) return <p className="enterprise-error" role="alert">{t(result.error)}</p>;
  if (result.data === undefined) return <p className="enterprise-loading" role="status">{t("Loading…")}</p>;
  return children(result.data);
}

export function Page({ title, children }: { title: string; children: ReactNode }) {
  return <section className="iam-page"><h1>{title}</h1>{children}</section>;
}

export function Panel({ title, children }: { title: string; children: ReactNode }) {
  return <section className="panel iam-panel"><h2>{title}</h2>{children}</section>;
}

export function CollapsiblePanel({ title, children }: { title: string; children: ReactNode }) {
  return <details className="panel iam-panel collapsible-panel">
    <summary>{title}</summary>
    <div className="collapsible-content">{children}</div>
  </details>;
}

export function SelectId({ label, name, items, required = true, defaultValue }: {
  label: string;
  name: string;
  items: { id: number; name: string }[];
  required?: boolean;
  defaultValue?: number;
}) {
  return <label>{label}
    <select aria-label={label} name={name} required={required} defaultValue={defaultValue ?? ""}>
      <option value="">{required ? t("Select…") : t("None")}</option>
      {items.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
    </select>
  </label>;
}

export function Pagination({ cursor, rows }: {
  cursor: ReturnType<typeof useCursor>; rows: { id: number }[];
}) {
  const last = rows.at(-1);
  return <div className="iam-actions">
    {cursor.previous && <button className="secondary-button" onClick={cursor.previous}>{t("Previous page")}</button>}
    {last && rows.length === PAGE_SIZE && (
      <button className="secondary-button" onClick={() => cursor.next(last.id)}>{t("Next page")}</button>
    )}
  </div>;
}

export function SectionTabs<T extends string>({ items, active, change, label }: {
  items: readonly T[]; active: T; change: (item: T) => void; label: string;
}) {
  return <div className="enterprise-tabs" role="group" aria-label={t(label)}>
    {items.map(item => <button key={item} type="button" className="secondary-button" aria-pressed={active === item}
      onClick={() => change(item)}>{t(item)}</button>)}
  </div>;
}

export function DataTable<T>({ label, rows, columns, rowKey }: {
  label: string; rows: T[]; columns: { label: string; render: (row: T) => ReactNode }[]; rowKey: (row: T) => string | number;
}) {
  if (!rows.length) return <p>{t("No records.")}</p>;
  return <div className="data-table-wrap" role="region" aria-label={label} tabIndex={0}>
    <table className="data-table" aria-label={label}><thead><tr>{columns.map(column =>
      <th key={column.label} scope="col">{column.label}</th>)}</tr></thead>
      <tbody>{rows.map(row => <tr key={rowKey(row)}>{columns.map(column => <td key={column.label}>{column.render(row)}</td>)}</tr>)}</tbody>
    </table>
  </div>;
}

export function Drawer({ title, close, children }: { title: string; close: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  const id = useId();
  useEffect(() => {
    const dialog = ref.current;
    const focused = document.activeElement;
    dialog?.showModal();
    return () => {
      dialog?.close();
      if (focused instanceof HTMLElement && focused.isConnected) focused.focus();
    };
  }, []);
  return <dialog ref={ref} className="enterprise-drawer" aria-labelledby={id} onCancel={event => {
    event.preventDefault();
    close();
  }}>
    <header><h2 id={id}>{title}</h2><button type="button" className="icon-button" aria-label={t("Close details")}
      title={t("Close details")} onClick={close}><X size={20} aria-hidden="true" /></button></header>
    {children}
  </dialog>;
}

export function StatusBadge({ children }: { children: ReactNode }) {
  return <span className="status-badge">{children}</span>;
}
