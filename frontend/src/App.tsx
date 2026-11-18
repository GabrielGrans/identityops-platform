import { useEffect, useState } from "react";
import {
  Activity,
  Building2,
  CheckCircle2,
  ChevronDown,
  CircleHelp,
  Command,
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
import LoginPage from "./LoginPage";
import DashboardPage from "./dashboard/DashboardPage";
import EmployeesPage from "./EmployeesPage";
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
  { label: "Audit Logs", icon: Activity, section: "GOVERNANCE" },
];

function getInitials(employee: Employee) {
  return `${employee.first_name.charAt(0)}${employee.last_name.charAt(0)}`.toUpperCase();
}

function App() {
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
        <div className="login-brand-mark">
          <Command size={25} />
        </div>
        <p>Verifying your session...</p>
      </div>
    );
  }

  if (!token || !currentEmployee) {
    return <LoginPage onLogin={handleLogin} />;
  }

  const isDashboard = activePage === "Dashboard";
  const isEmployees = activePage === "Employees";
  const displayName = `${currentEmployee.first_name} ${currentEmployee.last_name}`;
  const initials = getInitials(currentEmployee);

  return (
    <div className={isDashboard ? "app-shell governance-shell" : "app-shell"}>
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">
            <Command size={23} strokeWidth={2.5} />
          </div>
          <div className="brand-copy">
            <span className="brand-name">IdentityOps</span>
            <span className="brand-subtitle">IDENTITY PLATFORM</span>
          </div>
        </div>

        <div className="workspace-selector">
          <div className="workspace-avatar">IO</div>
          <div className="workspace-copy">
            <span className="workspace-name">IdentityOps</span>
            <span className="workspace-plan">Enterprise workspace</span>
          </div>
          <ChevronDown size={16} />
        </div>

        <nav className="sidebar-nav">
          {["OVERVIEW", "IDENTITY MANAGEMENT", "ACCESS MANAGEMENT", "GOVERNANCE"].map(
            (section) => (
              <div className="nav-section" key={section}>
                <span className="nav-section-label">{section}</span>
                {navigation
                  .filter((item) => item.section === section)
                  .map((item) => {
                    const Icon = item.icon;

                    return (
                      <button
                        className={`nav-item ${activePage === item.label ? "active" : ""}`}
                        key={item.label}
                        aria-label={item.label}
                        aria-current={activePage === item.label ? "page" : undefined}
                        title={item.label}
                        onClick={() => setActivePage(item.label)}
                      >
                        <Icon size={18} strokeWidth={1.8} />
                        <span>{item.label}</span>
                      </button>
                    );
                  })}
              </div>
            ),
          )}
        </nav>

        <div className="sidebar-bottom">
          <button className="nav-item" onClick={() => setActivePage("Settings")}>
            <Settings size={18} />
            <span>Settings</span>
          </button>

          <button className="nav-item" onClick={() => setActivePage("Help Center")}>
            <CircleHelp size={18} />
            <span>Help Center</span>
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
              aria-label="Log out"
              title="Log out"
              onClick={handleLogout}
            >
              <LogOut size={17} />
            </button>
          </div>
        </div>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <div className="breadcrumb">
            <span>Workspace</span>
            <span className="breadcrumb-separator">/</span>
            <strong>{activePage}</strong>
          </div>

          <div className="topbar-actions">
            <div className="topbar-avatar">{initials}</div>
          </div>
        </header>

        <div className="page-content">
          {isDashboard ? (
            <DashboardPage token={token} navigate={setActivePage} />
          ) : isEmployees && token ? (
            <EmployeesPage token={token} />
          ) : token && navigation.some((item) => item.label === activePage) ? (
            <IamPage key={activePage} page={activePage} token={token} employeeId={currentEmployee.id} />
          ) : (
            <section className="module-placeholder">
              <div className="module-placeholder-icon">
                <ShieldCheck size={30} />
              </div>
              <span className="eyebrow">IDENTITYOPS MODULE</span>
              <h1>{activePage}</h1>
              <p>
                This module is part of the IdentityOps roadmap. Its interface
                will be connected to the FastAPI backend as we implement each
                feature.
              </p>
              <button
                className="secondary-button"
                onClick={() => setActivePage("Dashboard")}
              >
                Back to dashboard
              </button>
            </section>
          )}
        </div>
      </main>
    </div>
  );
}

export default App;
