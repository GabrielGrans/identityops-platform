import { EntraChangeRequests } from "./EntraChangeRequests";
import { t } from "../i18n";
import { useState, type ReactNode } from "react";
import { Drawer, DataTable, StatusBadge, Feedback, Page, Panel, Pagination, QueryState, SelectId,  } from "./common";
import { type CatalogItem, type Session, displayTime, PAGE_SIZE, useCursor, useMutation, useQuery } from "./data";

interface Workflow {
  id: number;
  employee_id: number;
  group_id: number;
  status: string;
  reason?: string;
  decided_by: number | null;
  decision_note: string | null;
  created_at: string;
  decided_at: string | null;
}

function WorkflowList({ rows, groupNames, actions }: {
  rows: Workflow[];
  groupNames: Map<number, string>;
  actions?: (row: Workflow) => ReactNode;
}) {
  const [selected, setSelected] = useState<Workflow>();
  const current = selected && rows.find(row => row.id === selected.id);
  return <>
    <DataTable label={t("Requests and reviews")} rows={rows} rowKey={row => row.id} columns={[
      { label: t("Request ID"), render: row => <button className="secondary-button" onClick={() => setSelected(row)}>#{row.id}</button> },
      { label: t("Employee"), render: row => `#${row.employee_id}` },
      { label: t("Group"), render: row => groupNames.get(row.group_id) ?? `#${row.group_id}` },
      { label: t("Status"), render: row => <StatusBadge>{t(row.status)}</StatusBadge> },
      { label: t("Date"), render: row => displayTime(row.created_at) },
    ]} />
    {current && <Drawer title={`${t("Request details")} #${current.id}`} close={() => setSelected(undefined)}>
      <p>{t("Employee")} #{current.employee_id} · {groupNames.get(current.group_id) ?? `#${current.group_id}`}</p>
      <p>{t(current.status)} · {displayTime(current.created_at)}</p>
      {current.reason && <p>{current.reason}</p>}
      {current.decided_at && <p>{current.decision_note} · {current.decided_by ? `#${current.decided_by} · ` : ""}{displayTime(current.decided_at)}</p>}
      {actions?.(current)}
    </Drawer>}
  </>;

}

function DecisionForm({ decisions, busy, onDecide }: {
  decisions: readonly [string, string]; busy: boolean; onDecide: (decision: string, note: string) => void;
}) {
  return <form className="iam-form" onSubmit={(event) => {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    onDecide(String(fields.get("decision")), String(fields.get("note")));
  }}>
    <label>{t("Decision")}<select aria-label={t("Decision")} name="decision" defaultValue="" required>
      <option value="">{t("Select…")}</option>
      {decisions.map((decision) => <option key={decision} value={decision}>{t(decision)}</option>)}
    </select></label>
    <label>{t("Decision note")}<input name="note" required maxLength={1000} /></label>
    <button className="primary-button" disabled={busy}>{t("Record decision")}</button>
  </form>;
}

export function RequestsPage({ session }: { session: Session }) {
  const mutation = useMutation(session.token);
  const [createLocal, setCreateLocal] = useState(false);
  const mineCursor = useCursor();
  const queueCursor = useCursor();
  const { token, permissions } = session;
  const catalog = useQuery<CatalogItem[]>(token, "/access-requests/catalog", mutation.revision);
  const names = new Map(catalog.data?.map((group) => [group.id, group.name]));
  const canApprove = permissions.includes("access:manage");
  const mine = useQuery<Workflow[]>(token, `/access-requests?limit=${PAGE_SIZE}${mineCursor.query}`, mutation.revision);
  const queue = useQuery<Workflow[]>(token, canApprove ? `/access-requests/queue?limit=${PAGE_SIZE}${queueCursor.query}` : null, mutation.revision);
  return <Page title={t("Access Requests")}>
    <EntraChangeRequests session={session} />
    <h2>{t("Employee self-service requests")}</h2>
    <Feedback message={mutation.message} />
    <button className="secondary-button" onClick={() => setCreateLocal(true)}>{t("Request local group access")}</button>
    {createLocal && <Drawer title={t("Request group access")} close={() => setCreateLocal(false)}>
      <QueryState result={catalog}>{(groups) => groups.length ? <form className="iam-form" onSubmit={async (event) => {
        event.preventDefault();
        const form = event.currentTarget;
        const fields = new FormData(form);
        if (await mutation.mutate("/access-requests", "POST", {
          group_id: Number(fields.get("group")), reason: fields.get("reason"),
        })) {
          form.reset();
          setCreateLocal(false);
          mineCursor.reset();
          queueCursor.reset();
        }
      }}>
        <SelectId label={t("Group")} name="group" items={groups} />
        <label>{t("Business justification")}<textarea name="reason" required maxLength={1000} /></label>
        <button className="primary-button" disabled={mutation.busy}>{t("Submit request")}</button>
      </form> : <p>{t("No groups are currently accepting requests.")}</p>}</QueryState>
    </Drawer>}
    <Panel title={t("My requests")}>
      <QueryState result={mine}>{(rows) => <>
        <WorkflowList rows={rows} groupNames={names} />
        <Pagination rows={rows} cursor={mineCursor} />
      </>}</QueryState>
    </Panel>
    {canApprove && <Panel title={t("Approval queue")}>
      <QueryState result={queue}>{(rows) => <>
        <WorkflowList rows={rows} groupNames={names} actions={(row) => row.employee_id !== session.employeeId && (
          <DecisionForm decisions={["approved", "rejected"]} busy={mutation.busy}
            onDecide={(decision, note) => void mutation.mutate(`/access-requests/${row.id}/decision`, "POST", { decision, note })} />
        )} />
        <Pagination rows={rows} cursor={queueCursor} />
      </>}</QueryState>
    </Panel>}
  </Page>;
}

export function ReviewsPage({ session }: { session: Session }) {
  const mutation = useMutation(session.token);
  const cursor = useCursor();
  const [create, setCreate] = useState(false);
  const [status, setStatus] = useState("pending");
  const { token, permissions } = session;
  const groups = useQuery<CatalogItem[]>(token, permissions.includes("groups:read") ? "/groups" : null);
  const result = useQuery<Workflow[]>(token,
    `/access-reviews?limit=${PAGE_SIZE}${cursor.query}${status && `&status=${status}`}`, mutation.revision);
  return <Page title={t("Access Reviews")}>
    <Feedback message={mutation.message} />
    <button className="primary-button" onClick={() => setCreate(true)}>{t("Open a membership review")}</button>
    {create && <Drawer title={t("Open a membership review")} close={() => setCreate(false)}>
      <Feedback message={mutation.message} />
      <form className="iam-form" onSubmit={async (event) => {
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        if (await mutation.mutate("/access-reviews", "POST", {
          employee_id: Number(form.get("employee")), group_id: Number(form.get("group")),
        })) {
          setStatus("pending");
          cursor.reset();
        }
      }}>
        <label>{t("Employee ID")}<input type="number" name="employee" required min={1} /></label>
        {groups.data ? <SelectId label={t("Group")} name="group" items={groups.data.filter((group) => group.is_active)} />
          : <label>{t("Group ID")}<input type="number" name="group" min={1} required /></label>}
        <button className="primary-button" disabled={mutation.busy}>{t("Open review")}</button>
      </form>
    </Drawer>}
    <Panel title={t("Reviews")}>
      <label>{t("Status")}<select aria-label={t("Status")} value={status} onChange={(event) => {
        setStatus(event.target.value);
        cursor.reset();
      }}>
        <option value="">{t("All")}</option>
        {["pending", "retained", "revoked", "superseded"].map((value) => <option key={value} value={value}>{t(value)}</option>)}
      </select></label>
      <QueryState result={result}>{(rows) => <>
        <WorkflowList rows={rows} groupNames={new Map(groups.data?.map((group) => [group.id, group.name]))}
          actions={(row) => row.status === "pending" && row.employee_id !== session.employeeId && (
            <DecisionForm decisions={["retained", "revoked"]} busy={mutation.busy}
              onDecide={(decision, note) => void mutation.mutate(`/access-reviews/${row.id}/decision`, "POST", { decision, note })} />
          )} />
        <Pagination rows={rows} cursor={cursor} />
      </>}</QueryState>
    </Panel>
  </Page>;
}

interface AuditEvent {
  id: number;
  actor_id: number | null;
  action: string;
  target_type: string;
  target_id: number | null;
  details: Record<string, unknown>;
  created_at: string;
}

export function AuditPage({ session }: { session: Session }) {
  const cursor = useCursor();
  const [filters, setFilters] = useState("");
  const [detail, setDetail] = useState<AuditEvent>();
  const result = useQuery<AuditEvent[]>(session.token, `/audit-events?limit=${PAGE_SIZE}${cursor.query}${filters}`);
  return <Page title={t("Audit Logs")}>
    <Panel title={t("Search events")}>
      <form className="iam-form" onSubmit={(event) => {
        event.preventDefault();
        const values = new FormData(event.currentTarget);
        const params = new URLSearchParams();
        for (const key of ["query", "actor_id", "category", "start_on", "end_on", "outcome"]) {
          const value = String(values.get(key)).trim();
          if (value) params.set(key, value);
        }
        cursor.reset();
        setFilters(`&${params}`);
      }}>
        <label>{t("Event category")}<select name="category">
          <option value="">{t("All categories")}</option>
          <option value="entra_sync">{t("Entra synchronization")}</option>
          <option value="entra_provisioning">{t("Entra provisioning")}</option>
          <option value="governance">{t("Governance")}</option>
          <option value="authorization">{t("Authorization")}</option>
        </select></label>
        <label>{t("Search actions")}<input name="query" type="search" placeholder="request.approved" maxLength={150} /></label>
        <label>{t("Start date (UTC)")}<input name="start_on" type="date" /></label>
        <label>{t("End date (UTC)")}<input name="end_on" type="date" /></label>
        <label>{t("Recorded outcome")}<select name="outcome"><option value="">{t("All statuses")}</option>
          {["succeeded", "failed", "approved", "rejected"].map(outcome => <option key={outcome} value={outcome}>{t(outcome)}</option>)}
        </select></label>
        <label>{t("Actor ID")}<input name="actor_id" type="number" min={1} /></label>
        <button className="primary-button">{t("Filter")}</button>
      </form>
    </Panel>
    <Panel title={t("Events")}>
      <QueryState result={result}>{rows => <>
        <DataTable label={t("Events")} rows={rows} rowKey={row => row.id} columns={[
          { label: t("Action"), render: row => <button className="secondary-button" onClick={() => setDetail(row)}>{row.action}</button> },
          { label: t("Date"), render: row => displayTime(row.created_at) },
          { label: t("Actor ID"), render: row => row.actor_id ?? t("System") },
          { label: t("Target"), render: row => `${row.target_type} ${row.target_id === null ? "" : "#" + row.target_id}` },
        ]} />
        <Pagination rows={rows} cursor={cursor} />
      </>}</QueryState>
    </Panel>
    {detail && <Drawer title={t("Event details")} close={() => setDetail(undefined)}>
      <dl><dt>{t("Action")}</dt><dd>{detail.action}</dd>
        <dt>{t("Date")}</dt><dd>{displayTime(detail.created_at)}</dd>
        <dt>{t("Actor ID")}</dt><dd>{detail.actor_id ?? t("System")}</dd>
        <dt>{t("Target")}</dt><dd>{detail.target_type} {detail.target_id}</dd></dl>
      {Object.keys(detail.details).length > 0 && <pre>{JSON.stringify(detail.details, null, 2)}</pre>}
    </Drawer>}
  </Page>;
}
