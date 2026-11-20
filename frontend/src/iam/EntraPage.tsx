import { t } from "../i18n";
import { useState, type FormEvent, type ReactNode } from "react";
import { EntraReconciliation, type Selection } from "./EntraReconciliation";
import { Feedback, Page, Pagination, Panel, QueryState } from "./common";
import { displayTime, PAGE_SIZE, useCursor, useMutation, useQuery, type Session } from "./data";

type Run = {
  id: number;
  status: "running" | "completed" | "failed";
  started_at: string;
  finished_at: string | null;
  error_code: string | null;
  users_count: number | null;
  groups_count: number | null;
  memberships_count: number | null;
  skipped_users_count: number | null;
};

type Connection = {
  state: "disabled" | "invalid_configuration" | "migration_required" | "ready" | "connected" | "error" | "sync_running";
  message: string;
  last_success_at: string | null;
  imported_users: number | null;
  imported_groups: number | null;
  latest_run: Run | null;
};

type ExternalObject = { id: number; object_id: string; display_name: string | null; present: boolean };
type User = ExternalObject & {
  principal_name: string | null;
  mail: string | null;
  account_enabled: boolean | null;
  local_employee_id: number | null;
};
type Group = ExternalObject & { security_enabled: boolean | null; local_group_id: number | null };

const connectionLabels: Record<Connection["state"], string> = {
  disabled: "Disabled",
  invalid_configuration: "Configuration required",
  migration_required: "Database migration required",
  ready: "Ready to synchronize",
  connected: "Verified",
  error: "Last synchronization failed",
  sync_running: "Synchronizing",
};

const errors: Record<string, string> = {
  token_rejected: "Microsoft rejected the application credentials.",
  graph_unauthorized: "Microsoft Graph rejected the application token.",
  graph_forbidden: "Microsoft Graph refused directory access. Verify application consent.",
  membership_forbidden: "Microsoft Graph refused group membership access.",
  graph_throttled: "Microsoft throttled the request. Try again later.",
  graph_unavailable: "Microsoft was temporarily unavailable.",
  invalid_response: "Microsoft returned data that could not be validated.",
  sync_limit: "The directory size, request or time limit was reached.",
  sync_expired: "Synchronization expired.",
  storage_failed: "The snapshot could not be stored.",
};

export function EntraPage({ session }: { session: Session }) {
  const { token, permissions } = session;
  const operation = useMutation(token);
  const status = useQuery<Connection>(token, "/entra/status", operation.revision, true);
  const schedule = useQuery<{next_run: string | null; failures: number}>(token,
    status.data && !["disabled", "invalid_configuration", "migration_required"].includes(status.data.state)
      ? "/entra/automation/schedule" : null, operation.revision, true);
  const canSync = permissions.includes("entra:sync");
  const canLink = permissions.includes("entra:manage_links");
  const [tab, setTab] = useState<"users" | "groups">("users");
  const [user, setUser] = useState<User>();
  const [group, setGroup] = useState<Group>();
  const [selected, setSelected] = useState<Selection[]>([]);
  const canReconcile = canLink && permissions.includes("entra:provision_local");
  const canCreate = permissions.includes("employees:create");

  function toggle(user: User) {
    setSelected(current => current.some(item => item.object_id === user.object_id)
      ? current.filter(item => item.object_id !== user.object_id)
      : current.length < 25 ? [...current, { object_id: user.object_id, display_name: user.display_name }] : current);
  }

  async function sync() {
    if (!window.confirm(t("Read Microsoft Graph and refresh the local Entra snapshot?"))) return;
    if (!await operation.mutate("/entra/sync", "POST")) operation.refresh();
  }

  function mapping(item: User | Group, kind: "users" | "groups") {
    const localId = "local_employee_id" in item ? item.local_employee_id : item.local_group_id;
    return <LinkEditor item={item} localId={localId} kind={kind} canLink={canLink} busy={operation.busy}
      onChange={(nextId) => operation.mutate(`/entra/${kind}/${item.object_id}/link`, "PUT", { local_id: nextId })} />;
  }

  return <Page title="Microsoft Entra ID">
    <Feedback message={operation.message} />
    <Panel title={t("Connection")}>
      <QueryState result={status}>{(connection) => <>
        <div>
          <strong>{t(connectionLabels[connection.state])}</strong>
          <p>{t(connection.message)}</p>
          <p>{t("Last successful sync:")}{" "}{connection.last_success_at ? displayTime(connection.last_success_at) : t("Never")}</p>
          <p>{t("Next scheduled synchronization")}: {schedule.data?.next_run ? displayTime(schedule.data.next_run) : "—"}</p>
          {schedule.error && <p role="alert">{schedule.error}</p>}
          {!!schedule.data?.failures && <p role="status">{t("Consecutive synchronization failures")}: {schedule.data.failures}</p>}
          <p>{t("Imported users")}: {connection.imported_users ?? "—"} · {t("Imported groups")}: {connection.imported_groups ?? "—"}</p>
          {connection.latest_run?.error_code && <p role="alert">{t(errors[connection.latest_run.error_code] ?? "Synchronization could not complete.")}</p>}
          {connection.latest_run && <p>{t("Latest run #")}{connection.latest_run.id} · {t(connection.latest_run.status)}</p>}
        </div>
        <div className="iam-actions">
          {canSync && <button className="primary-button" disabled={operation.busy ||
            ["disabled", "invalid_configuration", "migration_required", "sync_running"].includes(connection.state)}
            onClick={() => void sync()}>{operation.busy ? t("Working…") : t("Sync from Microsoft Graph")}</button>}
          <button className="secondary-button" disabled={operation.busy} onClick={operation.refresh}>{t("Refresh")}</button>
        </div>
      </>}</QueryState>
    </Panel>
    {status.data && !["disabled", "migration_required"].includes(status.data.state) &&
      (status.data.state !== "invalid_configuration" || status.data.latest_run) && <>
        {user && <UserAccess key={user.object_id} user={user} token={token} revision={operation.revision} onClose={() => setUser(undefined)} />}
        <Panel title={t("External directory")}>
          <div className="iam-actions" aria-label={t("Directory view")}>
            <button className="secondary-button" aria-pressed={tab === "users"} onClick={() => { setTab("users"); setGroup(undefined); }}>{t("Users")}</button>
            <button className="secondary-button" aria-pressed={tab === "groups"} onClick={() => { setTab("groups"); setUser(undefined); }}>{t("Groups")}</button>
          </div>
          {tab === "users" ? <DirectoryList<User> key="users" token={token} path="/entra/users" revision={operation.revision}
            render={(item) => <><UserDetails user={item} />{mapping(item, "users")}
              <button className="secondary-button" onClick={() => setUser(item)}>{t("View user access")}</button>
              {canReconcile && item.present && item.local_employee_id === null && <label className="entra-attestation">
                <input type="checkbox" checked={selected.some(row => row.object_id === item.object_id)}
                  disabled={selected.length >= 25 && !selected.some(row => row.object_id === item.object_id)}
                  onChange={() => toggle(item)} />
                {t("Reconcile")}{" "}{item.display_name ?? item.object_id}
              </label>}
            </>} />
            : <DirectoryList<Group> key="groups" token={token} path="/entra/groups" revision={operation.revision}
              render={(item) => <>
                <div>
                  <ObjectTitle item={item} />
                  <p>{item.security_enabled === null ? t("Group type unavailable") : item.security_enabled ? t("Security group") : t("Other group")}</p>
                </div>
                <div className="iam-actions">
                  {mapping(item, "groups")}
                  <button className="secondary-button" onClick={() => setGroup(item)}>{t("View members")}</button>
                </div>
              </>} />}
        </Panel>
        {canReconcile && tab === "users" && selected.length > 0 &&
          <EntraReconciliation selected={selected} session={session}
            canCreate={canCreate} onComplete={operation.refresh}
            remove={(id) => setSelected(current => current.filter(item => item.object_id !== id))} />}
        {group && <Panel title={t("Direct user members · {p0}", { p0: String(group.display_name ?? group.object_id) })}>
          <button className="secondary-button" onClick={() => setGroup(undefined)}>{t("Close members")}</button>
          <DirectoryList<User> key={group.object_id} token={token} path={`/entra/groups/${group.object_id}/members`} revision={operation.revision}
            render={(item) => <UserDetails user={item} />} />
        </Panel>}
      </>}
  </Page>;
}

function ObjectTitle({ item }: { item: ExternalObject }) {
  return <>
    <strong>{item.display_name ?? t("Unnamed directory object")}</strong>
    <p>{item.object_id}{!item.present && t(" · Absent from latest snapshot")}</p>
  </>;
}

function UserDetails({ user }: { user: User }) {
  return <div>
    <ObjectTitle item={user} />
    {user.principal_name && <p>{user.principal_name}</p>}
    {user.mail && user.mail !== user.principal_name && <p>{user.mail}</p>}
    <p>{user.account_enabled === null ? t("Account status unavailable") : user.account_enabled ? t("Enabled in Entra") : t("Disabled in Entra")}</p>
  </div>;
}

function DirectoryList<T extends { id: number }>({ token, path, revision, searchable = true, render }: {
  token: string; path: string; revision: number; searchable?: boolean; render: (row: T) => ReactNode;
}) {
  const cursor = useCursor();
  const [search, setSearch] = useState("");
  const query = search ? `&search=${encodeURIComponent(search)}` : "";
  const result = useQuery<T[]>(token, `${path}?limit=${PAGE_SIZE}${cursor.query}${query}`, revision);

  function filter(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const input = new FormData(event.currentTarget).get("search");
    setSearch(typeof input === "string" ? input.trim() : "");
    cursor.reset();
  }

  return <>
    {searchable && <form className="iam-form" onSubmit={filter}>
      <label>{t("Search directory")}<input name="search" type="search" maxLength={150} /></label>
      <button className="secondary-button">{t("Search")}</button>
    </form>}
    <QueryState result={result}>{(rows) => <>
      {rows.length ? <ul className="iam-list">{rows.map((row) => <li key={row.id}>{render(row)}</li>)}</ul>
        : <p>{search ? t("No entries match this search.") : t("No entries to display.")}</p>}
      <Pagination cursor={cursor} rows={rows} />
    </>}</QueryState>
  </>;
}

function LinkEditor({ item, localId, kind, canLink, busy, onChange }: {
  item: ExternalObject; localId: number | null; kind: "users" | "groups"; canLink: boolean; busy: boolean;
  onChange: (id: number | null) => Promise<boolean>;
}) {
  const [editing, setEditing] = useState(false);
  const label = t(kind === "users" ? "employee" : "group");
  if (localId !== null) return <div>
    <p>{t("Local")}{" "}{label} #{localId}</p>
    {canLink && <button className="secondary-button" disabled={busy} onClick={() => {
      if (window.confirm(t("Remove the link to local {p0} #{p1}?", { p0: String(label), p1: String(localId) }))) void onChange(null);
    }}>{t("Unlink")}</button>}
  </div>;
  if (!canLink || !item.present) return <p>{t("Unlinked")}</p>;
  if (!editing) return <button className="secondary-button" onClick={() => setEditing(true)}>{t("Link local")}{" "}{label}</button>;
  return <form className="iam-form" onSubmit={async (event) => {
    event.preventDefault();
    const id = Number(new FormData(event.currentTarget).get("localId"));
    if (window.confirm(t("Link this Entra object to local {p0} #{p1}?", { p0: String(label), p1: String(id) })) && await onChange(id)) setEditing(false);
  }}>
    <label>{t("Local")}{" "}{label}{" "}{t("ID")}<input name="localId" type="number" min="1" max="2147483647" required /></label>
    <button className="primary-button" disabled={busy}>{t("Save link")}</button>
    <button className="secondary-button" type="button" onClick={() => setEditing(false)}>{t("Cancel")}</button>
  </form>;
}

type UserAccessResult = {
  user: User;
  groups: Group[];
  snapshot_id: number | null;
  comparison: {
    local_only_group_ids: number[];
    entra_only_group_ids: number[];
    unmapped_local_group_ids: number[];
    unmapped_entra_group_ids: string[];
  } | null;
};

function UserAccess({ user, token, revision, onClose }: {
  user: User; token: string; revision: number; onClose: () => void;
}) {
  const result = useQuery<UserAccessResult>(token, `/entra/users/${user.object_id}/access`, revision);
  return <Panel title={t("User details and access")}>
    <button className="secondary-button" onClick={onClose}>{t("Close details")}</button>
    <QueryState result={result}>{data => <>
      <UserDetails user={data.user} />
      <h3>{t("Direct Entra memberships")}</h3>
      {data.snapshot_id === null ? <p>{t("No current snapshot for this user.")}</p> : data.groups.length ?
        <ul className="iam-list directory-options">{data.groups.map(group => <li key={group.id}>
          <span>{group.display_name ?? group.object_id}</span>
        </li>)}</ul> : <p>{t("No direct memberships in this snapshot.")}</p>}
      <h3>{t("Local and Entra access comparison")}</h3>
      {data.comparison ? <dl>
        <dt>{t("Local only")}</dt><dd>{data.comparison.local_only_group_ids.join(", ") || "—"}</dd>
        <dt>{t("Entra only")}</dt><dd>{data.comparison.entra_only_group_ids.join(", ") || "—"}</dd>
        <dt>{t("Unmapped local groups")}</dt><dd>{data.comparison.unmapped_local_group_ids.join(", ") || "—"}</dd>
        <dt>{t("Unmapped Entra groups")}</dt><dd>{data.comparison.unmapped_entra_group_ids.join(", ") || "—"}</dd>
      </dl> : <p>{t("A recent snapshot, a linked employee and permission to manage access are required.")}</p>}
    </>}</QueryState>
  </Panel>;
}
