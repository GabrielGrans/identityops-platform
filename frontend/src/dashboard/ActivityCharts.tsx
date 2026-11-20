import { useId, useState } from "react";
import { locale, t } from "../i18n";

export interface AccessActivity {
  available: boolean;
  month?: { grants: number; revocations: number };
  series?: { date: string; grants: number; revocations: number; succeeded: number; failed: number }[];
  groups?: { id: string; name: string | null; count: number }[];
}
const severityColors = ["#ed6256", "#e29860", "#dabd6c", "#a4adb8"];

export function ActivityRange({ days, change }: { days: string; change: (days: string) => void }) {
  return <label className="iam-form">{t("Activity window")}
    <select value={days} onChange={event => change(event.target.value)}>
      {["7", "30", "90"].map(day => <option key={day} value={day}>{t(`Last ${day} days`)}</option>)}
    </select>
  </label>;
}

export function AccessLine({ series }: { series: NonNullable<AccessActivity["series"]> }) {
  const [point, setPoint] = useState<number>();
  const title = useId();
  const maximum = Math.max(1, ...series.flatMap(row => [row.grants, row.revocations]));
  const x = (index: number) => 40 + 520 * index / Math.max(series.length - 1, 1);
  const y = (count: number) => 157 - 138 * count / maximum;
  const selected = point === undefined ? undefined : series[point];
  const date = (value: string) => new Date(value + "T00:00:00Z").toLocaleDateString(locale(), { timeZone: "UTC", month: "short", day: "numeric" });
  if (!series.some(row => row.grants || row.revocations)) return <p>{t("No verified access changes in this period.")}</p>;
  return <>
    <svg className="chart-line" viewBox="0 0 580 190" role="img" aria-labelledby={title}
      onPointerMove={event => {
        const bounds = event.currentTarget.getBoundingClientRect();
        const position = (event.clientX - bounds.left) * 580 / bounds.width;
        setPoint(Math.max(0, Math.min(series.length - 1, Math.round((position - 40) / 520 * (series.length - 1)))));
      }} onPointerLeave={() => setPoint(undefined)}>
      <title id={title}>{t("Confirmed grants and revocations over time")}</title>
      {[0, maximum].map(value => <g key={value}>
        <path d={`M40 ${y(value)} H560`} stroke="#474b54" />
        <text x="32" y={y(value) + 4} textAnchor="end" fill="#bcc1cb" fontSize="11">{value}</text>
      </g>)}
      <polyline points={series.map((row, index) => `${x(index)},${y(row.grants)}`).join(" ")} fill="none" stroke="#ee7367" strokeWidth="3" />
      <polyline points={series.map((row, index) => `${x(index)},${y(row.revocations)}`).join(" ")} fill="none" stroke="#a6c3bd" strokeWidth="3" strokeDasharray="6 3" />
      {selected && point !== undefined && <path d={`M${x(point)} 19 V157`} stroke="#d7d8dc" strokeDasharray="3 4" />}
      <text x="40" y="178" fill="#bcc1cb" fontSize="11">{date(series[0].date)}</text>
      <text x="560" y="178" textAnchor="end" fill="#bcc1cb" fontSize="11">{date(series[series.length - 1].date)}</text>
    </svg>
    <ul className="chart-legend"><li><i style={{ background: "#ee7367" }} />{t("Grants")}</li>
      <li><i style={{ background: "#a6c3bd" }} />{t("Revocations")}</li></ul>
    <label className="iam-form">{t("Inspect chart date")}
      <select value={point ?? ""} onChange={event => setPoint(event.target.value === "" ? undefined : Number(event.target.value))}>
        <option value="">{t("Select…")}</option>{series.map((row, index) => <option key={row.date} value={index}>{date(row.date)}</option>)}
      </select>
    </label>
    <p className="chart-readout" aria-live="polite">{selected && `${date(selected.date)} · ${t("Grants")} ${selected.grants} · ${t("Revocations")} ${selected.revocations}`}</p>
  </>;
}

export function Distribution({ rows, colors = severityColors }: { rows: [string, number][]; colors?: string[] }) {
  const total = rows.reduce((sum, [, count]) => sum + count, 0);
  let angle = 0;
  const stops = rows.map(([, count], index) => {
    const prior = angle;
    angle += total ? count / total * 100 : 0;
    return `${colors[index % colors.length]} ${prior}% ${angle}%`;
  });
  return <>
    <div className="chart-donut" aria-hidden="true" style={{ background: total ? `conic-gradient(${stops.join(",")})` : "#424650" }}><strong>{total}</strong></div>
    <ul className="chart-legend">{rows.map(([label, count], index) =>
      <li key={label}><i style={{ background: colors[index % colors.length] }} /><span>{label} <strong>{count}</strong></span></li>)}</ul>
  </>;
}

export function Bars({ rows }: { rows: [string, number][] }) {
  const max = Math.max(1, ...rows.map(([, count]) => count));
  if (!rows.length) return <p>{t("No records.")}</p>;
  return <ul className="chart-bars">{rows.map(([label, count], index) =>
    <li key={`${label}:${index}`}><span>{label}</span><strong>{count}</strong><meter aria-label={label} max={max} value={count} /></li>)}</ul>;
}
