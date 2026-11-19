import { t } from "../i18n";
import { type ReactNode } from "react";
import { type QueryResult, type useCursor, PAGE_SIZE } from "./data";

export function Feedback({ message }: { message?: { text: string; error: boolean } }) {
  return message && <p role={message.error ? "alert" : "status"}>{t(message.text)}</p>;
}

export function QueryState<T>({ result, children }: { result: QueryResult<T>; children: (data: T) => ReactNode }) {
  if (result.error) return <p role="alert">{t(result.error)}</p>;
  if (result.data === undefined) return <p role="status">{t("Loading…")}</p>;
  return children(result.data);
}

export function Page({ title, children }: { title: string; children: ReactNode }) {
  return <section className="iam-page"><h1>{title}</h1>{children}</section>;
}

export function Panel({ title, children }: { title: string; children: ReactNode }) {
  return <section className="panel iam-panel"><h2>{title}</h2>{children}</section>;
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
