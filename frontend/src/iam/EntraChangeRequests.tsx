import { useState } from "react";
import { t } from "../i18n";
import { request } from "../services/api";
import { Feedback, Panel, QueryState } from "./common";
import { displayTime, provisioningStatus, useMutation, useQuery, type Session } from "./data";

const endpoint = "/entra/automation";
const errors: Record<string, string> = {
  graph_throttled: "Microsoft throttled the request. Try again later.",
  graph_unavailable: "Microsoft was temporarily unavailable.",
  graph_unauthorized: "Microsoft Graph rejected the application token.",
  graph_forbidden: "Microsoft Graph denied this operation.",
  membership_forbidden: "Microsoft Graph refused group membership access.",
  invalid_response: "Microsoft returned data that could not be validated.",
  write_conflict: "The current membership differs from the approved preview.",
  write_unsupported: "This group does not support controlled provisioning.",
};
interface Draft {
  employee_id: number; group_id: string; add: boolean; justification: string;
}
interface Preview { user_id: string; group_id: string; expected: boolean; snapshot_id: number; direct_authorized: boolean }
interface Change {
  id: number; employee_id: number | null; user_object_id: string; error_code: string | null; requester_id: number; status: string; expires_at: string;
  request: Preview & Draft;
}

export function EntraChangeRequests({ session }: { session: Session }) {
  const canRequest = session.permissions.includes("entra:request_change");
  const canApprove = session.permissions.includes("entra:approve_change");
  const allowed = canRequest || canApprove;
  const mutation = useMutation(session.token);
  const [proposal, setProposal] = useState<{draft: Draft; preview: Preview}>();
  const [previewBusy, setPreviewBusy] = useState(false);
  const [error, setError] = useState("");
  const [cursors, setCursors] = useState<number[]>([]);
  const before = cursors.at(-1);
  const rows = useQuery<Change[]>(session.token, allowed ? `${endpoint}/requests${before ? `?before_id=${before}` : ""}` : null,
    mutation.revision);
  if (!allowed) return null;
  return <Panel title={t("Administrative Entra requests")}>
    <Feedback message={mutation.message} />
    {error && <p role="alert">{error}</p>}
    {canRequest && <form className="iam-form" onChange={() => setProposal(undefined)} onSubmit={async event => {
      event.preventDefault();
      const form = new FormData(event.currentTarget);
      const draft = {
        employee_id: Number(form.get("employee")), group_id: String(form.get("group")).trim(),
        add: form.get("operation") === "add", justification: String(form.get("justification")).trim(),
      };
      setError("");
      setProposal(undefined);
      setPreviewBusy(true);
      try {
        const preview = await request<Preview>(`${endpoint}/preview`, {
          method: "POST", body: JSON.stringify(draft),
        }, session.token);
        setProposal({ draft, preview });
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : t("Request failed."));
      } finally { setPreviewBusy(false); }
    }}>
      <fieldset disabled={previewBusy || mutation.busy} className="iam-form">
        <label>{t("Employee ID")}<input name="employee" required type="number" min={1} /></label>
        <label>{t("Entra group object ID")}<input name="group" required maxLength={36} /></label>
        <label>{t("Action")}<select name="operation">
          <option value="add">{t("Add membership")}</option>
          <option value="remove">{t("Remove membership")}</option>
        </select></label>
        <label>{t("Business justification")}<textarea name="justification" required minLength={8} maxLength={1000} /></label>
        <button className="secondary-button">{t("Preview change")}</button>
      </fieldset>
    </form>}
    {proposal && <section aria-label={t("Preview change")}>
      <p>{t(proposal.draft.add ? "Add membership" : "Remove membership")} · {t("Employee ID")} #{proposal.draft.employee_id}</p>
      <p>{t("Entra group object ID")}: {proposal.preview.group_id} · {t("Snapshot ID")} #{proposal.preview.snapshot_id}</p>
      <p>{t("Membership in snapshot")}: {t(proposal.preview.expected ? "Present" : "Absent")}</p>
      {proposal.preview.direct_authorized && <p>{t("Authorized administrator changes enter the execution queue directly.")}</p>}
      <button className="primary-button" disabled={mutation.busy} onClick={async () => {
        if (await mutation.mutate(`${endpoint}/requests`, "POST", {
          ...proposal.draft, expected_snapshot_id: proposal.preview.snapshot_id,
        })) { setProposal(undefined); setCursors([]); }
      }}>{t("Submit request")}</button>
    </section>}
    <QueryState result={rows}>{items => <>
      {items.length === 0 && <p>{t("No records.")}</p>}
      <ul className="iam-list">{items.map(item => <li key={item.id}>
        <div>
          <strong>#{item.id} · {provisioningStatus(item.status)} · {t(item.request.add ? "Add membership" : "Remove membership")}</strong>
          <p>{item.employee_id ? `${t("Employee ID")} #${item.employee_id}` :
            <a href={`#entra/users/${item.user_object_id}`}>{item.user_object_id}</a>} · {item.request.group_id}</p>
          {item.error_code && <p role="status">{t(errors[item.error_code] ?? item.error_code)}</p>}
          <p>{item.request.justification}</p>
          <p>{t("Membership in snapshot")}: {t(item.request.expected ? "Present" : "Absent")} · {t("Expires at")}: {displayTime(item.expires_at)}</p>
        </div>
        {canApprove && item.status === "pending" && item.employee_id !== session.employeeId &&
          item.requester_id !== session.employeeId && new Date(item.expires_at) > new Date() &&
          <form className="iam-form" onSubmit={event => {
            event.preventDefault();
            const form = new FormData(event.currentTarget);
            void mutation.mutate(`${endpoint}/requests/${item.id}/decision`, "POST", {
              approve: form.get("decision") === "approve", note: String(form.get("note")),
            });
          }}>
            <label>{t("Decision")}<select name="decision">
              <option value="approve">{t("Approve")}</option>
              <option value="reject">{t("Reject")}</option>
            </select></label>
            <label>{t("Decision note")}<input name="note" required minLength={8} maxLength={1000} /></label>
            <button className="primary-button" disabled={mutation.busy}>{t("Record decision")}</button>
          </form>}
      </li>)}</ul>
      <div className="iam-actions">
        <button className="secondary-button" disabled={!before} onClick={() => setCursors(cursors.slice(0, -1))}>{t("Previous page")}</button>
        <button className="secondary-button" disabled={items.length < 50} onClick={() => setCursors([...cursors, items[49].id])}>{t("Next page")}</button>
        <button className="secondary-button" onClick={mutation.refresh}>{t("Refresh")}</button>
      </div>
    </>}</QueryState>
  </Panel>;
}
