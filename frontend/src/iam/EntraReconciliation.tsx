import { t } from "../i18n";
import { useState } from "react";
import { ApiError, request } from "../services/api";
import { Panel } from "./common";
import { type CatalogItem, type Session, useQuery } from "./data";

export type Selection = {
  object_id: string;
  display_name: string | null;
};

type Item = {
  object_id: string;
  action: "create" | "link";
  local_employee_id?: number;
  department_id?: number;
  employee_number?: string;
  first_name?: string;
  last_name?: string;
  job_title?: string;
  person_verified: boolean;
};
type Proposal = Partial<Record<"employee_number" | "first_name" | "last_name" | "job_title" | "email" | "department_id", string | number | null>>;
type Outcome = {
  object_id: string; status: string; action: Item["action"]; proposal: Proposal | null;
  messages: string[]; matching_employee_ids: number[]; local_employee_id: number | null;
};
type Result = { snapshot_run_id: number | null; applied: boolean; items: Outcome[] };

const labels: Record<string, string> = {
  already_linked: "Already linked",
  eligible_for_creation: "Ready to create",
  eligible_for_link: "Ready to link",
  potential_duplicate: "Potential duplicate",
  missing_required_data: "Required data missing",
  unsupported_identity_type: "Unsupported identity type",
  unavailable_snapshot: "Snapshot unavailable or out of date",
  validation_conflict: "Conflict",
  created: "Created and linked",
  linked: "Linked",
};
const fields = [
  ["employee_number", "Employee number"], ["first_name", "First name"],
  ["last_name", "Last name"], ["job_title", "Job title"],
] as const;

function reconciliationMessage(message: string) {
  const fields = message.match(/^Supply valid employee fields: (.+)\.$/);
  if (!fields) return t(message);
  const names = new Map<string, string>(fieldsForDisplay);
  return t("Supply valid employee fields: {fields}.", {
    fields: fields[1].split(", ").map(field => t(names.get(field) ?? field)).join(", "),
  });
}

const fieldsForDisplay: readonly (readonly [string, string])[] = [
  ...fields, ["email", "Email"], ["department_id", "Department ID"],
];

export function EntraReconciliation({ selected, session, canCreate, onComplete, remove }: {
  selected: Selection[]; session: Session; canCreate: boolean; onComplete: () => void; remove: (id: string) => void;
}) {
  const [edits, setEdits] = useState<Record<string, Partial<Item>>>({});
  const [result, setResult] = useState<Result>();
  const [reviewedItems, setReviewedItems] = useState("");
  const [working, setWorking] = useState<"preview" | "apply">();
  const [error, setError] = useState("");
  const departments = useQuery<CatalogItem[]>(session.token, session.permissions.includes("departments:read") ? "/departments" : null);
  const items: Item[] = selected.map(({object_id}) => ({
    object_id, action: canCreate ? "create" : "link", person_verified: false, ...edits[object_id],
  }));
  const activeDepartments = departments.data?.filter(department => department.is_active) ?? [];

  function edit(id: string, change: Partial<Item>, replace = false) {
    if (Object.keys(change).some(field => field !== "person_verified")) setReviewedItems("");
    setEdits(previous => ({ ...previous, [id]: { ...(replace ? {} : previous[id]), ...change } }));
  }

  const signature = JSON.stringify(items.map(item => ({ ...item, person_verified: false })));
  async function submit(mode: "preview" | "apply") {
    if (mode === "apply" && !window.confirm(
      t("Apply this batch locally? {p0} inactive employees will be created and {p1} existing employees linked. Microsoft Entra will not be changed.", { p0: String(creations), p1: String(links) })
    )) return;
    setWorking(mode);
    setReviewedItems("");
    setError("");
    const payload = mode === "apply" ? { items, confirmed: true, snapshot_run_id: result?.snapshot_run_id } : { items };
    try {
      const response = await request<Result>(`/entra/reconciliation/${mode}`, {
        method: "POST", body: JSON.stringify(payload),
      }, session.token);
      setResult(response);
      setReviewedItems(mode === "preview" ? signature : "");
      if (response.applied) onComplete();
    } catch (cause) {
      setError(cause instanceof ApiError && cause.status === 403 ?
        t("Your account does not have the required reconciliation permissions.") :
        t("Reconciliation could not be completed. Check the selected fields and preview again."));
    } finally {
      setWorking(undefined);
    }
  }

  const creations = result?.items.filter(item => item.status === "eligible_for_creation").length ?? 0;
  const links = result?.items.filter(item => item.status === "eligible_for_link").length ?? 0;
  const reviewed = reviewedItems === signature;
  const ready = reviewed && !!result?.snapshot_run_id && creations + links > 0 &&
    result.items.every(item => ["eligible_for_creation", "eligible_for_link", "already_linked"].includes(item.status)) &&
    items.every(item => item.person_verified || result.items.some(row => row.object_id === item.object_id && row.status === "already_linked"));

  return <Panel title={t("Reconcile selected users ({p0}/25)", { p0: String(selected.length) })}>
    <p>{t("Preview the batch before applying. New local employees start inactive, without a password or group memberships.")}</p>
    {error && <p role="alert">{error}</p>}
    {working && <p role="status">{working === "preview" ? t("Checking selected identities…") : t("Applying the local batch…")}</p>}
    {result && !reviewed && !working && !result.applied && <p>{t("Preview again before applying changes.")}</p>}
    <fieldset disabled={!!working} className="entra-reconciliation">
      <legend>{t("Selected identities")}</legend>
      {items.map((item, index) => {
        const outcome = result?.items.find(row => row.object_id === item.object_id);
        const entry = selected[index];
        return <section key={item.object_id} className="iam-panel">
          <div>
            <strong>{entry.display_name ?? item.object_id}</strong>
            {entry.display_name && <p>{item.object_id}</p>}
          </div>
          <div className="iam-form">
            <label>{t("Local action")}<select value={item.action} onChange={event =>
              edit(item.object_id, { action: event.target.value as Item["action"], person_verified: item.person_verified }, true)}>
              {canCreate && <option value="create">{t("Create inactive employee")}</option>}
              <option value="link">{t("Link an existing employee")}</option>
            </select></label>
            {item.action === "create" ? <>
              {fields.map(([key, label]) => <label key={key}>{t(label)}
                <input maxLength={key === "employee_number" ? 30 : key === "job_title" ? 120 : 100}
                  value={item[key] ?? ""} placeholder={String(outcome?.proposal?.[key] ?? "")}
                  onChange={event => edit(item.object_id, { [key]: event.target.value || undefined })} />
              </label>)}
              {departments.data && <label>{t("Department")}<select value={item.department_id ?? ""} onChange={event =>
                edit(item.object_id, { department_id: event.target.value ? Number(event.target.value) : undefined })}>
                <option value="">{t("No department")}</option>
                {activeDepartments.map(dept => <option key={dept.id} value={dept.id}>{dept.name}</option>)}
              </select></label>}
              {departments.error && <p role="alert">{t("Departments could not be loaded.")}</p>}
            </> : <label>{t("Existing employee ID")}
              <input type="number" min={1} max={2147483647} value={item.local_employee_id ?? ""}
                onChange={event => edit(item.object_id, { local_employee_id: event.target.value ? Number(event.target.value) : undefined })} />
            </label>}
            <label className="entra-attestation"><input type="checkbox" checked={item.person_verified}
              onChange={event => edit(item.object_id, { person_verified: event.target.checked })} />{" "}{t("I verified this account belongs to a person")}</label>
            <button className="secondary-button" onClick={() => {setReviewedItems(""); remove(item.object_id);}}>{t("Remove selection")}</button>
          </div>
          {outcome && <>
            <p><strong>{t(labels[outcome.status] ?? outcome.status)}</strong>{outcome.local_employee_id && t(" · Employee #{p0}", { p0: String(outcome.local_employee_id) })}</p>
            {outcome.action === "create" && outcome.proposal && <p>
              {[outcome.proposal.employee_number, outcome.proposal.first_name, outcome.proposal.last_name,
                outcome.proposal.job_title, outcome.proposal.email].filter(Boolean).join(" · ")}
              {outcome.proposal.department_id ? t(" · Department #{p0}", { p0: String(outcome.proposal.department_id) }) : t(" · No department")}
            </p>}
            {outcome.matching_employee_ids.length > 0 && <p>{t("Matching employee IDs:")}{" "}{outcome.matching_employee_ids.join(", ")}</p>}
            {outcome.messages.map(message => <p key={message}>{reconciliationMessage(message)}</p>)}
          </>}
        </section>;
      })}
    </fieldset>
    <div className="iam-actions">
      <button className="secondary-button" disabled={!!working} onClick={() => void submit("preview")}>{t("Preview batch")}</button>
      <button className="primary-button" disabled={!ready || !!working} onClick={() => void submit("apply")}>{t("Confirm local changes")}</button>
    </div>
    {reviewed && <p role="status">{creations}{" "}{t("to create ·")}{" "}{links}{" "}{t("to link. Conflicts block the entire batch.")}</p>}
    {result?.applied && <p role="status">{t("Local reconciliation completed. Open Employees to see the refreshed directory.")}</p>}
    {result && !reviewed && !result.applied && <p>{t("No employee records or links were changed.")}</p>}
  </Panel>;
}
