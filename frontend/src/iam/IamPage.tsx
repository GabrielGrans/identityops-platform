import { t } from "../i18n";
import { DirectoryWorkspace } from "./UnifiedEntraDirectory";
import { EntraGovernancePage } from "./EntraGovernancePage";
import { GovernancePage } from "./GovernancePage";
import { CertificationPage } from "./CertificationPage";
import { EntraPage } from "./EntraPage";
import { CatalogPage } from "./CatalogPage";
import { LifecyclePage } from "./LifecyclePage";
import { AuditPage, RequestsPage, ReviewsPage } from "./WorkflowPages";
import { Page, QueryState } from "./common";
import { useQuery } from "./data";

const lifecyclePermissions = ["employees:create", "employees:update", "employees:deactivate"];

export function IamPage({ page, token, employeeId }: { page: string; token: string; employeeId: number }) {
  const result = useQuery<string[]>(token, "/auth/me/permissions");
  return <QueryState result={result}>{(permissions) => {
    const session = { token, employeeId, permissions };
    if (["Entra role governance", "Notifications"].includes(page) && permissions.includes("governance:read") && permissions.includes("entra:read"))
      return <EntraGovernancePage session={session} notifications={page === "Notifications"} />;
    if (page === "Governance findings" && permissions.includes("governance:read")) return <GovernancePage session={session} />;
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
