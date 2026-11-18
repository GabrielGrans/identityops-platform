import { useState, type FormEvent } from "react";
import { Feedback, Page, Pagination, Panel, QueryState } from "./common";
import { displayTime, PAGE_SIZE, useCursor, useMutation, useQuery, type Session } from "./data";

const campaignStatuses = ["draft", "active", "completed", "cancelled", "expired"] as const;
const itemStatuses = ["pending", "retained", "revoked", "superseded", "not_reviewed"] as const;
type Status = typeof campaignStatuses[number];
type ItemStatus = typeof itemStatuses[number];
type Action = "activate" | "complete" | "cancel" | "expire";

interface Campaign {
  id: number;
  name: string;
  description: string | null;
  owner_id: number;
  starts_on: string;
  due_on: string;
  status: Status;
  activated_at: string | null;
  closed_at: string | null;
}

interface CampaignDetails extends Campaign {
  reviewer_ids: number[];
  counts: Partial<Record<ItemStatus, number>>;
  can_decide: boolean;
  available_actions: Action[];
}

interface Item {
  id: number;
  employee_id: number;
  employee_name: string;
  group_id: number;
  group_name: string;
  status: ItemStatus;
  reviewer_id: number | null;
  justification: string | null;
  decided_at: string | null;
}

const actionPrompts: Record<Action, string> = {
  activate: "Activate and snapshot every active local employee–group membership?",
  complete: "Complete this campaign and lock its history?",
  cancel: "Cancel this campaign? Pending items will close without changing access.",
  expire: "Close this overdue campaign? Pending items will close without changing access.",
};

function reviewerIds(value: FormDataEntryValue | null) {
  return String(value ?? "").split(",").map((part) => Number(part.trim()));
}

export function CertificationPage({ session }: { session: Session }) {
  const { token, permissions } = session;
  const canManage = permissions.includes("certifications:manage");
  const operation = useMutation(token);
  const cursor = useCursor();
  const [status, setStatus] = useState("");
  const [selected, setSelected] = useState<number>();
  const list = useQuery<Campaign[]>(token,
    `/certification-campaigns?limit=${PAGE_SIZE}${cursor.query}${status ? `&status=${status}` : ""}`, operation.revision);

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    if (await operation.mutate("/certification-campaigns", "POST", {
      name: values.get("name"),
      description: values.get("description") || null,
      owner_id: Number(values.get("owner_id")),
      starts_on: values.get("starts_on"),
      due_on: values.get("due_on"),
      reviewer_ids: reviewerIds(values.get("reviewers")),
    })) {
      form.reset();
      cursor.reset();
      setStatus("");
    }
  }

  return <Page title="Access Certification">
    <div className="iam-actions">
      <button className="secondary-button" onClick={operation.refresh} disabled={operation.busy}>Refresh</button>
    </div>
    <Feedback message={operation.message} />
    {canManage && <Panel title="Create campaign">
      <form className="iam-form" onSubmit={(event) => void create(event)}>
        <label>Name<input name="name" required maxLength={120} /></label>
        <label>Description<textarea name="description" maxLength={2000} /></label>
        <label>Owner employee ID<input name="owner_id" type="number" min={1} max={2147483647} required defaultValue={session.employeeId} /></label>
        <label>Start date (UTC)<input name="starts_on" type="date" required /></label>
        <label>Due date (UTC)<input name="due_on" type="date" required /></label>
        <label>Reviewer employee IDs (comma-separated)<input name="reviewers" required defaultValue={session.employeeId} /></label>
        <button className="primary-button" disabled={operation.busy}>Create draft</button>
      </form>
    </Panel>}
    <Panel title="Campaigns">
      <label>Status<select aria-label="Campaign status" value={status} onChange={(event) => {
        setStatus(event.target.value);
        cursor.reset();
      }}>
        <option value="">All</option>
        {campaignStatuses.map((value) => <option key={value}>{value}</option>)}
      </select></label>
      <QueryState result={list}>{(campaigns) => <>
        {campaigns.length ? <ul className="iam-list">{campaigns.map((campaign) => <li key={campaign.id}>
          <div>
            <strong>{campaign.name}</strong>
            <p>{campaign.status} · {campaign.starts_on} to {campaign.due_on} (UTC)</p>
          </div>
          <button className="secondary-button" aria-pressed={selected === campaign.id}
            onClick={() => setSelected(campaign.id)}>Open campaign</button>
        </li>)}</ul> : <p>No campaigns to display.</p>}
        <Pagination rows={campaigns} cursor={cursor} />
      </>}</QueryState>
    </Panel>
    {selected !== undefined && <CampaignPanel key={selected} id={selected} session={session} operation={operation}
      onClose={() => setSelected(undefined)} />}
  </Page>;
}

function CampaignPanel({ id, session, operation, onClose }: {
  id: number; session: Session; operation: ReturnType<typeof useMutation>; onClose: () => void;
}) {
  const path = `/certification-campaigns/${id}`;
  const result = useQuery<CampaignDetails>(session.token, path, operation.revision, true);
  const [filter, setFilter] = useState("");
  const cursor = useCursor();
  const items = useQuery<Item[]>(session.token, result.data ?
    `${path}/items?limit=${PAGE_SIZE}${cursor.query}${filter ? `&status=${filter}` : ""}` : null, operation.revision);
  const canManage = session.permissions.includes("certifications:manage");

  return <Panel title={result.data?.name ?? "Campaign details"}>
    <button className="secondary-button" onClick={onClose}>Close details</button>
    <QueryState result={result}>{(campaign) => <>
      {campaign.description && <p>{campaign.description}</p>}
      <p>Owner #{campaign.owner_id} · {campaign.status} · {campaign.starts_on} to {campaign.due_on} (UTC)</p>
      <p>Reviewers {campaign.reviewer_ids.map((reviewer) => `#${reviewer}`).join(", ")}</p>
      {campaign.activated_at && <p>Activated {displayTime(campaign.activated_at)}</p>}
      {campaign.closed_at && <p>Closed {displayTime(campaign.closed_at)}</p>}

      {canManage && ["draft", "active"].includes(campaign.status) && <form key={campaign.reviewer_ids.join(",")}
        className="iam-form" onSubmit={(event) => {
          event.preventDefault();
          const ids = reviewerIds(new FormData(event.currentTarget).get("reviewers"));
          void operation.mutate(`${path}/reviewers`, "PUT", { reviewer_ids: ids });
        }}>
        <label>Assigned reviewer employee IDs<input name="reviewers" required defaultValue={campaign.reviewer_ids.join(", ")} /></label>
        <button className="secondary-button" disabled={operation.busy}>Update reviewers</button>
      </form>}

      {campaign.available_actions.length > 0 && <div className="iam-actions">
        {campaign.available_actions.map((action) => <button key={action} className="secondary-button" disabled={operation.busy}
          onClick={() => {
            if (window.confirm(actionPrompts[action])) void operation.mutate(`${path}/transition`, "POST", { action });
          }}>
          {action[0].toUpperCase() + action.slice(1)} campaign
        </button>)}
      </div>}

      <h3>Membership review items</h3>
      <p>{itemStatuses.map((status) => `${campaign.counts[status] ?? 0} ${status.replace("_", " ")}`).join(" · ")}</p>
      <label>Item status<select aria-label="Item status" value={filter} onChange={(event) => {
        setFilter(event.target.value);
        cursor.reset();
      }}>
        <option value="">All</option>
        {itemStatuses.map((status) => <option key={status} value={status}>{status.replace("_", " ")}</option>)}
      </select></label>
      <QueryState result={items}>{(rows) => <>
        {rows.length ? <ul className="iam-list">{rows.map((item) => <li key={item.id}>
          <div>
            <strong>{item.employee_name}</strong>
            <p>{item.group_name} · {item.status.replace("_", " ")}</p>
            {item.reviewer_id !== null && item.decided_at && <>
              <p>Reviewer #{item.reviewer_id} · {displayTime(item.decided_at)}</p>
              <p>{item.justification}</p>
            </>}
          </div>
          {item.status === "pending" && campaign.can_decide && (item.employee_id === session.employeeId
            ? <p>Another reviewer must certify your access.</p>
            : <DecisionForm busy={operation.busy} onDecision={(decision, justification) =>
              operation.mutate(`${path}/items/${item.id}/decision`, "POST", { decision, justification })} />)}
        </li>)}</ul> : <p>No items to display.</p>}
        <Pagination rows={rows} cursor={cursor} />
      </>}</QueryState>
    </>}</QueryState>
  </Panel>;
}

function DecisionForm({ busy, onDecision }: {
  busy: boolean; onDecision: (decision: string, justification: string) => Promise<boolean>;
}) {
  return <form className="iam-form" onSubmit={(event) => {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    const decision = String(values.get("decision"));
    if (decision === "revoked" && !window.confirm("Revoke this local group membership now?")) return;
    void onDecision(decision, String(values.get("justification")));
  }}>
    <label>Decision<select name="decision" aria-label="Decision" defaultValue="retained">
      <option value="retained">Retain</option>
      <option value="revoked">Revoke</option>
    </select></label>
    <label>Justification<textarea name="justification" required maxLength={1000} /></label>
    <button className="primary-button" disabled={busy}>Record decision</button>
  </form>;
}
