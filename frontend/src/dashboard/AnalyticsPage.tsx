import { useState } from "react";
import { t } from "../i18n";
import { CertificationMetrics } from "../iam/CertificationMetrics";
import { DepartmentOperations } from "../iam/DepartmentOperations";
import { CollapsiblePanel, Page, Panel, QueryState } from "../iam/common";
import { displayTime, useQuery } from "../iam/data";
import { type Metrics, type Navigate } from "./OperationsDashboard";

type AuditEvent = { action: string; created_at: string };

type Area = "Directory inventory" | "Access operations" | "Audit activity";
interface ActivityPage {
  items: {id: number; category: string; label: string; created_at: string}[];
}
interface ActivitySummary {
  activity: {joiners: number; movers: number; leavers: number; revocation_events: number; failed_entra_syncs: number} | null;
}

export function AnalyticsPage({ token, navigate }: { token: string; navigate: Navigate }) {
  const [area, setArea] = useState<Area>("Directory inventory");
  const [days, setDays] = useState("30");
  const metrics = useQuery<Metrics>(token, "/v1/dashboard/operations");
  return <Page title={t("Analytics")}>
    <div className="analytics-switch iam-actions" role="group" aria-label={t("Analytics sections")}>
      {(["Directory inventory", "Access operations", "Audit activity"] as const).map(name =>
        <button key={name} className="secondary-button" aria-pressed={area === name} onClick={() => setArea(name)}>{t(name)}</button>)}
    </div>
    {area === "Audit activity" ? <>
      <div className="iam-form"><label>{t("Activity window")}
        <select value={days} onChange={event => setDays(event.target.value)}>
          {["7", "30", "90"].map(day => <option key={day} value={day}>{t(`Last ${day} days`)}</option>)}
        </select></label></div>
      <AuditActivity token={token} days={days} navigate={navigate} />
      <RecordedOperations token={token} days={days} />
    </> : <QueryState result={metrics}>{data => area === "Directory inventory" ? <>
      <Panel title={t("Directory inventory")}>
        <MetricsList rows={[
          ["Entra security groups", data.entra?.groups], ["Local RBAC groups", data.local_groups],
          ["Official departments", data.official_departments],
        ]} />
      </Panel>
      {data.official_departments !== undefined && <DepartmentOperations token={token} revision={0} />}
      {data.entra && <Panel title={t("Entra synchronization health")}>
        <p>{t(data.entra.health)} · {t("Last successful sync:")} {data.entra.last_success ? displayTime(data.entra.last_success) : "—"}</p>
        <button className="secondary-button" onClick={() => navigate("Microsoft Entra ID")}>Microsoft Entra ID</button>
      </Panel>}
    </> : <>
      {data.findings && <Panel title={t("Governance findings by severity")}>
        <MetricsList rows={["critical", "high", "medium", "low"].map(level => [level, data.findings?.[level] ?? 0])} />
      </Panel>}
      <Panel title={t("Access operations")}>
        <MetricsList rows={[["Provisioning in progress", data.provisioning_active], ["Failed provisioning", data.provisioning_failed]]} />
        <button className="secondary-button" onClick={() => navigate("Access Requests")}>{t("Access Requests")}</button>
      </Panel>
      {data.certification && <CollapsiblePanel title={t("Access Certification Campaigns")}>
        <CertificationMetrics result={data.certification} />
        <button className="secondary-button" onClick={() => navigate("Access Certification")}>{t("Open campaigns")}</button>
      </CollapsiblePanel>}
    </>}</QueryState>}
  </Page>;
}

function MetricsList({ rows }: { rows: [string, number | undefined][] }) {
  return <dl className="analytics-metrics">{rows.map(([label, count]) => <div key={label}>
    <dt>{t(label)}</dt><dd>{count ?? "—"}</dd>
  </div>)}</dl>;
}

function AuditActivity({ token, days, navigate }: { token: string; days: string; navigate: Navigate }) {
  const summary = useQuery<ActivitySummary>(token, `/v1/dashboard/summary?days=${days}`);
  const activity = useQuery<ActivityPage>(token, `/v1/dashboard/activity?days=${days}&limit=8`);
  return <>
    <Panel title={t("Recorded in selected window")}>
      <QueryState result={summary}>{({ activity: counts }) => counts ? <MetricsList rows={[
        ["Joiners", counts.joiners], ["Movers", counts.movers], ["Leavers", counts.leavers],
        ["Access revocation events", counts.revocation_events], ["Failed Entra synchronizations", counts.failed_entra_syncs],
      ]} /> : <p>{t("Audit read permission required")}</p>}</QueryState>
    </Panel>
    <CollapsiblePanel title={t("Recent audit activity")}>
      <QueryState result={activity}>{data => data.items.length ? <ul className="iam-list">{data.items.map(item =>
        <li key={item.id}><span>{t(item.label)}</span><time dateTime={item.created_at}>{displayTime(item.created_at)}</time></li>
      )}</ul> : <p>{t("No events match the current filters.")}</p>}</QueryState>
      <button className="secondary-button" onClick={() => navigate("Audit Logs")}>{t("Audit Logs")}</button>
    </CollapsiblePanel>
  </>;
}

function RecordedOperations({ token, days }: { token: string; days: string }) {
  const provisioning = useQuery<AuditEvent[]>(token, "/audit-events?category=entra_provisioning&limit=200");
  const sync = useQuery<AuditEvent[]>(token, "/audit-events?category=entra_sync&limit=200");
  if (provisioning.errorStatus === 403 || sync.errorStatus === 403) return null;
  return <CollapsiblePanel title={t("Provisioning and synchronization activity")}>
    <p>{t("Counts use the latest 200 audit events per category within the selected window.")}</p>
    <QueryState result={provisioning}>{events => <OutcomeCounts events={events} days={days} prefix="entra.provisioning." />}</QueryState>
    <QueryState result={sync}>{events => <OutcomeCounts events={events} days={days} prefix="entra.sync." />}</QueryState>
  </CollapsiblePanel>;
}

function OutcomeCounts({ events, days, prefix }: { events: AuditEvent[]; days: string; prefix: string }) {
  const [now] = useState(Date.now);
  const cutoff = now - Number(days) * 86_400_000;
  const counts = new Map<string, number>();
  for (const event of events) {
    if (Date.parse(event.created_at) < cutoff) continue;
    const action = event.action.slice(prefix.length);
    counts.set(action, (counts.get(action) ?? 0) + 1);
  }
  return <section>
    <h3>{t(prefix === "entra.sync." ? "Entra synchronization" : "Entra provisioning")}</h3>
    {counts.size ? <MetricsList rows={[...counts.entries()]} /> : <p>{t("No events match the current filters.")}</p>}
  </section>;
}
