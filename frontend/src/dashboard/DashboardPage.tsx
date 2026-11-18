import { useState, type ReactNode } from "react";
import { Activity, ArrowRight, Building2, ClipboardCheck, Layers3, LockKeyhole, RefreshCw, ShieldAlert, ShieldCheck, Users, type LucideIcon } from "lucide-react";
import { useQuery, type QueryResult } from "../iam/data";
import "./dashboard.css";

type Inventory = { active: number; inactive: number };
type Decisions = { retained: number; revoked: number };
type Certification = {
  active_campaigns: number; overdue_campaigns: number; overdue_items: number;
  pending: number; retained: number; revoked: number; superseded: number; decisions: Decisions;
};
type Recorded = {
  joiners: number; movers: number; leavers: number;
  revocation_events: number; failed_entra_syncs: number;
};
type Summary = {
  as_of: string; period_start: string;
  employees: Inventory | null; departments: Inventory | null;
  groups: Inventory | null; permissions: Inventory | null;
  pending_requests: number | null;
  reviews: { pending: number; decisions: Decisions } | null;
  certification_available: boolean | null; certification: Certification | null;
  security: { privileged_memberships: number; inactive_accounts_with_active_groups: number } | null;
  activity: Recorded | null;
};
const categories = { lifecycle: "Lifecycle", access: "Access", certification: "Certification", entra: "Entra ID", other: "Other" };
type EventPage = {
  items: { id: number; created_at: string; category: keyof typeof categories; label: string }[];
  next_before_id: number | null;
};
const endpoint = "/v1/dashboard";
const number = new Intl.NumberFormat();
const time = new Intl.DateTimeFormat(undefined, {
  month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", timeZone: "UTC",
});
const inventoryCards = [
  ["employees", "Employees", Users], ["departments", "Departments", Building2],
  ["groups", "Access groups", Layers3], ["permissions", "Permissions", LockKeyhole],
] as const;

function formatTime(value: string) {
  return `${time.format(new Date(value))} UTC`;
}

function LoadState<T>({ result, retry, children }: {
  result: QueryResult<T>; retry: () => void; children: (data: T) => ReactNode;
}) {
  if (result.error) {
    const messages: Record<number, string> = {
      401: "Your session has expired. Sign in again to view the dashboard.",
      403: "Your role does not have access to this dashboard data.",
    };
    return <div className="gov-notice" role="alert">
      <p>{messages[result.errorStatus ?? 0] ?? "Dashboard data is temporarily unavailable."}</p>
      {result.errorStatus !== 403 && <button onClick={retry}>Retry</button>}
    </div>;
  }
  if (result.data === undefined) return <div className="gov-skeleton" role="status" aria-label="Loading dashboard data"><i /><i /><i /></div>;
  return children(result.data);
}

export default function DashboardPage({ token, navigate }: { token: string; navigate: (page: string) => void }) {
  const [days, setDays] = useState("30");
  const [revision, setRevision] = useState(0);
  const summary = useQuery<Summary>(token, `${endpoint}/summary?days=${days}`, revision);
  const refresh = () => setRevision((value) => value + 1);

  return <div className="gov">
    <header className="gov-header">
      <div><h1>IAM Governance Dashboard</h1><p>Identity inventory, access oversight and recorded activity</p></div>
      <div className="gov-controls">
        <label>Activity window<select value={days} onChange={(event) => setDays(event.target.value)}>
          <option value="7">Last 7 days</option><option value="30">Last 30 days</option><option value="90">Last 90 days</option>
        </select></label>
        <button onClick={refresh}><RefreshCw size={16} aria-hidden="true" />Refresh</button>
      </div>
    </header>
    <LoadState result={summary} retry={refresh}>{(data) => <>
      <SectionHeading title="Current overview" context={`Snapshot at ${formatTime(data.as_of)}`} />
      <div className="gov-grid">{inventoryCards.map(([key, label, Icon]) => {
        const item = data[key];
        return item && <article className="gov-panel gov-kpi" key={key}>
          <h3><Icon size={17} aria-hidden="true" />{label}</h3>
          <strong>{number.format(item.active + item.inactive)}</strong>
          <p>{number.format(item.active)} active · {number.format(item.inactive)} inactive</p>
        </article>;
      })}</div>
      <div className="gov-panels">
        {(data.pending_requests !== null || data.reviews) && <Panel title="Approval & review backlog" icon={ClipboardCheck}>
          <dl>
            {data.pending_requests !== null && <Metric label="Requests awaiting approval" value={data.pending_requests} />}
            {data.reviews && <Metric label="Pending access reviews" value={data.reviews.pending} />}
          </dl>
          {(data.pending_requests ?? 0) + (data.reviews?.pending ?? 0) === 0 && <p>No pending work in the queues you can view.</p>}
          <div className="gov-controls">
            {data.pending_requests !== null && <Navigate label="Access Requests" navigate={navigate} />}
            {data.reviews && <Navigate label="Access Reviews" navigate={navigate} />}
          </div>
        </Panel>}
        {data.certification_available === false && <Panel title="Certification progress" icon={ShieldCheck}>
          <p>Apply the database migrations to make campaign data available.</p>
        </Panel>}
        {data.certification && <Panel title="Certification progress" icon={ShieldCheck}>
          <CertificationProgress data={data.certification} />
          <Navigate label="Access Certification" navigate={navigate} />
        </Panel>}
        {data.security && <Panel title="Security indicators" icon={ShieldAlert}>
          <dl>
            <Metric label="Privileged memberships" value={data.security.privileged_memberships} />
            <Metric label="Inactive accounts in active groups" value={data.security.inactive_accounts_with_active_groups} warning />
          </dl>
          <p>Inactive accounts cannot sign in. Review their saved group memberships.</p>
        </Panel>}
      </div>
      {(data.activity || data.reviews || data.certification) && <>
        <SectionHeading title="Recorded in selected window" context={`${formatTime(data.period_start)} – ${formatTime(data.as_of)}`} />
        <div className="gov-panels">
          {(data.reviews || data.certification) && <Panel title="Retain & revoke decisions" icon={ClipboardCheck}>
            <dl>
              {data.reviews && <DecisionMetrics name="Access review" data={data.reviews.decisions} />}
              {data.certification && <DecisionMetrics name="Certification" data={data.certification.decisions} />}
            </dl>
          </Panel>}
          {data.activity && <>
            <Panel title="Identity lifecycle" icon={Activity}><Lifecycle data={data.activity} /></Panel>
            <Panel title="Recorded security events" icon={ShieldAlert}>
              <dl><Metric label="Access revocation events" value={data.activity.revocation_events} />
              <Metric label="Failed Entra synchronizations" value={data.activity.failed_entra_syncs} warning /></dl>
            </Panel>
          </>}
        </div>
      </>}
      {data.activity && <RecentActivity key={`${days}:${revision}`} token={token} days={days} navigate={navigate} />}
    </>}</LoadState>
  </div>;
}

function SectionHeading({ title, context }: { title: string; context: string }) {
  return <div className="gov-section-heading"><h2>{title}</h2><span>{context}</span></div>;
}
function Panel({ title, icon: Icon, children }: { title: string; icon: LucideIcon; children: ReactNode }) {
  return <section className="gov-panel"><h2><Icon size={18} aria-hidden="true" />{title}</h2>{children}</section>;
}
function Metric({ label, value, warning }: { label: string; value: number; warning?: boolean }) {
  return <div><dt>{label}</dt><dd className={warning && value > 0 ? "gov-warning" : undefined}>{number.format(value)}</dd></div>;
}
function DecisionMetrics({ name, data }: { name: string; data: Decisions }) {
  return <><Metric label={`${name} · retained`} value={data.retained} /><Metric label={`${name} · revoked`} value={data.revoked} /></>;
}
function Navigate({ label, navigate }: { label: string; navigate: (page: string) => void }) {
  return <button className="gov-link" onClick={() => navigate(label)}>{label}<ArrowRight size={15} aria-hidden="true" /></button>;
}

function CertificationProgress({ data }: { data: Certification }) {
  const decided = data.retained + data.revoked;
  const actionable = decided + data.pending;
  return <>
    <p>{number.format(data.active_campaigns)} active campaigns</p>
    {actionable > 0 ? <label className="gov-progress">
      <span>{number.format(decided)} of {number.format(actionable)} reviewable items decided</span>
      <progress value={decided} max={actionable} />
    </label> : <p>No reviewable items in active campaigns.</p>}
    <dl>
      <Metric label="Overdue active campaigns" value={data.overdue_campaigns} warning />
      <Metric label="Overdue pending items" value={data.overdue_items} warning />
      <Metric label="Superseded items" value={data.superseded} />
    </dl>
  </>;
}

function Lifecycle({ data }: { data: Recorded }) {
  const rows = [["Joiners", data.joiners], ["Movers", data.movers], ["Leavers", data.leavers]] as const;
  const maximum = Math.max(data.joiners, data.movers, data.leavers, 1);
  return <ul className="gov-bars">{rows.map(([label, value]) => <li key={label}>
    <span>{label}</span><div aria-hidden="true"><i style={{ width: `${value / maximum * 100}%` }} /></div>
    <strong>{number.format(value)}</strong>
  </li>)}</ul>;
}

function RecentActivity({ token, days, navigate }: { token: string; days: string; navigate: (page: string) => void }) {
  const [category, setCategory] = useState("");
  const [positions, setPositions] = useState<number[]>([]);
  const [retry, setRetry] = useState(0);
  const before = positions.at(-1);
  const query = new URLSearchParams({ days, limit: "8" });
  if (category) query.set("category", category);
  if (before !== undefined) query.set("before_id", String(before));
  const result = useQuery<EventPage>(token, `${endpoint}/activity?${query}`, retry);
  return <Panel title="Recent audit activity" icon={Activity}>
    <div className="gov-controls gov-event-controls">
      <label>Event category<select value={category} onChange={(event) => { setCategory(event.target.value); setPositions([]); }}>
        <option value="">All categories</option>
        {Object.entries(categories).map(([key, label]) => <option value={key} key={key}>{label}</option>)}
      </select></label>
      <Navigate label="Audit Logs" navigate={navigate} />
    </div>
    <LoadState result={result} retry={() => setRetry((value) => value + 1)}>{(page) => <>
      {page.items.length === 0 ? <p>No audit events match this window and category.</p> :
        <ul className="gov-events">{page.items.map((event) => <li key={event.id}>
          <div><strong>{event.label}</strong><span>{categories[event.category]}</span></div>
          <time dateTime={event.created_at}>{formatTime(event.created_at)}</time>
        </li>)}</ul>}
      {(positions.length > 0 || page.next_before_id !== null) && <div className="gov-controls">
        <button disabled={positions.length === 0} onClick={() => setPositions((values) => values.slice(0, -1))}>Previous page</button>
        <button disabled={page.next_before_id === null} onClick={() => {
          const next = page.next_before_id;
          if (next !== null) setPositions((values) => [...values, next]);
        }}>Next page</button>
      </div>}
    </>}</LoadState>
  </Panel>;
}
