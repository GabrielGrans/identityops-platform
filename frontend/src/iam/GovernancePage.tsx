import { useState } from "react";
import { t } from "../i18n";
import { Feedback, Page, Panel, QueryState } from "./common";
import { useMutation, useQuery, type Session } from "./data";

const rules: Record<string, string> = {
  excessive_permissions: "Excessive permissions",
  privileged_access: "Unauthorized privileged access",
  inactive_access: "Inactive identities retaining access",
  entra_mismatch: "Local and Entra access mismatch",
  overdue_review: "Overdue access reviews",
  segregation_of_duties: "Segregation of duties conflicts",
};
const evidenceLabels: Record<string, string> = {
  count: "Permission count", limit: "Policy limit", group_id: "Group ID", group_ids: "Group IDs",
  review_id: "Review ID", opened_at: "Opened at", max_age_days: "Maximum age (days)",
  permission_codes: "Permission codes", snapshot_id: "Snapshot ID",
  local_only_group_ids: "Local only", entra_only_group_ids: "Entra only",
};

interface Policy {
  max_permissions: number | null;
  review_max_age_days: number;
  privileged_groups: { group_id: number; allowed_employee_ids: number[] }[];
  conflicts: [string, string][];
}

interface Findings {
  counts: Record<string, number>;
  entra_state: string;
  evaluated_rules: string[];
  total: number;
  items: { rule: string; employee_id: number; evidence: Record<string, string | number | number[]> }[];
}

export function RiskIndicators({ token, onOpen }: { token: string; onOpen?: () => void }) {
  const result = useQuery<Findings>(token, "/governance/findings?limit=1");
  if (result.errorStatus === 403) return null;
  return <Panel title={t("Governance findings")}>
    <QueryState result={result}>{report => <>
      <div className="finding-counts">{Object.entries(rules).map(([key, label]) => <div key={key}>
        <strong>{report.evaluated_rules.includes(key) ? report.counts[key] ?? 0 : "—"}</strong>
        <span>{t(label)}</span>
      </div>)}</div>
      <p>{t("A dash means the rule was not evaluated.")}</p>
      {onOpen && <button className="secondary-button" onClick={onOpen}>{t("View findings")}</button>}
    </>}</QueryState>
  </Panel>;
}

export function GovernancePage({ session }: { session: Session }) {
  const mutation = useMutation(session.token);
  const [offset, setOffset] = useState(0);
  const report = useQuery<Findings>(session.token, `/governance/findings?offset=${offset}`, mutation.revision);
  const policy = useQuery<Policy>(session.token, "/governance/policy", mutation.revision);
  const canManage = session.permissions.includes("governance:manage");
  return <Page title={t("Governance findings")}>
    <Feedback message={mutation.message} />
    {canManage && <QueryState result={policy}>{data =>
      <PolicyForm key={mutation.revision} policy={data} busy={mutation.busy}
        save={next => { setOffset(0); void mutation.mutate("/governance/policy", "PUT", next); }} />
    }</QueryState>}
    <Panel title={t("Current evidence")}>
      <QueryState result={report}>{data => <>
        {data.entra_state !== "evaluated" && <p>{t("Entra comparison requires directory access and a recent synchronization.")}</p>}
        {data.items.length ? <ul className="iam-list">{data.items.map((item, index) => <li key={offset + index}>
          <div>
            <strong>{t(rules[item.rule] ?? item.rule)}</strong>
            <p>{t("Employee ID")}: {item.employee_id}</p>
            <dl>{Object.entries(item.evidence).map(([key, value]) => <div key={key}>
              <dt>{t(evidenceLabels[key] ?? key)}</dt>
              <dd>{Array.isArray(value) ? value.join(", ") || "—" : value}</dd>
            </div>)}</dl>
          </div>
        </li>)}</ul> : <p>{t("No findings for the current policy.")}</p>}
        <div className="iam-actions">
          <button className="secondary-button" disabled={!offset} onClick={() => setOffset(offset - 25)}>{t("Previous page")}</button>
          <button className="secondary-button" disabled={offset + 25 >= data.total} onClick={() => setOffset(offset + 25)}>{t("Next page")}</button>
          <button className="secondary-button" onClick={mutation.refresh}>{t("Refresh")}</button>
        </div>
      </>}</QueryState>
    </Panel>
  </Page>;
}

function PolicyForm({ policy, busy, save }: { policy: Policy; busy: boolean; save: (policy: Policy) => void }) {
  const [error, setError] = useState(false);
  return <Panel title={t("Detection policy")}>
    <p>{t("Rules report findings. They do not grant or revoke access.")}</p>
    <form className="iam-form" onSubmit={event => {
      event.preventDefault();
      const fields = new FormData(event.currentTarget);
      const lines = (name: string) => String(fields.get(name)).split("\n").map(line => line.trim()).filter(Boolean);
      const privileged_groups = lines("privileged").map(line => {
        const [id, allowed = ""] = line.split(":");
        return { group_id: Number(id), allowed_employee_ids: allowed.split(",").map(value => value.trim()).filter(Boolean).map(Number) };
      });
      const conflicts = lines("conflicts").map(line => line.split(",").map(code => code.trim()));
      const valid = lines("privileged").every(line => /^\d+\s*:\s*(\d+(\s*,\s*\d+)*)?$/.test(line)) &&
        conflicts.every(pair => pair.length === 2 && pair.every(Boolean));
      setError(!valid);
      if (valid) save({
        max_permissions: Number(fields.get("max")) || null,
        review_max_age_days: Number(fields.get("age")),
        privileged_groups, conflicts: conflicts as [string, string][],
      });
    }}>
      <label>{t("Maximum effective permissions")}<input name="max" type="number" min={1} max={10000}
        defaultValue={policy.max_permissions ?? ""} /></label>
      <label>{t("Pending review age (days)")}<input name="age" type="number" min={1} max={365} required
        defaultValue={policy.review_max_age_days} /></label>
      <label>{t("Privileged groups: group ID: allowed employee IDs")}<textarea name="privileged"
        defaultValue={policy.privileged_groups.map(row => `${row.group_id}: ${row.allowed_employee_ids.join(", ")}`).join("\n")} /></label>
      <label>{t("Conflicts: one comma-separated pair of permission codes per line")}<textarea name="conflicts"
        defaultValue={policy.conflicts.map(pair => pair.join(", ")).join("\n")} /></label>
      {error && <p role="alert">{t("Check the rule format before saving.")}</p>}
      <button className="primary-button" disabled={busy}>{t("Save policy")}</button>
    </form>
  </Panel>;
}
