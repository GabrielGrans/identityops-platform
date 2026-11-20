import { useState } from "react";
import { t } from "../i18n";
import { Feedback, Page, Panel, QueryState } from "./common";
import { useMutation, useQuery, type Session } from "./data";

interface Alert {
  key: string;
  state: string;
  payload: {
    rule: string; identity: string; policy: string; evidence: unknown[];
    severity: string; recommended_action: string; employee_id: number | null;
    user_object_id?: string; group_ids?: string[];
  };
}

const endpoint = "/entra/automation";
const findingLabels: Record<string, string> = {
  unexpected_access: "Unexpected access", missing_access: "Missing required access",
  privileged_access: "Unauthorized privileged access", segregation_of_duties: "Segregation of duties conflicts",
  inactive_access: "Inactive identities retaining access", overdue_review: "Overdue access reviews",
  provisioning_failed: "Provisioning failed", expired_exception: "Expired access exception",
};

export function EntraGovernancePage({ session, notifications }: { session: Session; notifications: boolean }) {
  const operations = useMutation(session.token);
  const [unread, setUnread] = useState(false);
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<string>();
  const [error, setError] = useState("");
  const rolePolicy = useQuery<Record<string, unknown>>(session.token, notifications ? null : `${endpoint}/role-policy`, operations.revision);
  const alerts = useQuery<Alert[]>(session.token, notifications ?
    `${endpoint}/notifications?unread=${unread}&offset=${offset}` : null, operations.revision);
  const detail = useQuery<Alert[]>(session.token, selected ? `${endpoint}/notifications?key=${selected}` : null,
    operations.revision);
  const canEdit = session.permissions.includes("governance:manage");
  return <Page title={t(notifications ? "Notifications" : "Entra role governance")}>
    <Feedback message={operations.message} />
    {notifications ? <>
      {selected && <Panel title={t("Finding evidence")}>
        <button className="secondary-button" onClick={() => setSelected(undefined)}>{t("Close details")}</button>
        <QueryState result={detail}>{rows => rows.length ? <FindingDetails item={rows[0]} /> : <p>{t("No records.")}</p>}</QueryState>
      </Panel>}
      <Panel title={t("Governance and provisioning alerts")}>
        <div className="iam-actions">
          <label className="iam-checkbox"><input type="checkbox" checked={unread} onChange={event => {
            setUnread(event.target.checked); setOffset(0);
          }} />{t("Unread only")}</label>
          <button className="secondary-button" onClick={operations.refresh}>{t("Refresh")}</button>
        </div>
        <QueryState result={alerts}>{rows => <>
          {rows.length ? <ul className="iam-list">{rows.map(item => <li key={item.key}>
            <div>
              <strong>{t(findingLabels[item.payload.rule] ?? item.payload.rule)}</strong>
              <p>{t(item.payload.severity)} · {t(item.state)} · {item.payload.identity}</p>
              <p>{t(item.payload.recommended_action)}</p>
            </div>
            <div className="iam-actions">
              <button className="secondary-button" onClick={() => setSelected(item.key)}>{t("Investigate finding")}</button>
              {item.state === "unread" && <button className="secondary-button" disabled={operations.busy}
                onClick={() => void operations.mutate(`${endpoint}/notifications/${item.key}`, "PUT")}>{t("Acknowledge")}</button>}
            </div>
          </li>)}</ul> : <p>{t("No records.")}</p>}
          <div className="iam-actions">
            <button className="secondary-button" disabled={!offset} onClick={() => setOffset(offset - 50)}>{t("Previous page")}</button>
            <button className="secondary-button" disabled={rows.length < 50} onClick={() => setOffset(offset + 50)}>{t("Next page")}</button>
          </div>
        </>}</QueryState>
      </Panel>
    </> : <Panel title={t("Role-based access policy")}>
      <p>{t("Rules report findings. They do not grant or revoke access.")}</p>
      <p>{t("Role rules match job title, local department and local employment status. Use Entra object IDs for groups and exceptions.")}</p>
      <details><summary>{t("Policy format")}</summary>
        <pre>{JSON.stringify({ review_days: 30, roles: [{ name: "", job_title: "", entra_department: "", department_id: null,
          employment_status: "", approved: [], required: [], privileged: [], forbidden: [],
          exceptions: [{ user_id: "", group_id: "", until: "YYYY-MM-DD" }] }] }, null, 2)}</pre>
      </details>
      {error && <p role="alert">{error}</p>}
      <QueryState result={rolePolicy}>{policy => <form key={operations.revision} className="iam-form" onSubmit={event => {
        event.preventDefault();
        try {
          const body = JSON.parse(String(new FormData(event.currentTarget).get("policy")));
          setError("");
          void operations.mutate(`${endpoint}/role-policy`, "PUT", body);
        } catch { setError(t("Enter a valid JSON policy.")); }
      }}>
        <label>{t("Role-based access policy")}<textarea rows={14} name="policy" readOnly={!canEdit} required
          defaultValue={JSON.stringify(policy, null, 2)} /></label>
        {canEdit && <button className="primary-button" disabled={operations.busy}>{t("Save policy")}</button>}
      </form>}</QueryState>
    </Panel>}
  </Page>;
}

function FindingDetails({ item }: { item: Alert }) {
  return <>
    <strong>{t(findingLabels[item.payload.rule] ?? item.payload.rule)}</strong>
    <dl>
      <dt>{t("Identity")}</dt><dd>{item.payload.user_object_id ?
        <a href={`#entra/users/${item.payload.user_object_id}`}>{item.payload.identity}</a> : item.payload.identity}</dd>
      {!!item.payload.group_ids?.length && <><dt>{t("Groups")}</dt><dd>{item.payload.group_ids.map(id =>
        <p key={id}><a href={`#entra/groups/${id}`}>{id}</a></p>)}</dd></>}
      <dt>{t("Policy")}</dt><dd>{t(item.payload.policy)}</dd>
      <dt>{t("Current evidence")}</dt><dd><pre>{JSON.stringify(item.payload.evidence, null, 2)}</pre></dd>
      <dt>{t("Recommended action")}</dt><dd>{t(item.payload.recommended_action)}</dd>
    </dl>
  </>;
}
