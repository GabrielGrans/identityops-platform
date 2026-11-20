import { useState } from "react";
import { ArrowDownToLine, ArrowUpFromLine, ShieldAlert, Users } from "lucide-react";
import { t } from "../i18n";
import { Page, Panel, QueryState } from "../iam/common";
import { useQuery, type QueryResult } from "../iam/data";
import { type Certification } from "../iam/CertificationMetrics";
import { AccessLine, ActivityRange, Distribution, type AccessActivity } from "./ActivityCharts";

export interface Metrics {
  local_employees?: number; local_groups?: number; official_departments?: number; local_unassigned?: number;
  entra?: { users?: number; groups?: number; unassigned?: number; last_success: string | null; health: string; stale?: boolean;
    identity_status?: Record<string, number> };
  pending_local?: number; pending_entra?: number; provisioning_active?: number; provisioning_failed?: number;
  findings?: Record<string, number>; certification?: Certification;
}
export type Navigate = (page: string, source?: "local" | "entra") => void;

export function OperationsDashboard({ token, navigate, metrics }: { token: string; navigate: Navigate; metrics: QueryResult<Metrics> }) {
  const [days, setDays] = useState("30");
  const activity = useQuery<AccessActivity>(token, `/v1/dashboard/access-activity?days=${days}`);
  return <Page title={t("IAM Governance Dashboard")}>
    <p className="executive-subtitle">{t("Monitor directory health, access risks and decisions awaiting action.")}</p>
    <QueryState result={metrics}>{data => {
      const { entra, findings } = data;
      const approvals = [data.pending_local, data.pending_entra].filter(value => value !== undefined);
      const risks = findings && Object.values(findings).reduce((total, count) => total + count, 0);
      const priorities = [
        { label: "Critical findings", count: findings?.critical, page: "Alerts & Findings" },
        { label: "Pending approvals", count: approvals.length ? approvals.reduce((sum, count) => sum + count, 0) : undefined, page: "Access Requests" },
        { label: "Failed provisioning", count: data.provisioning_failed, page: "Access Requests" },
        { label: "Overdue certifications", count: data.certification?.overdue, page: "Access Certification" },
      ].filter(item => (item.count ?? 0) > 0);
      return <>
        <div className="executive-kpis">
          {([
            ["Access grants this month", activity.data?.month?.grants, ArrowUpFromLine, "Access Requests"],
            ["Access revocations this month", activity.data?.month?.revocations, ArrowDownToLine, "Access Requests"],
            ["Active Microsoft Entra identities", entra?.identity_status?.active, Users, "Employees"],
            ["Open governance findings", risks, ShieldAlert, "Alerts & Findings"],
          ] as const).map(([label, value, Icon, page]) => <button key={label} className="executive-kpi" disabled={value === undefined}
            onClick={() => navigate(page, page === "Employees" ? "entra" : undefined)}>
            <Icon size={20} aria-hidden="true" /><span>{t(label)}</span><strong>{value ?? "—"}</strong>
          </button>)}
        </div>
        <div className="chart-layout">
          <Panel title={t("Verified access activity")}>
            <ActivityRange days={days} change={setDays} />
            <p>{t("IdentityOps provisioning only. External directory changes are excluded.")}</p>
            {activity.errorStatus === 403 ? <p>{t("Provisioning approval permission required.")}</p> :
              <QueryState result={activity}>{result => result.series ? <AccessLine key={days} series={result.series} /> :
                <p>{t("Provisioning history is unavailable.")}</p>}</QueryState>}
          </Panel>
          <Panel title={t("Governance findings by severity")}>
            {findings ? <Distribution rows={["critical", "high", "medium", "low"].map(level => [t(level), findings[level] ?? 0])} /> :
              <p>{t("No operational checks are available for your role.")}</p>}
          </Panel>
        </div>
        <Panel title={t("Requires attention")}>
          {priorities.length ? <ul className="executive-priorities">{priorities.map(({ label, count, page }) =>
            <li key={label}><button className="secondary-button" onClick={() => navigate(page)}>{t(label)} · {count}</button></li>)}</ul> :
            <p>{t(findings || approvals.length || data.provisioning_failed !== undefined || data.certification
              ? "No urgent items in your view." : "No operational checks are available for your role.")}</p>}
        </Panel>
      </>;
    }}</QueryState>
  </Page>;
}
