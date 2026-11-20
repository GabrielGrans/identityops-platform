import { useState } from "react";
import { t } from "../i18n";
import { DirectoryWorkspace } from "./UnifiedEntraDirectory";
import { EntraGovernancePage } from "./EntraGovernancePage";
import { GovernancePage } from "./GovernancePage";
import { CertificationPage } from "./CertificationPage";
import { EntraPage } from "./EntraPage";
import { CatalogPage } from "./CatalogPage";
import { LifecyclePage } from "./LifecyclePage";
import { AuditPage, RequestsPage, ReviewsPage } from "./WorkflowPages";
import { Page, QueryState, SectionTabs } from "./common";
import { useQuery, type Session } from "./data";

const surfaces = {
  "Access Policies": ["IdentityOps policy", "Entra role governance"],
  "Alerts & Findings": ["Governance findings", "Notifications"],
} as const;

function GovernanceWorkspace({ page, session }: { page: keyof typeof surfaces; session: Session }) {
  const [active, setActive] = useState<string>(surfaces[page][0]);
  const tabs = session.permissions.includes("entra:read") ? surfaces[page] : surfaces[page].slice(0, 1);
  return <Page title={t(page)}>
    {tabs.length > 1 && <SectionTabs items={tabs} active={active} change={setActive} label={page} />}
    {active === "Entra role governance" || active === "Notifications" ?
      <EntraGovernancePage session={session} notifications={active === "Notifications"} /> :
      <GovernancePage session={session} policyOnly={page === "Access Policies"} />}
  </Page>;
}

const lifecyclePermissions = ["employees:create", "employees:update", "employees:deactivate"];

export function IamPage({ page, token, employeeId }: { page: string; token: string; employeeId: number }) {
  const result = useQuery<string[]>(token, "/auth/me/permissions");
  return <QueryState result={result}>{(permissions) => {
    const session = { token, employeeId, permissions };
    if ((page === "Access Policies" || page === "Alerts & Findings") && permissions.includes("governance:read"))
      return <GovernanceWorkspace page={page} session={session} />;
    if (page === "Access Requests") return <RequestsPage session={session} />;
    if (page === "Employees" || page === "Access Groups") return <DirectoryWorkspace
      kind={page === "Employees" ? "users" : "groups"} session={session} />;
    if (page === "Permissions" && permissions.includes("permissions:read")) return <CatalogPage catalog="permissions" session={session} />;
    if (page === "Departments" && permissions.includes("departments:read")) return <CatalogPage catalog="departments" session={session} />;
    if (page === "Microsoft Entra ID" && permissions.includes("entra:read")) return <EntraPage session={session} />;
    if (page === "Audit Logs" && permissions.includes("audit:read")) return <AuditPage session={session} />;
    if (page === "Access Certification" && permissions.some((permission) =>
      permission === "certifications:manage" || permission === "certifications:review")) return <CertificationPage session={session} />;
    if (page === "Access Reviews" && permissions.includes("reviews:manage")) return <ReviewsPage session={session} />;
    if (page === "Identity Lifecycle" && permissions.includes("access:manage") &&
      lifecyclePermissions.some((permission) => permissions.includes(permission))) return <LifecyclePage session={session} />;
    return <Page title={page}><p role="alert">{t("Your account does not have permission to open this module.")}</p></Page>;
  }}</QueryState>;
}
