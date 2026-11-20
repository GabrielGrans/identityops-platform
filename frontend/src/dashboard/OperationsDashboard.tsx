import { t } from "../i18n";
import { CertificationMetrics, type Certification } from "../iam/CertificationMetrics";
import { Feedback, Page, Panel } from "../iam/common";
import { displayTime, useQuery } from "../iam/data";

interface Metrics {
  local_employees?: number; local_groups?: number; official_departments?: number; local_unassigned?: number;
  entra?: { users?: number; groups?: number; unassigned?: number; last_success: string | null; health: string; stale?: boolean };
  pending_local?: number; pending_entra?: number; provisioning_active?: number; provisioning_failed?: number;
  findings?: Record<string, number>; certification?: Certification;
}
interface Tile {
  name: string; value: number | string | undefined; page: string; source: string;
}

export function OperationsDashboard({ token, navigate, children }: {
  token: string; navigate: (page: string, source?: "local" | "entra") => void; children: React.ReactNode;
}) {
  const metrics = useQuery<Metrics>(token, "/v1/dashboard/operations");
  const data = metrics.data;
  const entra = data?.entra;
  const local = "Local IdentityOps";
  const graph = "Microsoft Entra ID";
  const inventory: Tile[] = [
    {name: "Entra users", value: entra?.users, page: "Employees", source: graph},
    {name: "Local employees", value: data?.local_employees, page: "Employees", source: local},
    {name: "Entra security groups", value: entra?.groups, page: "Access Groups", source: graph},
    {name: "Local RBAC groups", value: data?.local_groups, page: "Access Groups", source: local},
    {name: "Official departments", value: data?.official_departments, page: "Departments", source: local},
    {name: "Unassigned department", value: entra?.unassigned, page: "Departments", source: graph},
    {name: "Unassigned department", value: data?.local_unassigned, page: "Departments", source: local},
  ];
  const queue: Tile[] = [
    {name: "Pending approvals", value: data?.pending_local, page: "Access Requests", source: local},
    {name: "Pending approvals", value: data?.pending_entra, page: "Access Requests", source: graph},
    {name: "Provisioning in progress", value: data?.provisioning_active, page: "Access Requests", source: graph},
    {name: "Failed provisioning", value: data?.provisioning_failed, page: "Access Requests", source: graph},
  ];

  return <Page title={t("IAM Governance Dashboard")}>
    <Feedback message={metrics.error ? { text: metrics.error, error: true } : undefined} />
    {!data && !metrics.error && <p role="status">{t("Loading…")}</p>}
    {data && <>
      {!!entra && <Panel title={t("Entra synchronization health")}>
        <div className="iam-actions"><span className="directory-badge">{graph}</span>
          <strong>{t(entra.health)}</strong></div>
        <p>{t("Last successful sync:")} {entra.last_success ? displayTime(entra.last_success) : "—"}</p>
        {entra.stale && <p role="status">{t("Showing a stale Entra snapshot.")}</p>}
        <button className="secondary-button" onClick={() => navigate("Microsoft Entra ID")}>{t("Microsoft Entra ID")}</button>
      </Panel>}
      <DashboardTiles title="Directory inventory" tiles={inventory} navigate={navigate} />
      <DashboardTiles title="Access operations" tiles={queue} navigate={navigate} />
      {data.findings && <DashboardTiles title="Governance findings by severity" navigate={navigate} tiles={
        ["critical", "high", "medium", "low"].map(severity => ({
          name: severity, value: data.findings?.[severity] ?? 0, source: graph, page: "Notifications",
        }))
      } />}
      {data.certification && <Panel title={t("Access Certification Campaigns")}>
        <p title={t("Campaigns periodically review employee permissions and group memberships.")}>
          {t("Campaigns periodically review employee permissions and group memberships.")}
        </p>
        <CertificationMetrics result={data.certification} />
        <button className="secondary-button" onClick={() => navigate("Access Certification")}>{t("Open campaigns")}</button>
      </Panel>}
    </>}
    <details className="panel iam-panel"><summary>{t("Detailed governance activity")}</summary>{children}</details>
  </Page>;
}

function DashboardTiles({ title, tiles, navigate }: { title: string; tiles: Tile[]; navigate: (page: string, source?: "local" | "entra") => void }) {
  return <Panel title={t(title)}>
    <div className="operations-grid">
      {tiles.map(({name, value, page, source}) => <button className="operations-tile" key={`${source}:${name}`}
        onClick={() => navigate(page, source === "Local IdentityOps" ? "local" : "entra")}>
        <span className="directory-badge">{t(source)}</span>
        <strong>{value ?? "—"}</strong>
        <span>{t(name)}</span>
      </button>)}
    </div>
  </Panel>;
}
