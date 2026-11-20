import { useEffect, useState } from "react";
import { t } from "../i18n";
import EmployeesPage from "../EmployeesPage";
import { request } from "../services/api";
import { CatalogPage } from "./CatalogPage";
import { DataTable, Drawer, Feedback, Page, Panel, QueryState, StatusBadge } from "./common";
import { provisioningStatus, useMutation, useQuery, type Session } from "./data";

type Kind = "users" | "groups";
type User = {
  object_id: string; display_name: string | null; email: string | null; job_title: string | null;
  department: string | null; synchronized: boolean; account_enabled: boolean | null;
  profile_authority: "external" | "unknown" | "cloud_candidate";
};
type Group = {
  object_id: string; display_name: string | null; description: string | null;
  membership_count: number; eligibility: "eligible" | "protected" | "unsupported"; synchronized: boolean;
};
type Pending = { id: number; user_object_id: string; group_object_id: string; status: string };
type Result<T> = { items: T[]; next_after: number | null };
type Finding = { key: string; payload: { rule: string; recommended_action: string; evidence: unknown[]; group_ids?: string[] } };
type UserDetails = User & { groups: Group[]; pending: Pending[]; findings: Finding[] };
type GroupDetails = Group & { members: Result<User>; pending: Pending[] };
const api = "/entra/directory";
const governance = "/entra/automation";

function link(kind: Kind, objectId: string) {
  return `#entra/${kind}/${objectId}`;
}

function selectedObject(kind: Kind) {
  const match = location.hash.match(/^#entra\/(users|groups)\/([a-f0-9-]{36})$/i);
  return match?.[1] === kind ? match[2] : undefined;
}

function useDirectoryRefresh() {
  const [revision, setRevision] = useState(0);
  return [revision, () => setRevision(current => current + 1)] as const;
}

export function DirectoryWorkspace({ kind, session }: { kind: Kind; session: Session }) {
  const canReadEntra = session.permissions.includes("entra:read");
  const canReadLocal = session.permissions.includes(kind === "users" ? "employees:read" : "groups:read");
  const status = useQuery<{ state: string }>(session.token, canReadEntra ? "/entra/status" : null);
  const [view, setView] = useState<"entra" | "local" | undefined>(() =>
    location.hash === `#local/${kind}` && canReadLocal ? "local" :
    location.hash === `#entra/${kind}` && canReadEntra ? "entra" : undefined);
  const [objectId, setObjectId] = useState(() => selectedObject(kind));
  useEffect(() => {
    const changed = () => {
      const object = selectedObject(kind);
      setObjectId(object);
      if (object) setView("entra");
    };
    window.addEventListener("hashchange", changed);
    return () => window.removeEventListener("hashchange", changed);
  }, [kind]);
  const active = view ?? (canReadEntra && (objectId || !canReadLocal || status.data && status.data.state !== "disabled") ? "entra" : "local");
  if (!canReadEntra && !canReadLocal) return <Page title={t(kind === "users" ? "Employees" : "Access Groups")}>
    <p role="alert">{t("Your account does not have permission to open this module.")}</p>
  </Page>;
  return <>
    {canReadEntra && canReadLocal && <div className="iam-actions directory-source" role="group" aria-label={t("Directory source")}>
      <button className="secondary-button" aria-pressed={active === "entra"} onClick={() => setView("entra")}>Microsoft Entra ID</button>
      <button className="secondary-button" aria-pressed={active === "local"} onClick={() => setView("local")}>{t("Local IdentityOps")}</button>
    </div>}
    {active === "entra" && canReadEntra ? <RemoteDirectory kind={kind} session={session} objectId={objectId} close={() => { history.replaceState(null, "", `#entra/${kind}`); setObjectId(undefined); }} />
      : kind === "users" ? <EmployeesPage token={session.token} employeeId={session.employeeId} />
      : <CatalogPage catalog="groups" session={session} />}
  </>;
}

function RemoteDirectory({ kind, session, objectId, close }: { kind: Kind; session: Session; objectId?: string; close: () => void }) {
  const [revision, refresh] = useDirectoryRefresh();
  return <Page title={t(kind === "users" ? "Employees" : "Access Groups")}>
    {objectId && <DirectoryDetails key={objectId} kind={kind} session={session}
      objectId={objectId} revision={revision} refresh={refresh} close={close} />}
    <Panel title={t(kind === "users" ? "Entra employees" : "Entra security groups")}>
      <div className="iam-actions"><button className="secondary-button" onClick={refresh}>{t("Refresh")}</button></div>
      {kind === "users" ? <SearchRows<User> token={session.token} path={`${api}/users`} revision={revision} accountFilter
        label={t("Search name, email, job title or department")} columns={[
          { label: t("Employee"), render: user => <a href={link("users", user.object_id)}>{user.display_name ?? user.object_id}</a> },
          { label: t("Corporate email"), render: user => user.email ?? "—" },
          { label: t("Department"), render: user => user.department ?? "—" },
          { label: t("Job title"), render: user => user.job_title ?? "—" },
          { label: t("Status"), render: user => <StatusBadge>{t(!user.synchronized ? "Absent from snapshot" : user.account_enabled == null ? "Account status unavailable" : user.account_enabled ? "Active" : "Inactive")}</StatusBadge> },
        ]} />
        : <SearchRows<Group> token={session.token} path={`${api}/groups`} revision={revision}
          label={t("Search groups")} columns={[
            { label: t("Group"), render: group => <a href={link("groups", group.object_id)}>{group.display_name ?? group.object_id}</a> },
            { label: t("Description"), render: group => group.description ?? "—" },
            { label: t("Direct members"), render: group => group.membership_count },
            { label: t("Status"), render: group => <StatusBadge>{t(!group.synchronized ? "Absent from snapshot" : group.eligibility)}</StatusBadge> },
          ]} />}
    </Panel>
  </Page>;
}

function SearchRows<T extends {object_id: string}>({ token, path, revision, label, render, columns, accountFilter, members = false }: {
  token: string; path: string; revision: number; label: string; render?: (row: T) => React.ReactNode; columns?: { label: string; render: (row: T) => React.ReactNode }[]; accountFilter?: boolean; members?: boolean;
}) {
  const [term, setTerm] = useState("");
  const [account, setAccount] = useState("");
  const [cursors, setCursors] = useState<number[]>([]);
  const params = new URLSearchParams({query: term, limit: "25"});
  if (account) params.set("account", account);
  if (cursors.length) params.set("after", String(cursors.at(-1)));
  const result = useQuery<Result<T> | { members: Result<T> }>(token, `${path}?${params}`, revision, true);
  return <>
    <form className="iam-form" onSubmit={event => {
      event.preventDefault();
      setCursors([]);
      setTerm(String(new FormData(event.currentTarget).get("query") ?? "").trim());
    }}>
      <label>{label}<input name="query" type="search" maxLength={150} /></label>
      {accountFilter && <label>{t("Account status")}<select value={account} onChange={event => {
        setAccount(event.target.value); setCursors([]);
      }}>
        <option value="">{t("All statuses")}</option>
        {["active", "disabled", "unknown"].map(value => <option key={value} value={value}>{t(value)}</option>)}
      </select></label>}
      <button className="secondary-button">{t("Search")}</button>
    </form>
    <QueryState result={result}>{value => {
      const data = members && "members" in value ? value.members : value as Result<T>;
      return <>
        {columns ? <DataTable label={label} rows={data.items} rowKey={item => item.object_id} columns={columns} /> :
          data.items.length ? <ul className="iam-list">{data.items.map(item => <li key={item.object_id}>{render?.(item)}</li>)}</ul>
          : <p>{t("No records.")}</p>}
        <div className="iam-actions">
          <button className="secondary-button" disabled={!cursors.length}
            onClick={() => setCursors(cursors.slice(0, -1))}>{t("Previous page")}</button>
          <button className="secondary-button" disabled={data.next_after === null}
            onClick={() => data.next_after !== null && setCursors([...cursors, data.next_after])}>{t("Next page")}</button>
        </div>
      </>;
    }}</QueryState>
  </>;
}

function Badge({ children }: { children: React.ReactNode }) {
  return <span className="directory-badge">{children}</span>;
}

function UserRow({ user }: { user: User }) {
  return <div>
    <a href={link("users", user.object_id)}>{user.display_name ?? user.object_id}</a>
    <p>{user.email || "—"} · {user.job_title || "—"} · {user.department || "—"}</p>
    <div className="iam-actions">
      <Badge>Entra ID</Badge>
      <Badge>{t(user.synchronized ? "Synchronized" : "Absent from snapshot")}</Badge>
      <Badge>{t(user.account_enabled === null ? "Account status unavailable" : user.account_enabled ? "Active" : "Inactive")}</Badge>
    </div>
  </div>;
}

function GroupRow({ group }: { group: Group }) {
  return <div>
    <a href={link("groups", group.object_id)}>{group.display_name ?? group.object_id}</a>
    {group.description && <p>{group.description}</p>}
    <div className="iam-actions">
      <Badge>Entra ID</Badge>
      <Badge>{t(group.synchronized ? "Synchronized" : "Absent from snapshot")}</Badge>
      <Badge>{t(group.eligibility === "eligible" ? "Approval required" : group.eligibility === "protected" ? "Protected group" : "Unsupported operation")}</Badge>
      <Badge>{t("Direct members")}: {group.membership_count}</Badge>
    </div>
  </div>;
}

function DirectoryDetails({ kind, session, objectId, revision, refresh, close }: {
  kind: Kind; session: Session; objectId: string; revision: number; refresh: () => void; close: () => void;
}) {
  const [target, setTarget] = useState<{ user: User; group: Group; add: boolean }>();
  const [catalog, setCatalog] = useState(false);
  const details = useQuery<UserDetails | GroupDetails>(session.token, `${api}/${kind}/${objectId}`, revision, true);
  const canRequest = session.permissions.includes("entra:request_change");
  return <Drawer title={t(kind === "users" ? "User details and access" : "Group members")} close={close}>
    <QueryState result={details}>{row => <>
      {row.pending.map(change => <p key={change.id}><Badge>{t("Pending change")}</Badge> #{change.id} · {provisioningStatus(change.status)}</p>)}
      {"groups" in row ? <>
        <UserRow user={row} />
        <p>{t("Profile source")}: {t(row.profile_authority === "external" ? "Synchronized from on-premises" :
          row.profile_authority === "cloud_candidate" ? "Cloud account; attribute authority unverified" : "Profile authority unknown")}</p>
        <Badge>{t("Profile editing unavailable")}</Badge>
        <h3>{t("Direct Entra memberships")}</h3>
        <SearchRows<Group> token={session.token} path={`${api}/users/${row.object_id}/groups`} revision={revision}
          label={t("Search groups")} render={group => <><GroupRow group={group} />
          {canRequest && group.eligibility === "eligible" && group.synchronized &&
            <button className="secondary-button" onClick={() => setTarget({user: row, group, add: false})}>{t("Remove membership")}</button>}</>} />
        {canRequest && row.synchronized && row.account_enabled === true &&
          <button className="secondary-button" onClick={() => setCatalog(!catalog)}>{t("Search groups to assign")}</button>}
        {catalog && <SearchRows<Group> token={session.token} path={`${api}/groups`} revision={revision}
          label={t("Search groups")} render={group => <><GroupRow group={group} />
          {group.eligibility === "eligible" && group.synchronized && !row.groups.some(item => item.object_id === group.object_id) &&
            <button className="secondary-button" onClick={() => setTarget({user: row, group, add: true})}>{t("Add membership")}</button>}</>} />}
        <h3>{t("Governance findings")}</h3>
        {row.findings.length ? <ul className="iam-list">{row.findings.map(finding => <li key={finding.key}><div>
          <strong>{t(finding.payload.rule)}</strong><p>{t(finding.payload.recommended_action)}</p>
          {finding.payload.group_ids?.map(id => <p key={id}><a href={link("groups", id)}>{id}</a></p>)}
        </div></li>)}</ul> : <p>{t("No records.")}</p>}
      </> : <>
        <GroupRow group={row} />
        <SearchRows<User> token={session.token} path={`${api}/groups/${objectId}`} revision={revision} members
          label={t("Search members")} render={user => <><UserRow user={user} />
          {canRequest && row.eligibility === "eligible" && row.synchronized &&
            <button className="secondary-button" onClick={() => setTarget({user, group: row, add: false})}>{t("Remove membership")}</button>}</>} />
        {canRequest && row.eligibility === "eligible" && row.synchronized &&
          <button className="secondary-button" onClick={() => setCatalog(!catalog)}>{t("Search users to assign")}</button>}
        {catalog && <SearchRows<User> token={session.token} path={`${api}/users`} revision={revision}
          label={t("Search name, email, job title or department")} render={user => <><UserRow user={user} />
          {user.synchronized && user.account_enabled === true &&
            <button className="secondary-button" onClick={() => setTarget({user, group: row, add: true})}>{t("Add membership")}</button>}</>} />}
      </>}
    </>}</QueryState>
    {target && <MembershipProposal key={`${target.user.object_id}:${target.group.object_id}:${target.add}`}
      {...target} token={session.token} refresh={refresh} cancel={() => setTarget(undefined)} />}
  </Drawer>;
}

function MembershipProposal({ user, group, add, token, refresh, cancel }: {
  user: User; group: Group; add: boolean; token: string; refresh: () => void; cancel: () => void;
}) {
  const mutation = useMutation(token);
  const [preview, setPreview] = useState<{ snapshot_id: number; expected: boolean; direct_authorized: boolean }>();
  const [justification, setJustification] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const draft = {user_id: user.object_id, group_id: group.object_id, add, justification};
  return <section className="iam-panel" aria-label={t("Preview change")}>
    <h3>{t(add ? "Add membership" : "Remove membership")}</h3>
    <button className="secondary-button" onClick={cancel}>{t("Cancel")}</button>
    <p>{user.display_name ?? user.object_id} · {group.display_name ?? group.object_id}</p>
    <form className="iam-form" onSubmit={async event => {
      event.preventDefault();
      setBusy(true); setError(""); setPreview(undefined);
      try {
        setPreview(await request(`${governance}/preview`, {method: "POST", body: JSON.stringify(draft)}, token));
      } catch (cause) { setError(cause instanceof Error ? cause.message : t("Request failed.")); }
      finally { setBusy(false); }
    }}>
      <label>{t("Business justification")}<textarea required minLength={8} maxLength={1000}
        value={justification} onChange={event => { setJustification(event.target.value); setPreview(undefined); }} /></label>
      <button className="secondary-button" disabled={busy || mutation.busy}>{t("Preview change")}</button>
    </form>
    {error && <p role="alert">{error}</p>}
    <Feedback message={mutation.message} />
    {preview && <div>
      {preview.direct_authorized && <p>{t("Authorized administrator changes enter the execution queue directly.")}</p>}
      <p>{t("Membership in snapshot")}: {t(preview.expected ? "Present" : "Absent")} · {t("Snapshot ID")} #{preview.snapshot_id}</p>
      <button className="primary-button" disabled={mutation.busy} onClick={async () => {
        if (await mutation.mutate(`${governance}/requests`, "POST", { ...draft, expected_snapshot_id: preview.snapshot_id })) {
          setPreview(undefined); refresh();
        }
      }}>{t("Submit request")}</button>
    </div>}
  </section>;
}
