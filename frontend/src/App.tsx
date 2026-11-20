import { useEffect, useState } from "react";
import {
  Activity,
  Bell,
  Building2,
  CheckCircle2,
  LayoutDashboard,
  LockKeyhole,
  LogOut,
  Settings,
  ShieldCheck,
  UserPlus,
  Users,
  UsersRound,
} from "lucide-react";

import "./App.css";
import { Brand, BrandCredit, BrandEmblem } from "./Brand";
import LoginPage from "./LoginPage";
import DashboardPage from "./dashboard/DashboardPage";
import { t, useLanguage, useLocalizedValidation } from "./i18n";
import { SettingsPage } from "./iam/SettingsPage";
import { RiskIndicators } from "./iam/GovernancePage";
import { IamPage } from "./iam/IamPage";
import { getCurrentEmployee, type Employee } from "./services/api";

const navigation = [
  { label: "Dashboard", icon: LayoutDashboard, section: "OVERVIEW" },
  { label: "Employees", icon: Users, section: "IDENTITY MANAGEMENT" },
  { label: "Microsoft Entra ID", icon: Building2, section: "IDENTITY MANAGEMENT" },
  { label: "Departments", icon: Building2, section: "IDENTITY MANAGEMENT" },
  { label: "Access Groups", icon: UsersRound, section: "ACCESS MANAGEMENT" },
  { label: "Permissions", icon: ShieldCheck, section: "ACCESS MANAGEMENT" },
  { label: "Access Requests", icon: LockKeyhole, section: "ACCESS MANAGEMENT" },
  { label: "Identity Lifecycle", icon: UserPlus, section: "GOVERNANCE" },
  { label: "Access Reviews", icon: CheckCircle2, section: "GOVERNANCE" },
  { label: "Access Certification", icon: ShieldCheck, section: "GOVERNANCE" },
  { label: "Entra role governance", icon: ShieldCheck, section: "GOVERNANCE" },
  { label: "Notifications", icon: Bell, section: "GOVERNANCE" },
  { label: "Governance findings", icon: ShieldCheck, section: "GOVERNANCE" },
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
  const [activePage, setActivePage] = useState("Dashboard");

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

  return (
    <div className="app-shell governance-shell directory-shell">
      <aside className="sidebar">
        <Brand className="grans-sidebar" />

        <nav className="sidebar-nav">
          {["OVERVIEW", "IDENTITY MANAGEMENT", "ACCESS MANAGEMENT", "GOVERNANCE"].map(
            (section) => (
              <div className="nav-section" key={section}>
                <span className="nav-section-label">{t(section)}</span>
                {navigation
                  .filter((item) => item.section === section)
                  .map((item) => {
                    const Icon = item.icon;

                    return (
                      <button
                        className={`nav-item ${activePage === item.label ? "active" : ""}`}
                        key={item.label}
                        aria-label={t(item.label)}
                        aria-current={activePage === item.label ? "page" : undefined}
                        title={t(item.label)}
                        onClick={() => { if (location.hash) history.replaceState(null, "", location.pathname + location.search); setActivePage(item.label); }}
                      >
                        <Icon size={18} strokeWidth={1.8} />
                        <span>{t(item.label)}</span>
                      </button>
                    );
                  })}
              </div>
            ),
          )}
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
            <strong>{t(activePage)}</strong>
          </div>

          <div className="topbar-actions">
            <div className="topbar-avatar">{initials}</div>
          </div>
        </header>

        <div className="page-content">
          {isDashboard ? (
            <div className="iam-page"><DashboardPage key={language} token={token} navigate={setActivePage} />
              <RiskIndicators token={token} onOpen={() => setActivePage("Governance findings")} /></div>
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
