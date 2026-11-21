import { useState } from "react";
import { t } from "../i18n";
import { DataTable, Page, Panel, QueryState, SectionTabs } from "../iam/common";
import { displayTime, useQuery, type QueryResult } from "../iam/data";
import { AccessLine, ActivityRange, Bars, Distribution, type AccessActivity } from "./ActivityCharts";
import { type Metrics } from "./OperationsDashboard";

const tabs = ["Access activity", "Risks & compliance", "Identities & departments"] as const;
type Area = typeof tabs[number];
interface Departments {
  local: { name: string; employees: number | null }[];
  entra: { name: string | null; employees: number }[];
}

export function AnalyticsPage({ token, metrics }: { token: string; metrics: QueryResult<Metrics> }) {
  const [area, setArea] = useState<Area>("Access activity");
  const [days, setDays] = useState("30");
  const activity = useQuery<AccessActivity>(token, area === "Access activity" ? `/v1/dashboard/membership-observations?days=${days}` : null);
  const risk = useQuery<{ available: boolean; departments?: { name: string | null; count: number }[] | null; policy_findings?: number; violating_memberships?: number }>(token,
    area === "Risks & compliance" && metrics.data?.findings ? "/v1/dashboard/risk-distribution" : null);
  const departments = useQuery<Departments>(token, area === "Identities & departments" && metrics.data?.official_departments !== undefined
    ? "/departments/operations/catalog" : null);
  return <Page title={t("Analytics")}>
    <SectionTabs items={tabs} active={area} change={setArea} label="Analytics sections" />
    {area === "Access activity" ? <>
      <ActivityRange days={days} change={setDays} />
      <p>{t("Changes are detected between collections. The time shown is the observation time.")}</p>
      {activity.errorStatus === 403 ? <p>{t("Entra and audit read permissions required.")}</p> : <QueryState result={activity}>{result => {
        if (!result.series) return <p>{t("Collect an Entra directory snapshot to start monitoring.")}</p>;
        return <>
          <Panel title={t("Observed Entra access changes")}><AccessLine key={days} series={result.series} /></Panel>
          <div className="panel-grid">
            <Panel title={t("Most modified security groups")}><Bars rows={result.groups?.map(group => [group.name ?? group.id, group.count]) ?? []} /></Panel>
            <Panel title={t("Recent observed changes")}>
              <DataTable label={t("Recent observed changes")} rows={result.recent ?? []} rowKey={row => row.id} columns={[
                { label: t("Observed at"), render: row => displayTime(row.observed_at) },
                { label: t("User"), render: row => row.user_name ?? row.user_object_id },
                { label: t("Group"), render: row => row.group_name ?? row.group_object_id },
                { label: t("Change"), render: row => t(row.operation === "added" ? "Membership added" : "Membership removed") },
              ]} />
            </Panel>
          </div>
        </>;
      }}</QueryState>}
    </> : <QueryState result={metrics}>{data => <>
      <p>{t("Current snapshot. Date filters require historical records.")}</p>
      {area === "Risks & compliance" ? <div className="panel-grid">
        <Panel title={t("Governance findings by severity")}>{data.findings ?
          <Distribution rows={["critical", "high", "medium", "low"].map(level => [t(level), data.findings?.[level] ?? 0])} /> :
          <p>{t("No operational checks are available for your role.")}</p>}</Panel>
        <Panel title={t("Access Certification Campaigns")}>
          {data.certification ? <Bars rows={[
            [t("Completed"), data.certification.completed], [t("pending"), data.certification.pending],
            [t("Overdue certifications"), data.certification.overdue],
          ]} /> : <p>{t("No operational checks are available for your role.")}</p>}
          <p>{t("Historical risk and certification trends are unavailable.")}</p>
        </Panel>
        {data.findings && <QueryState result={risk}>{distribution => distribution.available ?
          <Panel title={t("Policy findings by department")}>
            <p>{t("Open policy findings")} · {distribution.policy_findings}</p>
            <p>{t("Memberships violating access policies")} · {distribution.violating_memberships ?? "—"}</p>
            {distribution.departments && <Bars rows={distribution.departments.map(row => [row.name ?? t("Unassigned department"), row.count])} />}
          </Panel> : null}</QueryState>}
      </div> : <>
        <div className="panel-grid">
          <Panel title={t("Entra identity status")}>{data.entra?.identity_status ?
            <Distribution rows={Object.entries(data.entra.identity_status).map(([label, count]) => [t(label), count])}
              colors={["#a6c3bd", "#ed6256", "#a4adb8"]} /> : <p>{t("No records.")}</p>}</Panel>
          <Panel title={t("Unassigned department")}>
            <p>{t("Local IdentityOps")} · {data.local_unassigned ?? "—"}</p>
            <p>Microsoft Entra ID · {data.entra?.unassigned ?? "—"}</p>
            <p>{t("Historical directory growth is unavailable.")}</p>
          </Panel>
        </div>
        {data.official_departments !== undefined && <QueryState result={departments}>{catalog => <div className="panel-grid">
          <Panel title={t("Local department distribution")}><Bars rows={catalog.local.filter(row => row.employees !== null)
            .sort((a, b) => (b.employees ?? 0) - (a.employees ?? 0)).slice(0, 10).map(row => [row.name, row.employees ?? 0])} /></Panel>
          <Panel title={t("Entra department distribution")}><Bars rows={catalog.entra.filter(row => row.name)
            .sort((a, b) => b.employees - a.employees).slice(0, 10).map(row => [row.name ?? t("Unassigned department"), row.employees])} /></Panel>
        </div>}</QueryState>}
      </>}
    </>}</QueryState>}
  </Page>;
}
