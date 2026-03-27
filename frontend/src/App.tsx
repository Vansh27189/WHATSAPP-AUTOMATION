import { FormEvent, startTransition, useDeferredValue, useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";

import { ErrorBoundary } from "./components/ErrorBoundary";
import { api, Institute, SendResult, Student, Summary, UnauthorizedError, User } from "./api";

type Toast = { type: "success" | "error"; text: string } | null;

type DashboardData = {
  summary: Summary | null;
  students: Student[];
  institutes: Institute[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
};

const emptyData: DashboardData = {
  summary: null,
  students: [],
  institutes: [],
  total: 0,
  page: 1,
  pageSize: 50,
  totalPages: 1,
};

function App() {
  const navigate = useNavigate();
  const [user, setUser] = useState<User | null>(() => api.getStoredSession()?.user ?? null);
  const [loadingSession, setLoadingSession] = useState(Boolean(api.getStoredSession()));
  const [toast, setToast] = useState<Toast>(null);

  useEffect(() => {
    if (!toast) return;
    const timeout = window.setTimeout(() => setToast(null), 3200);
    return () => window.clearTimeout(timeout);
  }, [toast]);

  useEffect(() => {
    if (!api.getStoredSession()) {
      setLoadingSession(false);
      return;
    }
    api.me()
      .then((nextUser) => setUser(nextUser))
      .catch(() => {
        api.clearStoredSession();
        setUser(null);
      })
      .finally(() => setLoadingSession(false));
  }, []);

  const handleLogin = async (username: string, password: string) => {
    try {
      const response = await api.login(username, password);
      startTransition(() => {
        setUser(response.user);
        setToast({ type: "success", text: `Welcome back, ${response.user.username}.` });
        navigate("/app/overview", { replace: true });
      });
    } catch (error) {
      setToast({ type: "error", text: error instanceof Error ? error.message : "Login failed" });
    }
  };

  const handleUnauthorized = async () => {
    await api.logout();
    setUser(null);
    navigate("/login", { replace: true });
  };

  const handleLogout = async () => {
    await api.logout();
    setUser(null);
    navigate("/login", { replace: true });
  };

  if (loadingSession) {
    return <SplashScreen />;
  }

  return (
    <>
      {toast ? <ToastBanner toast={toast} /> : null}
      <Routes>
        <Route path="/login" element={user ? <Navigate to="/app/overview" replace /> : <LoginPage onLogin={handleLogin} />} />
        <Route
          path="/app/*"
          element={
            user ? (
              <AuthenticatedShell user={user} onLogout={handleLogout} onToast={setToast} onUnauthorized={handleUnauthorized} />
            ) : (
              <Navigate to="/login" replace />
            )
          }
        />
        <Route path="*" element={<Navigate to={user ? "/app/overview" : "/login"} replace />} />
      </Routes>
    </>
  );
}

function SplashScreen() {
  return (
    <div className="splash-screen">
      <div className="splash-card">
        <p className="eyebrow">CoachingBot Control Center</p>
        <h1>Loading your workspace</h1>
        <p>Restoring session, verifying tokens, and preparing the dashboard.</p>
      </div>
    </div>
  );
}

function ToastBanner({ toast }: { toast: Exclude<Toast, null> }) {
  return <div className={`toast toast-${toast.type}`}>{toast.text}</div>;
}

function LoginPage({ onLogin }: { onLogin: (username: string, password: string) => Promise<void> }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    await onLogin(username, password);
    setSubmitting(false);
  };

  return (
    <div className="auth-shell">
      <section className="auth-panel auth-panel-copy">
        <p className="eyebrow">Modern FastAPI + React</p>
        <h1>Production operations, without the single-file dashboard bottleneck.</h1>
        <p>Admins can review institutes globally while each institute gets its own fee, import, and messaging workspace.</p>
      </section>
      <section className="auth-panel auth-panel-form">
        <form className="login-form" onSubmit={submit}>
          <p className="eyebrow">Secure Sign In</p>
          <h2>Welcome back</h2>
          <label>
            Username
            <input value={username} onChange={(event) => setUsername(event.target.value)} />
          </label>
          <label>
            Password
            <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
          </label>
          <button className="primary-button" disabled={submitting || !username || !password} type="submit">
            {submitting ? "Signing in..." : "Enter dashboard"}
          </button>
        </form>
      </section>
    </div>
  );
}

function AuthenticatedShell({
  user,
  onLogout,
  onToast,
  onUnauthorized,
}: {
  user: User;
  onLogout: () => Promise<void>;
  onToast: (toast: Toast) => void;
  onUnauthorized: () => Promise<void>;
}) {
  const [data, setData] = useState<DashboardData>(emptyData);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("all");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [loadingPage, setLoadingPage] = useState(false);
  const [loadingStudents, setLoadingStudents] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [broadcastMessage, setBroadcastMessage] = useState("");
  const [broadcastTarget, setBroadcastTarget] = useState<"all" | "unpaid">("all");
  const [attendancePhone, setAttendancePhone] = useState("");
  const [attendanceName, setAttendanceName] = useState("");
  const [lastSendResult, setLastSendResult] = useState<SendResult | null>(null);
  const deferredSearch = useDeferredValue(search);
  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    setPage(1);
  }, [deferredSearch, filter]);

  const handleApiError = async (error: unknown, fallback = "Request failed") => {
    if (error instanceof UnauthorizedError) {
      await onUnauthorized();
      return;
    }
    onToast({ type: "error", text: error instanceof Error ? error.message : fallback });
  };

  useEffect(() => {
    setLoadingPage(true);
    api.summary(user.role === "admin" ? undefined : user.institute ?? undefined)
      .then((response) => setData((current) => ({ ...current, summary: response.summary })))
      .catch((error) => void handleApiError(error, "Failed to load summary"))
      .finally(() => setLoadingPage(false));

    if (user.role === "admin") {
      api.institutes()
        .then((response) => setData((current) => ({ ...current, institutes: response.institutes })))
        .catch((error) => void handleApiError(error, "Failed to load institutes"));
    }
  }, [user.role, user.institute]);

  useEffect(() => {
    setLoadingStudents(true);
    api.students({
      search: deferredSearch,
      fee_status: filter,
      page,
      page_size: pageSize,
      institute: user.role === "admin" ? undefined : user.institute ?? undefined,
    })
      .then((response) => {
        setData((current) => ({
          ...current,
          students: response.students,
          total: response.total,
          page: response.page,
          pageSize: response.page_size,
          totalPages: response.total_pages,
        }));
      })
      .catch((error) => void handleApiError(error, "Failed to load students"))
      .finally(() => setLoadingStudents(false));
  }, [deferredSearch, filter, page, pageSize, user.role, user.institute]);

  useEffect(() => {
    const match = data.students.find((student) => student.phone === attendancePhone);
    if (match) setAttendanceName(match.name);
  }, [attendancePhone, data.students]);

  const unpaidCount = data.summary?.fees_pending ?? 0;

  const markStatus = async (phone: string, next: "paid" | "unpaid") => {
    try {
      if (next === "paid") {
        await api.markPaid(phone, user.role === "admin" ? undefined : user.institute ?? undefined);
      } else {
        await api.markUnpaid(phone, user.role === "admin" ? undefined : user.institute ?? undefined);
      }
      onToast({ type: "success", text: `Student marked as ${next}.` });
      setPage(1);
      navigate(location.pathname, { replace: true });
      api.summary(user.role === "admin" ? undefined : user.institute ?? undefined)
        .then((response) => setData((current) => ({ ...current, summary: response.summary })));
      api.students({
        search: deferredSearch,
        fee_status: filter,
        page,
        page_size: pageSize,
        institute: user.role === "admin" ? undefined : user.institute ?? undefined,
      }).then((response) => setData((current) => ({ ...current, students: response.students, total: response.total, page: response.page, pageSize: response.page_size, totalPages: response.total_pages })));
    } catch (error) {
      await handleApiError(error, "Status update failed");
    }
  };

  const submitImport = async (dryRun: boolean) => {
    if (!selectedFile) return;
    try {
      const result = await api.importStudents(selectedFile, user.role === "admin" ? undefined : user.institute ?? undefined, dryRun);
      onToast({ type: "success", text: dryRun ? `Preview ready: ${result.imported} rows would change.` : `Import finished: ${result.imported} rows changed.` });
      if (!dryRun) setSelectedFile(null);
    } catch (error) {
      await handleApiError(error, "Import failed");
    }
  };

  const submitReminder = async () => {
    try {
      const result = await api.sendReminders(user.role === "admin" ? undefined : user.institute ?? undefined);
      setLastSendResult(result);
      onToast({ type: "success", text: `Reminder send finished: ${result.success_count}/${result.total} ok.` });
    } catch (error) {
      await handleApiError(error, "Reminder send failed");
    }
  };

  const submitBroadcast = async () => {
    try {
      const result = await api.sendBroadcast({
        message: broadcastMessage,
        target: broadcastTarget,
        institute: user.role === "admin" ? undefined : user.institute ?? undefined,
      });
      setLastSendResult(result);
      onToast({ type: "success", text: `Broadcast finished: ${result.success_count}/${result.total} ok.` });
    } catch (error) {
      await handleApiError(error, "Broadcast failed");
    }
  };

  const submitAttendance = async () => {
    try {
      await api.sendAttendance({
        phone: attendancePhone,
        student_name: attendanceName,
        institute: user.role === "admin" ? undefined : user.institute ?? undefined,
      });
      onToast({ type: "success", text: `Attendance alert sent for ${attendanceName}.` });
    } catch (error) {
      await handleApiError(error, "Attendance alert failed");
    }
  };

  const navItems = user.role === "admin"
    ? [
        { to: "/app/overview", label: "Overview" },
        { to: "/app/students", label: "Students" },
        { to: "/app/institutes", label: "Institutes" },
      ]
    : [
        { to: "/app/overview", label: "Overview" },
        { to: "/app/students", label: "Students" },
        { to: "/app/actions", label: "Messaging" },
      ];

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div>
          <p className="eyebrow">CoachingBot</p>
          <h2>{user.role === "admin" ? "Super Admin" : user.institute}</h2>
          <p className="sidebar-copy">FastAPI backend, React control center, token refresh, and production-safe workflows.</p>
        </div>
        <nav className="nav-links">
          {navItems.map((item) => (
            <NavLink key={item.to} className={({ isActive }) => `nav-link${isActive ? " nav-link-active" : ""}`} to={item.to}>
              {item.label}
            </NavLink>
          ))}
        </nav>
        <button className="secondary-button" onClick={() => void onLogout()} type="button">Log out</button>
      </aside>
      <main className="main-panel">
        <header className="page-header">
          <div>
            <p className="eyebrow">{location.pathname.replace("/app/", "") || "overview"}</p>
            <h1>{user.role === "admin" ? "Operations overview" : "Institute operations hub"}</h1>
          </div>
          <div className="header-search">
            <input placeholder="Search name, phone, batch..." value={search} onChange={(event) => setSearch(event.target.value)} />
            <select value={filter} onChange={(event) => setFilter(event.target.value)}>
              <option value="all">All students</option>
              <option value="paid">Paid only</option>
              <option value="unpaid">Unpaid only</option>
            </select>
          </div>
        </header>

        <section className="metrics-grid">
          <MetricCard label="Total students" value={String(data.summary?.total_students ?? 0)} accent="teal" />
          <MetricCard label="Fees paid" value={String(data.summary?.fees_paid ?? 0)} accent="amber" />
          <MetricCard label="Fees pending" value={String(data.summary?.fees_pending ?? 0)} accent="coral" />
          <MetricCard label={user.role === "admin" ? "Institutes" : "Unpaid reminders"} value={String(user.role === "admin" ? data.summary?.institutes ?? 0 : unpaidCount)} accent="slate" />
        </section>

        {loadingPage ? <div className="panel muted-panel">Refreshing overview...</div> : null}

        <Routes>
          <Route path="overview" element={<ErrorBoundary><OverviewPage user={user} students={data.students} /></ErrorBoundary>} />
          <Route path="students" element={<ErrorBoundary><StudentsPage students={data.students} loading={loadingStudents} page={data.page} pageSize={data.pageSize} total={data.total} totalPages={data.totalPages} onMarkStatus={markStatus} onPageChange={setPage} onPageSizeChange={(size) => { setPage(1); setPageSize(size); }} user={user} /></ErrorBoundary>} />
          <Route path="actions" element={user.role === "admin" ? <Navigate to="/app/overview" replace /> : <ErrorBoundary><MessagingPage attendanceName={attendanceName} attendancePhone={attendancePhone} broadcastMessage={broadcastMessage} broadcastTarget={broadcastTarget} lastSendResult={lastSendResult} onAttendanceNameChange={setAttendanceName} onAttendancePhoneChange={setAttendancePhone} onBroadcastMessageChange={setBroadcastMessage} onBroadcastTargetChange={setBroadcastTarget} onImport={submitImport} onReminderSend={submitReminder} onAttendanceSend={submitAttendance} onBroadcastSend={submitBroadcast} selectedFile={selectedFile} setSelectedFile={setSelectedFile} students={data.students} /></ErrorBoundary>} />
          <Route path="institutes" element={user.role === "admin" ? <ErrorBoundary><InstitutesPage institutes={data.institutes} /></ErrorBoundary> : <Navigate to="/app/overview" replace />} />
          <Route path="*" element={<Navigate to="/app/overview" replace />} />
        </Routes>
      </main>
    </div>
  );
}

function MetricCard({ label, value, accent }: { label: string; value: string; accent: string }) {
  return <article className={`metric-card metric-${accent}`}><span>{label}</span><strong>{value}</strong></article>;
}

function OverviewPage({ user, students }: { user: User; students: Student[] }) {
  return (
    <div className="page-grid">
      <section className="panel hero-panel">
        <p className="eyebrow">Command Snapshot</p>
        <h2>{user.role === "admin" ? "See the entire network clearly." : "Stay ahead of daily fee follow-ups."}</h2>
        <p>{user.role === "admin" ? "Track institutes, data quality, and adoption from one production-ready console." : "Import safely, manage fee state, and send WhatsApp updates without risky bulk wipes."}</p>
      </section>
      <section className="panel">
        <div className="panel-head"><h3>Recent student snapshot</h3><span>{students.length} loaded</span></div>
        <div className="mini-list">
          {students.slice(0, 5).map((student) => (
            <div className="mini-row" key={`${student.institute}-${student.phone}`}>
              <div><strong>{student.name}</strong><span>{student.batch}</span></div>
              <span className={`pill ${student.fee_paid ? "pill-paid" : "pill-pending"}`}>{student.fee_paid ? "Paid" : "Pending"}</span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function StudentsPage({ students, loading, page, pageSize, total, totalPages, onMarkStatus, onPageChange, onPageSizeChange, user }: { students: Student[]; loading: boolean; page: number; pageSize: number; total: number; totalPages: number; onMarkStatus: (phone: string, next: "paid" | "unpaid") => Promise<void>; onPageChange: (page: number) => void; onPageSizeChange: (size: number) => void; user: User; }) {
  return (
    <section className="panel">
      <div className="panel-head"><div><h3>Student directory</h3><span>Search, filter, paginate, and update fee state inline.</span></div></div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Phone</th>
              <th>Batch</th>
              <th>Fee</th>
              <th>Due date</th>
              {user.role === "admin" ? <th>Institute</th> : null}
              <th>Status</th>
              {user.role === "institute" ? <th>Action</th> : null}
            </tr>
          </thead>
          <tbody>
            {loading ? Array.from({ length: 6 }).map((_, index) => (
              <tr key={`skeleton-${index}`}>
                <td colSpan={user.role === "admin" ? 7 : 7}><div className="table-skeleton" /></td>
              </tr>
            )) : students.map((student) => (
              <tr key={`${student.institute}-${student.phone}`}>
                <td>{student.name}</td>
                <td>{student.phone}</td>
                <td>{student.batch}</td>
                <td>Rs. {student.fee_amount}</td>
                <td>{student.fee_due_date}</td>
                {user.role === "admin" ? <td>{student.institute}</td> : null}
                <td><span className={`pill ${student.fee_paid ? "pill-paid" : "pill-pending"}`}>{student.fee_paid ? "Paid" : "Pending"}</span></td>
                {user.role === "institute" ? <td><button className="table-action" onClick={() => void onMarkStatus(student.phone, student.fee_paid ? "unpaid" : "paid")} type="button">{student.fee_paid ? "Mark unpaid" : "Mark paid"}</button></td> : null}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="pagination-bar">
        <span>Showing page {page} of {totalPages} • {total} students</span>
        <div className="pagination-controls">
          <select value={pageSize} onChange={(event) => onPageSizeChange(Number(event.target.value))}>
            <option value={25}>25 / page</option>
            <option value={50}>50 / page</option>
            <option value={100}>100 / page</option>
            <option value={200}>200 / page</option>
          </select>
          <button className="secondary-button" disabled={page <= 1 || loading} onClick={() => onPageChange(page - 1)} type="button">Prev</button>
          <button className="secondary-button" disabled={page >= totalPages || loading} onClick={() => onPageChange(page + 1)} type="button">Next</button>
        </div>
      </div>
    </section>
  );
}

function MessagingPage(props: { students: Student[]; selectedFile: File | null; setSelectedFile: (file: File | null) => void; broadcastMessage: string; broadcastTarget: "all" | "unpaid"; attendancePhone: string; attendanceName: string; lastSendResult: SendResult | null; onBroadcastMessageChange: (value: string) => void; onBroadcastTargetChange: (value: "all" | "unpaid") => void; onAttendancePhoneChange: (value: string) => void; onAttendanceNameChange: (value: string) => void; onImport: (dryRun: boolean) => Promise<void>; onReminderSend: () => Promise<void>; onAttendanceSend: () => Promise<void>; onBroadcastSend: () => Promise<void>; }) {
  return (
    <div className="page-grid actions-grid">
      <section className="panel stack-gap">
        <div className="panel-head"><h3>Import students</h3><span>Dry-run first, then commit once the preview looks correct.</span></div>
        <label className="file-drop"><input type="file" accept=".xlsx" onChange={(event) => props.setSelectedFile(event.target.files?.[0] ?? null)} /><span>{props.selectedFile ? props.selectedFile.name : "Choose an Excel file"}</span></label>
        <div className="button-row">
          <button className="secondary-button" disabled={!props.selectedFile} onClick={() => void props.onImport(true)} type="button">Dry run</button>
          <button className="primary-button" disabled={!props.selectedFile} onClick={() => void props.onImport(false)} type="button">Import</button>
        </div>
      </section>
      <section className="panel stack-gap">
        <div className="panel-head"><h3>Fee reminders</h3><span>Send the approved template to unpaid students only.</span></div>
        <button className="primary-button" onClick={() => void props.onReminderSend()} type="button">Send reminders</button>
      </section>
      <section className="panel stack-gap">
        <div className="panel-head"><h3>Attendance alert</h3><span>Select a student from the current page.</span></div>
        <select value={props.attendancePhone} onChange={(event) => props.onAttendancePhoneChange(event.target.value)}>
          <option value="">Select student</option>
          {props.students.map((student) => <option key={student.phone} value={student.phone}>{student.name} - {student.phone}</option>)}
        </select>
        <input value={props.attendanceName} onChange={(event) => props.onAttendanceNameChange(event.target.value)} placeholder="Student name" />
        <button className="secondary-button" onClick={() => void props.onAttendanceSend()} type="button">Send attendance alert</button>
      </section>
      <section className="panel stack-gap">
        <div className="panel-head"><h3>Broadcast</h3><span>Send custom updates to all students or unpaid only.</span></div>
        <textarea rows={6} value={props.broadcastMessage} onChange={(event) => props.onBroadcastMessageChange(event.target.value)} />
        <div className="segmented-control">
          <button className={props.broadcastTarget === "all" ? "segment-active" : ""} onClick={() => props.onBroadcastTargetChange("all")} type="button">All students</button>
          <button className={props.broadcastTarget === "unpaid" ? "segment-active" : ""} onClick={() => props.onBroadcastTargetChange("unpaid")} type="button">Unpaid only</button>
        </div>
        <button className="primary-button" onClick={() => void props.onBroadcastSend()} type="button">Send broadcast</button>
      </section>
      <section className="panel span-two-columns">
        <div className="panel-head"><h3>Last send result</h3><span>Success and failure visibility per recipient.</span></div>
        {props.lastSendResult ? <div className="mini-list">{props.lastSendResult.results.map((result) => <div className="mini-row" key={`${result.phone}-${result.status_code}`}><div><strong>{result.name}</strong><span>{result.phone}</span></div><span className={`pill ${result.success ? "pill-paid" : "pill-pending"}`}>{result.success ? `OK ${result.status_code}` : `Fail ${result.status_code}`}</span></div>)}</div> : <p className="muted-copy">No send action has been run in this session yet.</p>}
      </section>
    </div>
  );
}

function InstitutesPage({ institutes }: { institutes: Institute[] }) {
  return <section className="panel"><div className="panel-head"><h3>Institutes</h3><span>Admin-only institute list.</span></div><div className="mini-list">{institutes.map((institute) => <div className="mini-row" key={institute.username}><div><strong>{institute.name}</strong><span>{institute.username}</span></div></div>)}</div></section>;
}

export default App;
