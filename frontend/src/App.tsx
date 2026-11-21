import { useEffect, useState } from "react";
import {
  Activity,
  Bell,
  Building2,
  LayoutDashboard,
  ChevronDown,
  PanelLeftClose,
  PanelLeftOpen,
  RefreshCw,
  LogOut,
  Settings,
  ShieldCheck,
  Users,
  UsersRound,
} from "lucide-react";

import "./App.css";
import "./enterprise.css";
import { Brand, BrandCredit, BrandEmblem } from "./Brand";
import LoginPage from "./LoginPage";
import { refreshLocalData, useQuery } from "./iam/data";
import { OperationsDashboard, type Metrics } from "./dashboard/OperationsDashboard";
import { AnalyticsPage } from "./dashboard/AnalyticsPage";
import { t, useLanguage, useLocalizedValidation } from "./i18n";
import { SettingsPage } from "./iam/SettingsPage";
import { IamPage } from "./iam/IamPage";
import { getCurrentEmployee, type Employee } from "./services/api";

const navigation = [
  { label: "Dashboard", icon: LayoutDashboard, section: "OVERVIEW" },
  { label: "Analytics", icon: Activity, section: "OVERVIEW" },
  { label: "Employees", icon: Users, section: "DIRECTORY" },
  { label: "Departments", icon: Building2, section: "DIRECTORY" },
  { label: "Access Groups", icon: UsersRound, section: "DIRECTORY" },
  { label: "Permissions", icon: ShieldCheck, section: "DIRECTORY" },
  { label: "Microsoft Entra ID", icon: Building2, section: "DIRECTORY" },
  { label: "Alerts & Findings", icon: Bell, section: "GOVERNANCE" },
  { label: "Audit Logs", icon: Activity, section: "GOVERNANCE" },
];

function getInitials(employee: Employee) {
  return `${employee.first_name.charAt(0)}${employee.last_name.charAt(0)}`.toUpperCase();
}

function App() {
  const language = useLanguage();
  useLocalizedValidation();
  const [token, setToken] = useState<string | null>(() =>
    sessionStorage.getItem("identityops_token"),
  );
  const [currentEmployee, setCurrentEmployee] = useState<Employee | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [compact, setCompact] = useState(() => localStorage.getItem("identityops_nav_compact") === "true");
  const [collapsed, setCollapsed] = useState<string[]>(() => {
    try {
      const value: unknown = JSON.parse(localStorage.getItem("identityops_nav_sections") ?? "[]");
      return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
    } catch { return []; }
  });
  const [activePage, setActivePage] = useState("Dashboard");
  const [syncRevision, setSyncRevision] = useState(0);
  const status = useQuery<Metrics>(token ?? "", token && currentEmployee ? "/v1/dashboard/operations" : null, syncRevision, true);

  useEffect(() => {
    const refresh = () => setSyncRevision(value => value + 1);
    window.addEventListener("focus", refresh);
    return () => {
      window.removeEventListener("focus", refresh);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function validateSession() {
      if (!token) {
        setCurrentEmployee(null);
        setAuthLoading(false);
        return;
      }

      setAuthLoading(true);

      try {
        const employee = await getCurrentEmployee(token);

        if (!cancelled) {
          setCurrentEmployee(employee);
        }
      } catch {
        sessionStorage.removeItem("identityops_token");

        if (!cancelled) {
          setToken(null);
          setCurrentEmployee(null);
        }
      } finally {
        if (!cancelled) {
          setAuthLoading(false);
        }
      }
    }

    void validateSession();

    return () => {
      cancelled = true;
    };
  }, [token]);

  useEffect(() => {
    const openDirectoryLink = () => {
      if (location.hash.startsWith("#entra/users/")) setActivePage("Employees");
      if (location.hash.startsWith("#entra/groups/")) setActivePage("Access Groups");
    };
    openDirectoryLink();
    window.addEventListener("hashchange", openDirectoryLink);
    return () => window.removeEventListener("hashchange", openDirectoryLink);
  }, []);

  useEffect(() => {
    localStorage.setItem("identityops_nav_compact", String(compact));
    localStorage.setItem("identityops_nav_sections", JSON.stringify(collapsed));
  }, [compact, collapsed]);

  function handleLogin(accessToken: string) {
    sessionStorage.setItem("identityops_token", accessToken);
    setToken(accessToken);
  }

  function handleLogout() {
    sessionStorage.removeItem("identityops_token");
    setToken(null);
    setCurrentEmployee(null);
    setActivePage("Dashboard");
  }

  if (authLoading) {
    return (
      <div className="auth-loading">
        <BrandEmblem />
        <p>{t("Verifying your session...")}</p>
      </div>
    );
  }

  if (!token || !currentEmployee) {
    return <LoginPage key={language} onLogin={handleLogin} />;
  }

  const isDashboard = activePage === "Dashboard";
  const displayName = `${currentEmployee.first_name} ${currentEmployee.last_name}`;
  const initials = getInitials(currentEmployee);

  function navigate(page: string, source?: "local" | "entra") {
    const directory = page === "Employees" ? "users" : page === "Access Groups" ? "groups" : null;
    history.replaceState(null, "", location.pathname + location.search + (directory && source ? `#${source}/${directory}` : ""));
    setActivePage(page === "Notifications" || page === "Governance findings" ? "Alerts & Findings" : page);
  }

  return (
    <div className={`app-shell governance-shell directory-shell enterprise-shell ${compact ? "compact-nav" : ""}`}>
      <aside className="sidebar">
        <Brand className="grans-sidebar" />
        <button type="button" className="icon-button sidebar-toggle" aria-expanded={!compact}
          title={t(compact ? "Expand sidebar" : "Collapse sidebar")} aria-label={t(compact ? "Expand sidebar" : "Collapse sidebar")}
          onClick={() => setCompact(value => !value)}>
          {compact ? <PanelLeftOpen size={19} /> : <PanelLeftClose size={19} />}
        </button>
        <nav className="sidebar-nav" aria-label={t("Main navigation")}>
          {["OVERVIEW", "DIRECTORY", "GOVERNANCE"].map(section => {
            const items = navigation.filter(item => item.section === section);
            const hidden = !compact && collapsed.includes(section);
            return <div className="nav-section" key={section}>
              {!compact && <button className="nav-section-label nav-category" aria-expanded={!hidden} aria-controls={`nav-${section}`}
                onClick={() => setCollapsed(value => hidden ? value.filter(key => key !== section) : [...value, section])}>
                {t(section)} <ChevronDown size={14} aria-hidden="true" />
              </button>}
              <div id={`nav-${section}`}>
                {items.filter(item => !hidden || item.label === activePage).map(item => {
                  const Icon = item.icon;
                  const label = t(item.label);
                  return <button className={`nav-item ${activePage === item.label ? "active" : ""}`}
                    key={item.label} aria-label={label} aria-current={activePage === item.label ? "page" : undefined}
                    title={label} onClick={() => navigate(item.label)}>
                    <Icon size={18} strokeWidth={1.8} aria-hidden="true" /><span>{label}</span>
                  </button>;
                })}
              </div>
            </div>;
          })}
        </nav>

        <div className="sidebar-bottom">
          <button className="nav-item" aria-label={t("Settings")} aria-current={activePage === "Settings" ? "page" : undefined} onClick={() => setActivePage("Settings")}>
            <Settings size={18} />
            <span>{t("Settings")}</span>
          </button>

          <div className="sidebar-divider" />

          <div className="user-profile">
            <div className="user-avatar">{initials}</div>
            <div className="user-copy">
              <span className="user-name">{displayName}</span>
              <span className="user-role">{currentEmployee.job_title}</span>
            </div>
            <button
              className="icon-button logout-button"
              aria-label={t("Log out")}
              title={t("Log out")}
              onClick={handleLogout}
            >
              <LogOut size={17} />
            </button>
          </div>
          <BrandCredit />
        </div>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <Brand className="grans-header" />
          <div className="breadcrumb">
            <span>IdentityOps</span>
            <span className="breadcrumb-separator">/</span>
            <strong>{t(activePage === "Access Certification" ? "Access Certification Campaigns" : activePage)}</strong>
          </div>

          <div className="topbar-actions">
            {activePage !== "Settings" && <button type="button" className="icon-button"
              title={t(isDashboard || activePage === "Analytics" ? "Refresh indicators" : "Refresh local data")}
              aria-label={t(isDashboard || activePage === "Analytics" ? "Refresh indicators" : "Refresh local data")}
              onClick={refreshLocalData}><RefreshCw size={17} aria-hidden="true" /></button>}
            <div className="topbar-avatar">{initials}</div>
          </div>
        </header>

        <div className="page-content">
          {activePage !== "Microsoft Entra ID" && status.data?.entra &&
            ["failed", "stale"].includes(status.data.entra.health) &&
            <div className="sync-warning" role="status">
              <span>{t("Entra synchronization needs attention.")}</span>
              <button className="secondary-button" onClick={() => navigate("Microsoft Entra ID")}>{t("Open synchronization diagnostics")}</button>
            </div>}
          {isDashboard ? (
            <OperationsDashboard key={language} token={token} navigate={navigate} metrics={status} />
          ) : activePage === "Analytics" ? (
            <AnalyticsPage key={language} token={token} metrics={status} />
          ) : activePage === "Settings" ? (
            <SettingsPage />
          ) : (
            <IamPage key={`${activePage}:${language}`} page={activePage} token={token} employeeId={currentEmployee.id} />
          )}
        </div>
      </main>
    </div>
  );
}

export default App;
