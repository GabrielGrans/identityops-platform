import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  ArrowDownRight,
  ArrowUpRight,
  Bell,
  Building2,
  CheckCircle2,
  ChevronDown,
  CircleHelp,
  Clock3,
  Command,
  CreditCard,
  LayoutDashboard,
  LockKeyhole,
  LogOut,
  MoreHorizontal,
  Search,
  Settings,
  Shield,
  ShieldCheck,
  UserPlus,
  Users,
  UsersRound,
} from "lucide-react";

import "./App.css";
import LoginPage from "./LoginPage";
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
  { label: "Audit Logs", icon: Activity, section: "GOVERNANCE" },
];

const activities = [
  {
    initials: "JD",
    name: "James Davidson",
    action: "was added to",
    target: "IT Administrators",
    time: "10 minutes ago",
    type: "Group assignment",
    color: "blue",
  },
  {
    initials: "SM",
    name: "Sarah Mitchell",
    action: "requested access to",
    target: "Finance Portal",
    time: "32 minutes ago",
    type: "Access request",
    color: "purple",
  },
  {
    initials: "RL",
    name: "Robert Lewis",
    action: "was updated in",
    target: "Employee Directory",
    time: "1 hour ago",
    type: "Profile update",
    color: "green",
  },
  {
    initials: "EW",
    name: "Emily Wilson",
    action: "was deactivated in",
    target: "Identity Management",
    time: "2 hours ago",
    type: "Account change",
    color: "orange",
  },
];

const metrics = [
  {
    label: "Total Employees",
    value: "1,284",
    change: "+12.8%",
    description: "Demo data",
    icon: Users,
    color: "blue",
    trend: "up",
  },
  {
    label: "Active Accounts",
    value: "1,196",
    change: "+8.2%",
    description: "Demo data",
    icon: CheckCircle2,
    color: "green",
    trend: "up",
  },
  {
    label: "Access Groups",
    value: "48",
    change: "+3.4%",
    description: "Demo data",
    icon: Shield,
    color: "purple",
    trend: "up",
  },
  {
    label: "Pending Requests",
    value: "23",
    change: "-5.1%",
    description: "Demo data",
    icon: Clock3,
    color: "orange",
    trend: "down",
  },
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
  const [search, setSearch] = useState("");

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
    setSearch("");
  }

  const filteredActivities = useMemo(
    () =>
      activities.filter((activity) =>
        `${activity.name} ${activity.target} ${activity.type}`
          .toLowerCase()
          .includes(search.toLowerCase()),
      ),
    [search],
  );

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
    <div className="app-shell">
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
            <label className="global-search">
              <Search size={17} />
              <input
                type="search"
                placeholder="Search anything..."
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
              <kbd>âŒ˜ K</kbd>
            </label>

            <button className="icon-button notification-button" aria-label="Notifications">
              <Bell size={19} />
              <span className="notification-dot" />
            </button>

            <div className="topbar-avatar">{initials}</div>
          </div>
        </header>

        <div className="page-content">
          {isDashboard ? (
            <>
              <section className="welcome-section">
                <div>
                  <div className="eyebrow">
                    <span className="eyebrow-dot" />
                    IDENTITY & ACCESS MANAGEMENT
                  </div>
                  <h1>Welcome back, {currentEmployee.first_name}</h1>
                  <p>
                    Here&apos;s what&apos;s happening across your identity
                    environment today.
                  </p>
                </div>

                <button
                  className="primary-button"
                  onClick={() => setActivePage("Employees")}
                >
                  <UserPlus size={17} />
                  View employees
                </button>
              </section>

              <section className="metrics-grid">
                {metrics.map((metric) => {
                  const Icon = metric.icon;

                  return (
                    <article className="metric-card" key={metric.label}>
                      <div className="metric-top">
                        <span className="metric-label">{metric.label}</span>
                        <div className={`metric-icon ${metric.color}`}>
                          <Icon size={19} />
                        </div>
                      </div>

                      <div className="metric-value">{metric.value}</div>

                      <div className="metric-footer">
                        <span className={`metric-change ${metric.trend}`}>
                          {metric.trend === "up" ? (
                            <ArrowUpRight size={15} />
                          ) : (
                            <ArrowDownRight size={15} />
                          )}
                          {metric.change}
                        </span>
                        <span className="metric-description">
                          {metric.description}
                        </span>
                      </div>
                    </article>
                  );
                })}
              </section>

              <section className="dashboard-grid">
                <article className="panel activity-panel">
                  <div className="panel-header">
                    <div>
                      <h2>Recent activity</h2>
                      <p>Illustrative activity â€” not connected to audit logs</p>
                    </div>
                    <button
                      className="text-button"
                      onClick={() => setActivePage("Audit Logs")}
                    >
                      View all
                    </button>
                  </div>

                  <div className="activity-list">
                    {filteredActivities.length > 0 ? (
                      filteredActivities.map((activity, index) => (
                        <div
                          className="activity-row"
                          key={`${activity.name}-${index}`}
                        >
                          <div className={`activity-avatar ${activity.color}`}>
                            {activity.initials}
                          </div>
                          <div className="activity-description">
                            <p>
                              <strong>{activity.name}</strong> {activity.action}{" "}
                              <strong>{activity.target}</strong>
                            </p>
                            <span>{activity.type}</span>
                          </div>
                          <time>{activity.time}</time>
                          <button
                            className="icon-button more-button"
                            aria-label="More options"
                          >
                            <MoreHorizontal size={18} />
                          </button>
                        </div>
                      ))
                    ) : (
                      <div className="empty-state">
                        No activities match your search.
                      </div>
                    )}
                  </div>
                </article>

                <article className="panel access-panel">
                  <div className="panel-header">
                    <div>
                      <h2>Access overview</h2>
                      <p>Illustrative account status distribution</p>
                    </div>
                    <button className="icon-button" aria-label="More options">
                      <MoreHorizontal size={19} />
                    </button>
                  </div>

                  <div className="access-chart">
                    <div className="donut-chart">
                      <div className="donut-center">
                        <strong>1,284</strong>
                        <span>Demo accounts</span>
                      </div>
                    </div>
                  </div>

                  <div className="chart-legend">
                    <div>
                      <span className="legend-dot active-dot" />
                      <span>Active accounts</span>
                      <strong>1,196</strong>
                    </div>
                    <div>
                      <span className="legend-dot inactive-dot" />
                      <span>Inactive accounts</span>
                      <strong>65</strong>
                    </div>
                    <div>
                      <span className="legend-dot pending-dot" />
                      <span>Pending activation</span>
                      <strong>23</strong>
                    </div>
                  </div>
                </article>
              </section>

              <section className="bottom-grid">
                <article className="panel onboarding-panel">
                  <div className="panel-header">
                    <div>
                      <h2>Identity lifecycle</h2>
                      <p>Illustrative onboarding and provisioning metrics</p>
                    </div>
                    <span className="status-pill">Demo data</span>
                  </div>

                  <div className="lifecycle-stats">
                    <div>
                      <span className="lifecycle-number">36</span>
                      <span className="lifecycle-label">New employees</span>
                    </div>
                    <div>
                      <span className="lifecycle-number">29</span>
                      <span className="lifecycle-label">Accounts provisioned</span>
                    </div>
                    <div>
                      <span className="lifecycle-number">7</span>
                      <span className="lifecycle-label">In progress</span>
                    </div>
                  </div>

                  <div className="progress-track">
                    <div className="progress-fill" />
                  </div>

                  <div className="progress-caption">
                    <span>Provisioning progress</span>
                    <strong>80.5%</strong>
                  </div>
                </article>

                <article className="panel security-panel">
                  <div className="security-icon">
                    <ShieldCheck size={23} />
                  </div>
                  <div className="security-copy">
                    <h2>Security posture</h2>
                    <p>IdentityOps authentication status</p>
                    <div className="security-status">
                      <span className="security-status-dot" />
                      Signed in
                    </div>
                  </div>
                  <button
                    className="icon-button"
                    aria-label="View security details"
                    onClick={() => setActivePage("Settings")}
                  >
                    <CreditCard size={18} />
                  </button>
                </article>
              </section>

              <footer className="page-footer">
                <span>
                  IdentityOps Platform <span className="footer-version">v0.8.0</span>
                </span>
                <span>Identity management made simple.</span>
              </footer>
            </>
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
