import { useState, type FormEvent } from "react";
import { type Employee } from "../services/api";
import { Feedback, Page, Panel, QueryState, SelectId,  } from "./common";
import { type CatalogItem, type Session, useMutation, useQuery } from "./data";

type Catalog = "groups" | "permissions" | "departments";
const titles = { groups: "Access Groups", permissions: "Permissions", departments: "Departments" };

export function CatalogPage({ catalog, session }: { catalog: Catalog; session: Session }) {
  const { token, permissions } = session;
  const mutation = useMutation(token);
  const result = useQuery<CatalogItem[]>(token, `/${catalog}`, mutation.revision);
  const allowEdit = permissions.includes(`${catalog}:manage`);
  const allowAccess = catalog === "groups" && permissions.includes("access:manage");
  const requestable = useQuery<CatalogItem[]>(token, allowAccess ? "/access-requests/catalog" : null, mutation.revision);
  const [edit, setEdit] = useState<CatalogItem | "new" | null>(null);
  const [selectedGroup, setSelectedGroup] = useState<number>();
  const item = edit === "new" ? undefined : edit ?? undefined;

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const fields = Object.fromEntries(form);
    const body = item ? { ...fields, is_active: form.has("is_active") } : fields;
    const success = await mutation.mutate(
      item ? `/${catalog}/${item.id}` : `/${catalog}`,
      item ? "PUT" : "POST",
      body,
    );
    if (success) setEdit(null);
  }

  return <Page title={titles[catalog]}>
    <Feedback message={mutation.message} />
    {allowEdit && <button className="primary-button" onClick={() => setEdit("new")}>Create record</button>}
    {edit && <Panel title={item ? `Edit ${item.name}` : "New record"}>
      <form key={item?.id ?? "new"} className="iam-form" onSubmit={save}>
        <label>Name<input name="name" required minLength={2} maxLength={100} defaultValue={item?.name} /></label>
        <label>Code<input name="code" required minLength={2} maxLength={{ departments: 20, groups: 50, permissions: 100 }[catalog]} defaultValue={item?.code} /></label>
        {catalog === "permissions" && <>
          <label>Resource<input name="resource" required minLength={2} maxLength={100} defaultValue={item?.resource} /></label>
          <label>Action<input name="action" required minLength={2} maxLength={50} defaultValue={item?.action} /></label>
        </>}
        <label>Description<textarea name="description" defaultValue={item?.description ?? ""} /></label>
        {item && <label className="iam-checkbox"><input name="is_active" type="checkbox" defaultChecked={item.is_active} /> Active</label>}
        <div className="iam-actions">
          <button className="primary-button" disabled={mutation.busy}>Save</button>
          <button className="secondary-button" type="button" onClick={() => setEdit(null)}>Cancel</button>
        </div>
      </form>
    </Panel>}
    <Panel title="Directory">
      <QueryState result={result}>{(items) => items.length ? <ul className="iam-list">
        {items.map((entry) => {
          const enabled = requestable.data?.some((group) => group.id === entry.id);
          return <li key={entry.id}>
            <div>
              <strong>{entry.name}</strong> <span>{entry.code} · {entry.is_active ? "Active" : "Inactive"}</span>
              {entry.description && <p>{entry.description}</p>}
            </div>
            <div className="iam-actions">
              {allowEdit && <button className="secondary-button" onClick={() => setEdit(entry)}>Edit</button>}
              {allowAccess && <>
                <button className="secondary-button" onClick={() => setSelectedGroup(entry.id)}>Permissions</button>
                {requestable.data && entry.is_active && <button className="secondary-button" disabled={mutation.busy}
                  onClick={() => void mutation.mutate(`/groups/${entry.id}/requestability`, "PUT", { enabled: !enabled })}>
                  {enabled ? "Close to requests" : "Open to requests"}
                </button>}
              </>}
            </div>
          </li>;
        })}
      </ul> : <p>No records.</p>}</QueryState>
      {requestable.error && <p role="alert">{requestable.error}</p>}
    </Panel>
    {allowAccess && selectedGroup !== undefined && (
      <Assignments key={selectedGroup} session={session} groupId={selectedGroup} revision={mutation.revision}
        onClose={() => setSelectedGroup(undefined)} onChange={mutation.refresh} />
    )}
    {allowAccess && <Memberships session={session} />}
  </Page>;
}

function Assignments({ session, groupId, revision, onClose, onChange }: {
  session: Session; groupId: number; revision: number; onClose: () => void; onChange: () => void;
}) {
  const mutation = useMutation(session.token);
  const group = useQuery<CatalogItem>(session.token, `/groups/${groupId}`, revision);
  const current = useQuery<CatalogItem[]>(session.token, `/groups/${groupId}/permissions`, mutation.revision);
  const available = useQuery<CatalogItem[]>(session.token, session.permissions.includes("permissions:read") ? "/permissions" : null);
  return <Panel title={`Permissions for ${group.data?.name ?? `group #${groupId}`}`}>
    <button className="secondary-button" onClick={onClose}>Close</button>
    <Feedback message={mutation.message} />
    <QueryState result={current}>{(items) => <>
      {items.length ? <ul className="iam-list">{items.map((item) => <li key={item.id}>
        <span>{item.name} · {item.code}</span>
        <button className="secondary-button" disabled={mutation.busy} onClick={() =>
          void mutation.mutate(`/groups/${groupId}/permissions/${item.id}`, "DELETE").then((success) => { if (success) onChange(); })}>Remove</button>
      </li>)}</ul> : <p>No assigned permissions.</p>}
      {available.data && group.data?.is_active && <form className="iam-form" onSubmit={(event) => {
        event.preventDefault();
        const id = new FormData(event.currentTarget).get("permission");
        void mutation.mutate(`/groups/${groupId}/permissions/${id}`, "POST").then((success) => { if (success) onChange(); });
      }}>
        <SelectId label="Permission" name="permission" items={available.data.filter((item) => item.is_active && !items.some((assigned) => assigned.id === item.id))} />
        <button className="primary-button" disabled={mutation.busy}>Assign permission</button>
      </form>}
      {available.error && <p role="alert">{available.error}</p>}
    </>}</QueryState>
  </Panel>;
}

function Memberships({ session }: { session: Session }) {
  const mutation = useMutation(session.token);
  const [employeeId, setEmployeeId] = useState("");
  const employees = useQuery<Employee[]>(session.token, session.permissions.includes("employees:read") ? "/employees" : null);
  const groups = useQuery<CatalogItem[]>(session.token, "/groups");
  const current = useQuery<CatalogItem[]>(session.token, employeeId ? `/employees/${employeeId}/groups` : null, mutation.revision);
  return <Panel title="Employee memberships">
    <form className="iam-form" onSubmit={(event) => {
      event.preventDefault();
      setEmployeeId(String(new FormData(event.currentTarget).get("employee")));
    }}>
      {employees.data ? <SelectId label="Employee" name="employee" items={employees.data.map((employee) => ({
        id: employee.id, name: `${employee.first_name} ${employee.last_name} (${employee.employee_number})`,
      }))} /> : <label>Employee ID<input name="employee" type="number" min={1} required /></label>}
      <button className="secondary-button">Load memberships</button>
    </form>
    <Feedback message={mutation.message} />
    {employeeId && <QueryState result={current}>{(items) => <>
      <h3>Memberships for employee #{employeeId}</h3>
      {items.length ? <ul className="iam-list">{items.map((item) => <li key={item.id}>
        <span>{item.name}</span>
        <button className="secondary-button" disabled={mutation.busy} onClick={() =>
          void mutation.mutate(`/employees/${employeeId}/groups/${item.id}`, "DELETE")}>Remove</button>
      </li>)}</ul> : <p>No memberships.</p>}
      {groups.data && <form className="iam-form" onSubmit={(event) => {
        event.preventDefault();
        const id = new FormData(event.currentTarget).get("group");
        void mutation.mutate(`/employees/${employeeId}/groups/${id}`, "POST");
      }}>
        <SelectId label="Group" name="group" items={groups.data.filter((group) => group.is_active && !items.some((assigned) => assigned.id === group.id))} />
        <button className="primary-button" disabled={mutation.busy}>Assign group</button>
      </form>}
    </>}</QueryState>}
  </Panel>;
}
