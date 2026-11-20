import { useState, type FormEvent } from "react";
import { t } from "../i18n";
import { request } from "../services/api";
import { CollapsiblePanel, DataTable, Drawer, Feedback, Panel, QueryState, StatusBadge } from "./common";
import { displayTime, provisioningStatus, useMutation, useQuery, type Session } from "./data";

const endpoint = "/entra/automation";
const statuses = ["pending", "direct_authorized", "approved", "executing", "succeeded", "failed", "conflict", "expired", "rejected"];
type Subject = { user_id: string } | { employee_id: number };
type Draft = Subject & { group_id: string; add: boolean; justification: string };
interface Preview { user_id: string; group_id: string; expected: boolean; snapshot_id: number; direct_authorized: boolean }
interface ServiceNowEvidence {
  ritm: string; sys_id: string; requester_id: string; beneficiary_id: string; approver_id: string; approval_id: string;
  user_object_id: string; group_object_id: string; operation: "grant" | "revoke"; justification: string;
}
interface Change {
  id: number; employee_id: number | null; user_object_id: string; error_code: string | null; requester_id: number;
  reviewer_id: number | null; status: string; expires_at: string; created_at: string | null; employee_name: string | null; group_name: string | null;
  request: Preview & Draft & { direct_authorization?: { actor_id: number }; servicenow?: ServiceNowEvidence };
}
interface Timeline { id: number; action: string; created_at: string; actor_id: number | null; verified_membership: boolean | null }

export function EntraChangeRequests({ session }: { session: Session }) {
  const canRequest = session.permissions.includes("entra:request_change");
  const canApprove = session.permissions.includes("entra:approve_change");
  const mutation = useMutation(session.token);
  const [create, setCreate] = useState(false);
  const [selected, setSelected] = useState<number>();
  const [cursors, setCursors] = useState<number[]>([]);
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");
  const before = cursors.at(-1);
  const params = new URLSearchParams({ query: search });
  if (before) params.set("before_id", String(before));
  if (status) params.set("status", status);
  const rows = useQuery<Change[]>(session.token, canRequest || canApprove ? `${endpoint}/requests?${params}` : null, mutation.revision, true);
  if (!canRequest && !canApprove) return null;
  const current = rows.data?.find(row => row.id === selected);
  return <><Panel title={t("Administrative Entra requests")}>
    <Feedback message={mutation.message} />
    <div className="iam-actions">
      {canRequest && <button className="primary-button" onClick={() => setCreate(true)}>{t("New request")}</button>}
      <button className="secondary-button" onClick={mutation.refresh}>{t("Refresh")}</button>
    </div>
    <form className="iam-form enterprise-toolbar" onSubmit={event => {
      event.preventDefault();
      setCursors([]);
      setSearch(String(new FormData(event.currentTarget).get("query") ?? "").trim());
    }}>
      <label>{t("Search requests")}<input type="search" name="query" maxLength={150} /></label>
      <label>{t("Status")}<select value={status} onChange={event => { setStatus(event.target.value); setCursors([]); }}>
        <option value="">{t("All statuses")}</option>
        {statuses.map(value => <option key={value} value={value}>{provisioningStatus(value)}</option>)}
      </select></label>
      <button className="secondary-button">{t("Search")}</button>
    </form>
    {create && <NewRequest session={session} close={() => setCreate(false)} completed={() => {
      setCreate(false); setStatus(""); setSearch(""); setCursors([]); mutation.refresh();
    }} />}
    <QueryState result={rows}>{items => <>
      <p>{t("On this page")} · {t("pending")} {items.filter(item => item.status === "pending").length} · {t("Completed")} {items.filter(item => item.status === "succeeded").length}</p>
      <DataTable label={t("Administrative Entra requests")} rows={items} rowKey={item => item.id} columns={[
        { label: t("Request ID"), render: item => <button className="secondary-button" onClick={() => setSelected(item.id)}>#{item.id}</button> },
        { label: t("Source"), render: item => item.request.servicenow ? `ServiceNow · ${item.request.servicenow.ritm}` : "IdentityOps" },
        { label: t("Employee"), render: item => item.employee_name ?? (item.employee_id ? `#${item.employee_id}` : item.user_object_id) },
        { label: t("Group"), render: item => item.group_name ?? item.request.group_id },
        { label: t("Action"), render: item => t(item.request.add ? "Add membership" : "Remove membership") },
        { label: t("Requested by"), render: item => `#${item.requester_id}` },
        { label: t("Status"), render: item => <StatusBadge>{provisioningStatus(item.status)}</StatusBadge> },
        { label: t("Date"), render: item => item.created_at ? displayTime(item.created_at) : "—" },
      ]} />
      <div className="iam-actions">
        <button className="secondary-button" disabled={!before} onClick={() => setCursors(cursors.slice(0, -1))}>{t("Previous page")}</button>
        <button className="secondary-button" disabled={items.length < 50} onClick={() => setCursors([...cursors, items[49].id])}>{t("Next page")}</button>
      </div>
    </>}</QueryState>
    {current && <RequestDetails item={current} close={() => setSelected(undefined)} session={session} canApprove={canApprove}
      mutation={mutation} />}
  </Panel>
  {canApprove && <ServiceNowSimulations token={session.token} revision={mutation.revision} />}
  </>;
}

interface Simulation {
  sys_id: string; created_at: string; evidence: ServiceNowEvidence;
}

function ServiceNowSimulations({ token, revision }: { token: string; revision: number }) {
  const [cursors, setCursors] = useState<string[]>([]);
  const [current, setCurrent] = useState<Simulation>();
  const before = cursors.at(-1);
  const rows = useQuery<Simulation[]>(token, `/integrations/servicenow/access-requests/snapshot${before ? `?before=${before}` : ""}`, revision);
  if (rows.data?.length === 0 && !before) return null;
  return <CollapsiblePanel title={t("ServiceNow simulations")}>
    <QueryState result={rows}>{items => <>
      <DataTable label={t("ServiceNow simulations")} rows={items} rowKey={item => item.sys_id} columns={[
        { label: "RITM", render: item => <button className="secondary-button" onClick={() => setCurrent(item)}>{item.evidence.ritm}</button> },
        { label: t("Employee"), render: item => item.evidence.user_object_id },
        { label: t("Group"), render: item => item.evidence.group_object_id },
        { label: t("Status"), render: () => <StatusBadge>{t("Simulated")}</StatusBadge> },
        { label: t("Date"), render: item => displayTime(item.created_at) },
      ]} />
      <button className="secondary-button" disabled={!before} onClick={() => setCursors(cursors.slice(0, -1))}>{t("Previous page")}</button>
      <button className="secondary-button" disabled={items.length < 25} onClick={() => setCursors([...cursors, items[24].sys_id])}>{t("Next page")}</button>
    </>}</QueryState>
    {current && <Drawer title={current.evidence.ritm} close={() => setCurrent(undefined)}>
      <p role="status">{t("Simulation completed without changing Microsoft Entra ID.")}</p>
      <dl><ServiceNowDetails evidence={current.evidence} />
        <dt>{t("Employee")}</dt><dd>{current.evidence.user_object_id}</dd>
        <dt>{t("Group")}</dt><dd>{current.evidence.group_object_id}</dd>
        <dt>{t("Action")}</dt><dd>{t(current.evidence.operation === "grant" ? "Add membership" : "Remove membership")}</dd>
        <dt>{t("Business justification")}</dt><dd>{current.evidence.justification}</dd>
        <dt>{t("Date")}</dt><dd>{displayTime(current.created_at)}</dd>
      </dl>
    </Drawer>}
  </CollapsiblePanel>;
}

function ServiceNowDetails({ evidence }: { evidence: ServiceNowEvidence }) {
  return <>
    <dt>{t("Source")}</dt><dd>ServiceNow · {evidence.ritm} · {evidence.sys_id}</dd>
    <dt>{t("Requested by in ServiceNow")}</dt><dd>{evidence.requester_id}</dd>
    <dt>{t("ServiceNow beneficiary")}</dt><dd>{evidence.beneficiary_id}</dd>
    <dt>{t("Approved by in ServiceNow")}</dt><dd>{evidence.approver_id} · {evidence.approval_id}</dd>
  </>;
}

function RequestDetails({ item, session, close, canApprove, mutation }: {
  item: Change; session: Session; close: () => void; canApprove: boolean; mutation: ReturnType<typeof useMutation>;
}) {
  const timeline = useQuery<Timeline[]>(session.token, `${endpoint}/requests/${item.id}/timeline`, mutation.revision);
  const verified = timeline.data?.find(event => event.action === "succeeded")?.verified_membership;
  return <Drawer title={`${t("Request details")} #${item.id}`} close={close}>
    <dl>
      {item.request.servicenow && <ServiceNowDetails evidence={item.request.servicenow} />}
      <dt>{t("Employee")}</dt><dd>{item.employee_name ?? (item.employee_id ? `#${item.employee_id}` : "—")}</dd>
      <dt>{t("Entra object ID")}</dt><dd>{item.user_object_id}</dd>
      <dt>{t("Group")}</dt><dd>{item.group_name ? `${item.group_name} · ${item.request.group_id}` : item.request.group_id}</dd>
      <dt>{t("Action")}</dt><dd>{t(item.request.add ? "Add membership" : "Remove membership")}</dd>
      <dt>{t(item.request.servicenow ? "Integration identity" : "Requested by")}</dt><dd>#{item.requester_id}</dd>
      <dt>{t("Business justification")}</dt><dd>{item.request.justification}</dd>
      <dt>{t("Approval")}</dt><dd>{item.request.direct_authorization ? t("Authorized administrator changes enter the execution queue directly.")
        : item.reviewer_id ? `#${item.reviewer_id} · ${t(item.status === "rejected" ? "rejected" : "approved")}` : t("No decision recorded")}</dd>
      <dt>{t("Expires at")}</dt><dd>{displayTime(item.expires_at)}</dd>
      <dt>{t("Status")}</dt><dd><StatusBadge>{provisioningStatus(item.status)}</StatusBadge></dd>
      <dt>{t("Graph verification")}</dt><dd>{verified == null ? "—" : t(verified ? "Present" : "Absent")}</dd>
    </dl>
    {item.error_code && <p className="enterprise-error" role="status">{t("Provisioning reported an error.")} · {t(item.error_code)}</p>}
    <Feedback message={mutation.message} />
    {canApprove && item.status === "pending" && item.employee_id !== session.employeeId &&
      item.requester_id !== session.employeeId && new Date(item.expires_at) > new Date() &&
      <form className="iam-form" onSubmit={async event => {
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        await mutation.mutate(`${endpoint}/requests/${item.id}/decision`, "POST", {
          approve: form.get("decision") === "approve", note: String(form.get("note")),
        });
      }}>
        <label>{t("Decision")}<select name="decision">
          <option value="approve">{t("Approve")}</option><option value="reject">{t("Reject")}</option>
        </select></label>
        <label>{t("Decision note")}<input name="note" required minLength={8} maxLength={1000} /></label>
        <button className="primary-button" disabled={mutation.busy}>{t("Record decision")}</button>
      </form>}
    <h3>{t("Audit timeline")}</h3>
    <QueryState result={timeline}>{events => events.length ? <ol className="iam-list">{events.map(event =>
      <li key={event.id}><strong>{t(event.action)}</strong><span>{displayTime(event.created_at)} · {event.actor_id ? `#${event.actor_id}` : t("System")}</span></li>
    )}</ol> : <p>{t("No records.")}</p>}</QueryState>
  </Drawer>;
}

interface Option { object_id: string; display_name: string | null; synchronized: boolean; email?: string | null; eligibility?: string }

function DirectoryPicker({ token, kind, selected, choose }: {
  token: string; kind: "users" | "groups"; selected?: Option; choose: (option: Option) => void;
}) {
  const [search, setSearch] = useState("");
  const [pages, setPages] = useState<number[]>([]);
  const params = new URLSearchParams({ query: search, limit: "25" });
  if (pages.length) params.set("after", String(pages.at(-1)));
  const result = useQuery<{ items: Option[]; next_after: number | null }>(token, `/entra/directory/${kind}?${params}`);
  return <>
    <form className="iam-form enterprise-toolbar" onSubmit={event => {
      event.preventDefault();
      setSearch(String(new FormData(event.currentTarget).get("search") ?? "").trim());
      setPages([]);
    }}>
      <label>{t(kind === "users" ? "Search name, email, job title or department" : "Search groups")}<input type="search" name="search" maxLength={150} /></label>
      <button className="secondary-button">{t("Search")}</button>
    </form>
    <QueryState result={result}>{({ items, next_after }) => <>
      {items.length ? <ul className="iam-list">{items.map(option =>
        <li key={option.object_id}><button type="button" className="secondary-button" aria-pressed={selected?.object_id === option.object_id}
          disabled={!option.synchronized || (kind === "groups" && option.eligibility !== "eligible")}
          onClick={() => choose(option)}>{option.display_name ?? option.object_id}{option.email && ` · ${option.email}`}</button>
          {option.eligibility && <StatusBadge>{t(option.eligibility)}</StatusBadge>}</li>)}</ul> : <p>{t("No records.")}</p>}
      <div className="iam-actions">
        <button className="secondary-button" disabled={!pages.length} onClick={() => setPages(pages.slice(0, -1))}>{t("Previous page")}</button>
        <button className="secondary-button" disabled={next_after === null} onClick={() => next_after !== null && setPages([...pages, next_after])}>{t("Next page")}</button>
      </div>
    </>}</QueryState>
  </>;
}

function NewRequest({ session, close, completed }: { session: Session; close: () => void; completed: () => void }) {
  const [step, setStep] = useState(1);
  const [user, setUser] = useState<Option>();
  const [group, setGroup] = useState<Option>();
  const [employee, setEmployee] = useState<number>();
  const [groupId, setGroupId] = useState("");
  const [draft, setDraft] = useState<Draft>();
  const [preview, setPreview] = useState<Preview>();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const canRead = session.permissions.includes("entra:read");

  async function review(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (canRead ? !user || !group : !employee || !groupId.trim()) return;
    const values = new FormData(event.currentTarget);
    const payload: Draft = { ...(user ? { user_id: user.object_id } : { employee_id: employee! }),
      group_id: group?.object_id ?? groupId.trim(), add: values.get("operation") === "add", justification: String(values.get("justification")).trim() };
    setBusy(true); setError("");
    try {
      setPreview(await request<Preview>(`${endpoint}/preview`, { method: "POST", body: JSON.stringify(payload) }, session.token));
      setDraft(payload); setStep(3);
    } catch (cause) { setError(cause instanceof Error ? cause.message : t("Request failed.")); }
    finally { setBusy(false); }
  }

  async function submit() {
    if (!draft || !preview) return;
    setBusy(true); setError("");
    try {
      await request(`${endpoint}/requests`, { method: "POST", body: JSON.stringify({ ...draft, expected_snapshot_id: preview.snapshot_id }) }, session.token);
      completed();
    } catch (cause) { setError(cause instanceof Error ? cause.message : t("Request failed.")); }
    finally { setBusy(false); }
  }

  return <Drawer title={t("New request")} close={close}>
    <p>{step} / 3 · {t(step === 1 ? "Select employee" : step === 2 ? "Select group and action" : "Review and submit")}</p>
    {error && <p role="alert" className="enterprise-error">{t(error)}</p>}
    {step === 1 && <>
      {canRead ? <DirectoryPicker token={session.token} kind="users" selected={user} choose={setUser} /> :
        <label className="iam-form">{t("Employee ID")}<input required type="number" min={1} value={employee ?? ""} onChange={event => setEmployee(Number(event.target.value))} /></label>}
      <button className="primary-button" disabled={canRead ? !user : !employee || employee < 1} onClick={() => setStep(2)}>{t("Continue")}</button>
    </>}
    {step === 2 && <>
      {canRead && <DirectoryPicker token={session.token} kind="groups" selected={group} choose={setGroup} />}
      <form className="iam-form" onSubmit={review}>
        {!canRead && <label>{t("Entra group object ID")}<input value={groupId} onChange={event => setGroupId(event.target.value)} required maxLength={36} /></label>}
        <label>{t("Action")}<select name="operation" defaultValue={draft?.add === false ? "remove" : "add"}>
          <option value="add">{t("Add membership")}</option><option value="remove">{t("Remove membership")}</option>
        </select></label>
        <label>{t("Business justification")}<textarea name="justification" defaultValue={draft?.justification} required minLength={8} maxLength={1000} /></label>
        <div className="iam-actions">
          <button type="button" className="secondary-button" disabled={busy} onClick={() => setStep(1)}>{t("Back")}</button>
          <button className="primary-button" disabled={busy || (canRead && !group)}>{t("Preview change")}</button>
        </div>
      </form>
    </>}
    {step === 3 && draft && preview && <>
      <p>{t(draft.add ? "Add membership" : "Remove membership")} · {user?.display_name ?? preview.user_id} · {group?.display_name ?? preview.group_id}</p>
      <p>{draft.justification}</p>
      <p>{t("Membership in snapshot")} · {t(preview.expected ? "Present" : "Absent")}</p>
      <p>{t(preview.direct_authorized ? "Authorized administrator changes enter the execution queue directly." : "This request requires approval.")}</p>
      <div className="iam-actions">
        <button className="secondary-button" disabled={busy} onClick={() => setStep(2)}>{t("Back")}</button>
        <button className="primary-button" disabled={busy} onClick={() => void submit()}>{t("Submit request")}</button>
      </div>
    </>}
  </Drawer>;
}
