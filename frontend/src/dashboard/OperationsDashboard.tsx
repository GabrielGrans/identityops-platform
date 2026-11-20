import { t } from "../i18n";
import { Page, QueryState } from "../iam/common";
import { displayTime, useQuery } from "../iam/data";
import { type Certification } from "../iam/CertificationMetrics";

export interface Metrics {
  local_employees?: number; local_groups?: number; official_departments?: number; local_unassigned?: number;
  entra?: { users?: number; groups?: number; unassigned?: number; last_success: string | null; health: string; stale?: boolean };
  pending_local?: number; pending_entra?: number; provisioning_active?: number; provisioning_failed?: number;
  findings?: Record<string, number>; certification?: Certification;
}

export type Navigate = (page: string, source?: "local" | "entra") => void;

export function OperationsDashboard({ token, navigate }: { token: string; navigate: Navigate }) {
  const metrics = useQuery<Metrics>(token, "/v1/dashboard/operations");
  return <Page title={t("IAM Governance Dashboard")}>
    <p className="executive-subtitle">{t("Monitor directory health, access risks and decisions awaiting action.")}</p>
    <QueryState result={metrics}>{data => {
      const { entra, findings } = data;
      const approvals = [data.pending_local, data.pending_entra].filter(value => value !== undefined);
      const risks = findings && Object.values(findings).reduce((total, count) => total + count, 0);
      const priorities = [
        entra && (entra.stale || ["failed", "unavailable"].includes(entra.health)) &&
          { label: "Review Entra synchronization", page: "Microsoft Entra ID" },
        !!(findings?.critical || findings?.high) && { label: "Investigate high-priority findings", page: "Notifications" },
        approvals.some(count => count > 0) && { label: "Review pending access requests", page: "Access Requests" },
        !!data.provisioning_failed && { label: "Investigate failed provisioning", page: "Access Requests" },
        !!data.certification?.overdue && { label: "Review overdue certifications", page: "Access Certification" },
      ].filter(item => item !== undefined && item !== false);
      const visibleChecks = !!entra || !!findings || approvals.length > 0 ||
        data.provisioning_failed !== undefined || data.certification !== undefined;
      return <>
        <div className="executive-status">
          <button className="secondary-button" onClick={() => navigate("Microsoft Entra ID")} disabled={!entra}>{t("Entra synchronization")}</button>
          <strong>{t(entra?.health ?? "unavailable")}</strong>
          {entra?.last_success && <span>{t("Last successful sync:")} {displayTime(entra.last_success)}</span>}
        </div>
        <div className="executive-kpis">
          <Kpi label="Entra identities" value={entra?.users} open={() => navigate("Employees", "entra")} />
          <Kpi label="Local IdentityOps identities" value={data.local_employees} open={() => navigate("Employees", "local")} />
          <Kpi label="Open governance risks" value={risks} open={() => navigate("Notifications")} />
          <Kpi label="Pending actions" value={approvals.length ? approvals.reduce((a, b) => a + b, 0) : undefined}
            open={() => navigate("Access Requests")} />
        </div>
        <section className="executive-attention" aria-labelledby="attention-heading">
          <h2 id="attention-heading">{t("Requires attention")}</h2>
          {priorities.length ? <ul className="executive-priorities">{priorities.map(item => <li key={item.label}>
            <button className="secondary-button" onClick={() => navigate(item.page)}>{t(item.label)}</button>
          </li>)}</ul> : <p>{t(visibleChecks ? "No urgent items in your view." : "No operational checks are available for your role.")}</p>}
        </section>
      </>;
    }}</QueryState>
  </Page>;
}

function Kpi({ label, value, open }: { label: string; value?: number; open: () => void }) {
  return <button className="executive-kpi" disabled={value === undefined} onClick={open}>
    <span>{t(label)}</span><strong>{value ?? "—"}</strong>
  </button>;
}
