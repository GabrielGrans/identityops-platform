import { useState, type FormEvent, type ReactNode } from "react";
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

function RunDetails({ run }: { run: Run }) {
  return <div>
    <strong>#{run.id} · {run.status}</strong>
    <p>Started {displayTime(run.started_at)}{run.finished_at && ` · Finished ${displayTime(run.finished_at)}`}</p>
    {run.status === "completed" && <p>
      {run.users_count} users · {run.groups_count} groups · {run.memberships_count} direct memberships
    </p>}
    {!!run.skipped_users_count && <p>{run.skipped_users_count} membership entries referenced users outside the snapshot.</p>}
    {run.error_code && <p>{errors[run.error_code] ?? "Synchronization could not complete."}</p>}
  </div>;
}

export function EntraPage({ session }: { session: Session }) {
  const { token, permissions } = session;
  const operation = useMutation(token);
  const status = useQuery<Connection>(token, "/entra/status", operation.revision, true);
  const canSync = permissions.includes("entra:sync");
  const canLink = permissions.includes("entra:manage_links");
  const [tab, setTab] = useState<"users" | "groups">("users");
  const [group, setGroup] = useState<Group>();

  async function sync() {
    if (!window.confirm("Read Microsoft Graph and refresh the local Entra snapshot?")) return;
    if (!await operation.mutate("/entra/sync", "POST")) operation.refresh();
  }

  function mapping(item: User | Group, kind: "users" | "groups") {
    const localId = "local_employee_id" in item ? item.local_employee_id : item.local_group_id;
    return <LinkEditor item={item} localId={localId} kind={kind} canLink={canLink} busy={operation.busy}
      onChange={(nextId) => operation.mutate(`/entra/${kind}/${item.object_id}/link`, "PUT", { local_id: nextId })} />;
  }

  return <Page title="Microsoft Entra ID">
    <Feedback message={operation.message} />
    <Panel title="Connection">
      <QueryState result={status}>{(connection) => <>
        <div>
          <strong>{connectionLabels[connection.state]}</strong>
          <p>{connection.message}</p>
          <p>Last successful sync: {connection.last_success_at ? displayTime(connection.last_success_at) : "Never"}</p>
          {connection.latest_run && <p>Latest run #{connection.latest_run.id} · {connection.latest_run.status}</p>}
        </div>
        <div className="iam-actions">
          {canSync && <button className="primary-button" disabled={operation.busy ||
            ["disabled", "invalid_configuration", "migration_required", "sync_running"].includes(connection.state)}
            onClick={() => void sync()}>{operation.busy ? "Working…" : "Sync from Microsoft Graph"}</button>}
          <button className="secondary-button" disabled={operation.busy} onClick={operation.refresh}>Refresh</button>
        </div>
      </>}</QueryState>
    </Panel>
    {status.data && !["disabled", "migration_required"].includes(status.data.state) &&
      (status.data.state !== "invalid_configuration" || status.data.latest_run) && <>
        <Panel title="External directory">
          <div className="iam-actions" aria-label="Directory view">
            <button className="secondary-button" aria-pressed={tab === "users"} onClick={() => { setTab("users"); setGroup(undefined); }}>Users</button>
            <button className="secondary-button" aria-pressed={tab === "groups"} onClick={() => setTab("groups")}>Groups</button>
          </div>
          {tab === "users" ? <DirectoryList<User> key="users" token={token} path="/entra/users" revision={operation.revision}
            render={(item) => <><UserDetails user={item} />{mapping(item, "users")}</>} />
            : <DirectoryList<Group> key="groups" token={token} path="/entra/groups" revision={operation.revision}
              render={(item) => <>
                <div>
                  <ObjectTitle item={item} />
                  <p>{item.security_enabled === null ? "Group type unavailable" : item.security_enabled ? "Security group" : "Other group"}</p>
                </div>
                <div className="iam-actions">
                  {mapping(item, "groups")}
                  <button className="secondary-button" onClick={() => setGroup(item)}>View members</button>
                </div>
              </>} />}
        </Panel>
        {group && <Panel title={`Direct user members · ${group.display_name ?? group.object_id}`}>
          <button className="secondary-button" onClick={() => setGroup(undefined)}>Close members</button>
          <DirectoryList<User> key={group.object_id} token={token} path={`/entra/groups/${group.object_id}/members`} revision={operation.revision}
            render={(item) => <UserDetails user={item} />} />
        </Panel>}
        <Panel title="Synchronization history">
          <DirectoryList<Run> token={token} path="/entra/sync-runs" revision={operation.revision} searchable={false}
            render={(run) => <RunDetails run={run} />} />
        </Panel>
      </>}
  </Page>;
}

function ObjectTitle({ item }: { item: ExternalObject }) {
  return <>
    <strong>{item.display_name ?? "Unnamed directory object"}</strong>
    <p>{item.object_id}{!item.present && " · Absent from latest snapshot"}</p>
  </>;
}

function UserDetails({ user }: { user: User }) {
  return <div>
    <ObjectTitle item={user} />
    {user.principal_name && <p>{user.principal_name}</p>}
    {user.mail && user.mail !== user.principal_name && <p>{user.mail}</p>}
    <p>{user.account_enabled === null ? "Account status unavailable" : user.account_enabled ? "Enabled in Entra" : "Disabled in Entra"}</p>
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
      <label>Search directory<input name="search" type="search" maxLength={150} /></label>
      <button className="secondary-button">Search</button>
    </form>}
    <QueryState result={result}>{(rows) => <>
      {rows.length ? <ul className="iam-list">{rows.map((row) => <li key={row.id}>{render(row)}</li>)}</ul>
        : <p>{search ? "No entries match this search." : "No entries to display."}</p>}
      <Pagination cursor={cursor} rows={rows} />
    </>}</QueryState>
  </>;
}

function LinkEditor({ item, localId, kind, canLink, busy, onChange }: {
  item: ExternalObject; localId: number | null; kind: "users" | "groups"; canLink: boolean; busy: boolean;
  onChange: (id: number | null) => Promise<boolean>;
}) {
  const [editing, setEditing] = useState(false);
  const label = kind === "users" ? "employee" : "group";
  if (localId !== null) return <div>
    <p>Local {label} #{localId}</p>
    {canLink && <button className="secondary-button" disabled={busy} onClick={() => {
      if (window.confirm(`Remove the link to local ${label} #${localId}?`)) void onChange(null);
    }}>Unlink</button>}
  </div>;
  if (!canLink || !item.present) return <p>Unlinked</p>;
  if (!editing) return <button className="secondary-button" onClick={() => setEditing(true)}>Link local {label}</button>;
  return <form className="iam-form" onSubmit={async (event) => {
    event.preventDefault();
    const id = Number(new FormData(event.currentTarget).get("localId"));
    if (window.confirm(`Link this Entra object to local ${label} #${id}?`) && await onChange(id)) setEditing(false);
  }}>
    <label>Local {label} ID<input name="localId" type="number" min="1" max="2147483647" required /></label>
    <button className="primary-button" disabled={busy}>Save link</button>
    <button className="secondary-button" type="button" onClick={() => setEditing(false)}>Cancel</button>
  </form>;
}
