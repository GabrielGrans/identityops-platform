import { DepartmentOperations } from "./DepartmentOperations";
import { t } from "../i18n";
import { useState, type FormEvent } from "react";
import { type Employee } from "../services/api";
import { CollapsiblePanel, DataTable, Drawer, Feedback, Page, Panel, QueryState, StatusBadge } from "./common";
import { DirectoryPagination, SearchChecks, SearchSelect } from "./DirectoryControls";
import { employeeLabel, PAGE_SIZE, type CatalogItem, type Session, useMutation, useQuery } from "./data";

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
  const [selectedGroup, setSelectedGroup] = useState<{ id: number; view: "details" | "permissions" | "members" }>();
  const [permissionIds, setPermissionIds] = useState<number[]>([]);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const canManagePermissions = catalog === "groups" && permissions.includes("permissions:manage");
  const canListPermissions = canManagePermissions && permissions.includes("permissions:read");
  const canManageMembers = allowAccess && permissions.includes("employees:read");
  const permissionOptions = useQuery<CatalogItem[]>(token, canListPermissions && edit === "new" ? "/permissions" : null);

  function openForm(entry: CatalogItem | "new") {
    setPermissionIds([]);
    setEdit(entry);
  }
  const item = edit === "new" ? undefined : edit ?? undefined;

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const fields = Object.fromEntries(form);
    const body = item || catalog === "groups" ? {
      ...fields, is_active: form.has("is_active"),
      ...(catalog === "groups" && !item && { permission_ids: permissionIds }),
    } : fields;
    if (catalog === "groups" && item && form.has("is_active") !== item.is_active &&
      !window.confirm(t("{p0} this group and save the changes?", { p0: t(item.is_active ? "Deactivate" : "Activate") }))) return;
    if (catalog === "groups" && permissionIds.length && !item &&
      !window.confirm(t("Create this group with the selected permissions?"))) return;
    const success = await mutation.mutate(
      item ? `/${catalog}/${item.id}` : `/${catalog}`,
      item ? "PUT" : "POST",
      body,
    );
    if (success) setEdit(null);
  }

  const DirectoryPanel = catalog === "permissions" ? CollapsiblePanel : Panel;

  return <Page title={t(titles[catalog])}>
    <Feedback message={mutation.message} />
    {catalog === "permissions" && <p>{t("Internal RBAC controls IdentityOps actions. Microsoft 365 access is managed through Entra group memberships.")}</p>}
    {catalog === "departments" && <DepartmentOperations token={token} revision={mutation.revision} />}
    {allowEdit && <button className="primary-button" onClick={() => openForm("new")}>{catalog === "groups" ? t("New Group") : t("Create record")}</button>}
    {edit && <Drawer close={() => setEdit(null)} title={item ? t("Edit {p0}", { p0: String(item.name) }) : t("New record")}>
      <form key={item?.id ?? "new"} className="iam-form" onSubmit={save}>
        <label>{t("Name")}<input name="name" required minLength={2} maxLength={100} defaultValue={item?.name} /></label>
        <label>{t("Code")}<input name="code" required minLength={2} maxLength={{ departments: 20, groups: 50, permissions: 100 }[catalog]} defaultValue={item?.code} /></label>
        {catalog === "permissions" && <>
          <label>{t("Resource")}<input name="resource" required minLength={2} maxLength={100} defaultValue={item?.resource} /></label>
          <label>{t("Action")}<input name="action" required minLength={2} maxLength={50} defaultValue={item?.action} /></label>
        </>}
        <label>{t("Description")}<textarea name="description" defaultValue={item?.description ?? ""} /></label>
        {(item || catalog === "groups") && <label className="iam-checkbox"><input name="is_active" type="checkbox" defaultChecked={item?.is_active ?? true} />{" "}{t("Active")}</label>}
        {canListPermissions && !item && <QueryState result={permissionOptions}>{options =>
          <SearchChecks label={t("Permissions")} options={permissionChoices(options.filter(option => option.is_active))}
            selected={permissionIds} onChange={setPermissionIds} />
        }</QueryState>}
        <div className="iam-actions">
          <button className="primary-button" disabled={mutation.busy}>{t("Save")}</button>
          <button className="secondary-button" type="button" onClick={() => setEdit(null)}>{t("Cancel")}</button>
        </div>
      </form>
    </Drawer>}
    {selectedGroup && <GroupDetails key={`${selectedGroup.id}:${selectedGroup.view}`} session={session}
      groupId={selectedGroup.id} view={selectedGroup.view} revision={mutation.revision}
      onClose={() => setSelectedGroup(undefined)} onChange={mutation.refresh} />}
    <DirectoryPanel title={t(catalog === "permissions" ? "Permissions directory" : "Directory")}>
      <div className="iam-form">
        <label>{t(catalog === "groups" ? "Search groups" : catalog === "permissions" ? "Search permissions" : "Search departments")}<input type="search" value={search} onChange={event => {
          setSearch(event.target.value); setPage(1);
        }} /></label>
      </div>
      <QueryState result={result}>{(items) => {
        const filtered = items.filter(entry =>
          `${entry.name} ${entry.code} ${entry.description ?? ""} ${entry.resource ?? ""} ${entry.action ?? ""}`.toLowerCase().includes(search.trim().toLowerCase()));
        const total = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
        const current = Math.min(page, total);
        const rows = filtered.slice((current - 1) * PAGE_SIZE, current * PAGE_SIZE);
        return <>
          <DataTable label={t(titles[catalog])} rows={rows} rowKey={entry => entry.id} columns={[
            { label: t("Name"), render: entry => <strong>{entry.name}</strong> },
            { label: t("Code"), render: entry => entry.code },
            { label: t("Description"), render: entry => entry.description ?? "—" },
            { label: t("Status"), render: entry => <StatusBadge>{t(entry.is_active ? "Active" : "Inactive")}</StatusBadge> },
            { label: t("Actions"), render: entry => {
              const enabled = requestable.data?.some(group => group.id === entry.id);
              return <div className="iam-actions">
              {catalog === "groups" && <button className="secondary-button" onClick={() =>
                setSelectedGroup({ id: entry.id, view: "details" })}>{t("View details")}</button>}
              {allowEdit && <button className="secondary-button" onClick={() => openForm(entry)}>{catalog === "groups" ? t("Edit Group") : t("Edit")}</button>}
              {catalog === "groups" && allowEdit && <button className="secondary-button" disabled={mutation.busy} onClick={() => {
                if (window.confirm(t("{action} {name}?", { action: t(entry.is_active ? "Deactivate" : "Activate"), name: entry.name }))) void mutation.mutate(
                  `/groups/${entry.id}`, entry.is_active ? "DELETE" : "PUT",
                  entry.is_active ? undefined : { name: entry.name, code: entry.code, description: entry.description, is_active: true },
                );
              }}>{entry.is_active ? t("Deactivate") : t("Activate")}</button>}
              {(allowAccess || canManagePermissions) && <button className="secondary-button" onClick={() =>
                setSelectedGroup({ id: entry.id, view: "permissions" })}>{t("Manage Permissions")}</button>}
              {canManageMembers && <button className="secondary-button" onClick={() =>
                setSelectedGroup({ id: entry.id, view: "members" })}>{t("Manage Members")}</button>}
              {allowAccess && <>

                {requestable.data && entry.is_active && <button className="secondary-button" disabled={mutation.busy}
                  onClick={() => void mutation.mutate(`/groups/${entry.id}/requestability`, "PUT", { enabled: !enabled })}>
                  {enabled ? t("Close to requests") : t("Open to requests")}
                </button>}
              </>}
            </div>
            } },
          ]} />
          {total > 1 && <DirectoryPagination page={current} total={total} onPage={setPage} />}
        </>;
      }}</QueryState>
      {requestable.error && <p role="alert">{requestable.error}</p>}
    </DirectoryPanel>
    {allowAccess && !canManageMembers && <MembershipsById session={session} />}
  </Page>;
}

function permissionChoices(items: CatalogItem[]) {
  return items.map(item => ({
    id: item.id, name: `${item.name} · ${item.code}`,
    searchText: `${item.resource ?? ""} ${item.action ?? ""}`,
  }));
}

function GroupDetails({ session, groupId, view, revision, onClose, onChange }: {
  session: Session; groupId: number; view: "details" | "permissions" | "members"; revision: number;
  onClose: () => void; onChange: () => void;
}) {
  const group = useQuery<CatalogItem>(session.token, `/groups/${groupId}`, revision, true);
  return <Drawer close={onClose} title={group.data?.name ?? t("Group #{p0}", { p0: String(groupId) })}>
    <QueryState result={group}>{entry => <>
      <p>{entry.code} · {entry.is_active ? t("Active") : t("Inactive")}</p>
      <p>{entry.description || t("No description.")}</p>
      {view === "permissions" && <Assignments session={session} group={entry} onChange={onChange} />}
      {view === "members" && <GroupMembers session={session} group={entry} />}
    </>}</QueryState>
  </Drawer>;
}

function Assignments({ session, group, onChange }: {
  session: Session; group: CatalogItem; onChange: () => void;
}) {
  const mutation = useMutation(session.token);
  const canManage = session.permissions.includes("permissions:manage");
  const path = `/groups/${group.id}/permissions`;
  const current = useQuery<CatalogItem[]>(session.token, path, mutation.revision);
  const available = useQuery<CatalogItem[]>(session.token, canManage &&
    session.permissions.includes("permissions:read") ? "/permissions" : null);

  async function change(id: FormDataEntryValue | number | null, method: string) {
    if (await mutation.mutate(`${path}/${id}`, method)) onChange();
  }

  return <>
    <h3>{t("Assigned permissions")}</h3>
    <Feedback message={mutation.message} />
    <QueryState result={current}>{items => <>
      {items.length ? <ul className="iam-list directory-options">{items.map(item => <li key={item.id}>
        <span>{item.name} · {item.code}{item.is_active ? "" : t(" · Inactive")}</span>
        {canManage && <button className="secondary-button" disabled={mutation.busy} onClick={() => {
          if (window.confirm(t("Remove {p0} from this group?", { p0: String(item.name) }))) void change(item.id, "DELETE");
        }}>{t("Remove")}</button>}
      </li>)}</ul> : <p>{t("No assigned permissions.")}</p>}
      {available.data && group.is_active && <form className="iam-form" onSubmit={(event) => {
        event.preventDefault();
        const id = new FormData(event.currentTarget).get("permission");
        if (window.confirm(t("Assign this permission to the group and its members?"))) void change(id, "POST");
      }}>
        <SearchSelect label={t("Permission")} name="permission" options={permissionChoices(
          available.data.filter(item => item.is_active && !items.some(assigned => assigned.id === item.id)),
        )} />
        <button className="primary-button" disabled={mutation.busy}>{t("Assign permission")}</button>
      </form>}
      {available.error && <p role="alert">{available.error}</p>}
    </>}</QueryState>
  </>;
}

function GroupMembers({ session, group }: { session: Session; group: CatalogItem }) {
  const mutation = useMutation(session.token);
  const members = useQuery<Employee[]>(session.token, `/groups/${group.id}/members`, mutation.revision);
  const employees = useQuery<Employee[]>(session.token, group.is_active ? "/employees" : null);
  const [search, setSearch] = useState("");
  const path = (id: number | FormDataEntryValue | null) => `/employees/${id}/groups/${group.id}`;

  return <>
    <h3>{t("Group members")}</h3>
    <Feedback message={mutation.message} />
    <QueryState result={members}>{items => {
      const shown = items.filter(employee => employeeLabel(employee).toLowerCase().includes(search.trim().toLowerCase()));
      return <>
        <div className="iam-form"><label>{t("Search members")}<input type="search" value={search}
          onChange={event => setSearch(event.target.value)} /></label></div>
        {shown.length ? <ul className="iam-list directory-options">{shown.map(employee => <li key={employee.id}>
          <span>{employeeLabel(employee)} · {t(employee.status)}</span>
          <button className="secondary-button" disabled={mutation.busy} onClick={() => {
            if (window.confirm(t("Remove {p0} from this group?", { p0: String(employeeLabel(employee)) }))) void mutation.mutate(path(employee.id), "DELETE");
          }}>{t("Remove")}</button>
        </li>)}</ul> : <p>{t("No matching members.")}</p>}
        {group.is_active && <QueryState result={employees}>{options => <form className="iam-form" onSubmit={event => {
          event.preventDefault();
          const id = new FormData(event.currentTarget).get("employee");
          if (window.confirm(t("Add this employee to the group?"))) void mutation.mutate(path(id), "POST");
        }}>
          <SearchSelect label={t("Employee")} name="employee" options={options.filter(employee => employee.status === "active" &&
            !items.some(member => member.id === employee.id)).map(employee => ({ id: employee.id, name: employeeLabel(employee) }))} />
          <button className="primary-button" disabled={mutation.busy}>{t("Add employee")}</button>
        </form>}</QueryState>}
      </>;
    }}</QueryState>
  </>;
}

function MembershipsById({ session }: { session: Session }) {
  const mutation = useMutation(session.token);
  const [employeeId, setEmployeeId] = useState("");
  const groups = useQuery<CatalogItem[]>(session.token, "/groups");
  const current = useQuery<CatalogItem[]>(session.token, employeeId ? `/employees/${employeeId}/groups` : null, mutation.revision);
  return <Panel title={t("Employee memberships")}>
    <form className="iam-form" onSubmit={(event) => {
      event.preventDefault();
      setEmployeeId(String(new FormData(event.currentTarget).get("employee")));
    }}>
      <label>{t("Employee ID")}<input name="employee" type="number" min={1} required /></label>
      <button className="secondary-button">{t("Load memberships")}</button>
    </form>
    <Feedback message={mutation.message} />
    {employeeId && <QueryState result={current}>{(items) => <>
      <h3>{t("Memberships for employee #")}{employeeId}</h3>
      {items.length ? <ul className="iam-list">{items.map((item) => <li key={item.id}>
        <span>{item.name}</span>
        <button className="secondary-button" disabled={mutation.busy} onClick={() => {
          if (window.confirm(t("Remove {p0} from this employee?", { p0: String(item.name) })))
            void mutation.mutate(`/employees/${employeeId}/groups/${item.id}`, "DELETE");
        }}>{t("Remove")}</button>
      </li>)}</ul> : <p>{t("No memberships.")}</p>}
      {groups.data && <form className="iam-form" onSubmit={(event) => {
        event.preventDefault();
        const id = new FormData(event.currentTarget).get("group");
        if (window.confirm(t("Assign this group to the employee?"))) void mutation.mutate(`/employees/${employeeId}/groups/${id}`, "POST");
      }}>
        <SearchSelect label={t("Group")} name="group" options={groups.data.filter((group) => group.is_active && !items.some((assigned) => assigned.id === group.id))} />
        <button className="primary-button" disabled={mutation.busy}>{t("Assign group")}</button>
      </form>}
    </>}</QueryState>}
  </Panel>;
}
