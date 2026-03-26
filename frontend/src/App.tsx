import { FormEvent, startTransition, useDeferredValue, useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";

import { api, Institute, SendResult, Student, Summary, User } from "./api";

type Toast = { type: "success" | "error"; text: string } | null;

type DashboardData = {
  summary: Summary | null;
  students: Student[];
  institutes: Institute[];
};

const defaultData: DashboardData = {
  summary: null,
  students: [],
  institutes: [],
};

function App() {
  const navigate = useNavigate();
  const location = useLocation();
  const [token, setToken] = useState(() => localStorage.getItem("coachingbot_token") ?? "");
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(Boolean(token));
  const [toast, setToast] = useState<Toast>(null);

  useEffect(() => {
    if (!toast) return;
    const timeout = window.setTimeout(() => setToast(null), 3500);
    return () => window.clearTimeout(timeout);
  }, [toast]);

  useEffect(() => {
    if (!token) {
      setUser(null);
      setLoading(false);
      return;
    }

    setLoading(true);
    api.me(token)
      .then((nextUser) => setUser(nextUser))
      .catch(() => {
        localStorage.removeItem("coachingbot_token");
        setToken("");
        setUser(null);
        setToast({ type: "error", text: "Your session expired. Please log in again." });
      })
      .finally(() => setLoading(false));
  }, [token]);

  useEffect(() => {
    if (!user) return;
    if (location.pathname === "/login" || location.pathname === "/") {
      navigate("/app/overview", { replace: true });
    }
  }, [location.pathname, navigate, user]);

  const handleLogin = async (username: string, password: string) => {
    setLoading(true);
    try {
      const response = await api.login(username, password);
      startTransition(() => {
        localStorage.setItem("coachingbot_token", response.token);
        setToken(response.token);
        setUser(response.user);
        setToast({ type: "success", text: `Welcome back, ${response.user.username}.` });
        navigate("/app/overview", { replace: true });
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Login failed";
      setToast({ type: "error", text: message });
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = async () => {
    if (token) {
      try {
        await api.logout(token);
      } catch {
        // Frontend logout should still succeed even if the backend is unavailable.
      }
    }
    localStorage.removeItem("coachingbot_token");
    setToken("");
    setUser(null);
    navigate("/login", { replace: true });
  };

  if (loading && !user) {
    return <SplashScreen />;
  }

  return (
    <>
      {toast ? <ToastBanner toast={toast} /> : null}
      <Routes>
        <Route
          path="/login"
          element={user ? <Navigate to="/app/overview" replace /> : <LoginPage busy={loading} onLogin={handleLogin} />}
        />
        <Route
          path="/app/*"
          element={
            user ? (
              <AuthenticatedShell token={token} user={user} onLogout={handleLogout} onToast={setToast} />
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
        <h1>Booting your operations workspace</h1>
        <p>Checking session, loading institute context, and preparing the dashboard.</p>
      </div>
    </div>
  );
}

function ToastBanner({ toast }: { toast: Exclude<Toast, null> }) {
  return <div className={`toast toast-${toast.type}`}>{toast.text}</div>;
}

function LoginPage({ busy, onLogin }: { busy: boolean; onLogin: (username: string, password: string) => Promise<void> }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    await onLogin(username, password);
  };

  return (
    <div className="auth-shell">
      <section className="auth-panel auth-panel-copy">
        <p className="eyebrow">Production UI Upgrade</p>
        <h1>Run your coaching operations from one polished control center.</h1>
        <p>
          Track fee collection, import students, trigger WhatsApp flows, and switch between admin and institute views
          without the limitations of a single-file dashboard.
        </p>
        <div className="feature-grid">
          <div>
            <strong>Admin visibility</strong>
            <span>Review institutes, search global student data, and audit performance.</span>
          </div>
          <div>
            <strong>Institute workflows</strong>
            <span>Manage uploads, attendance alerts, fee status changes, and broadcasts in one place.</span>
          </div>
          <div>
            <strong>API-first foundation</strong>
            <span>Ready for future mobile apps, background jobs, and richer reporting.</span>
          </div>
        </div>
      </section>
      <section className="auth-panel auth-panel-form">
        <form className="login-form" onSubmit={submit}>
          <p className="eyebrow">Secure Sign In</p>
          <h2>Welcome back</h2>
          <label>
            Username
            <input value={username} onChange={(event) => setUsername(event.target.value)} placeholder="admin or institute user" />
          </label>
          <label>
            Password
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="Enter your password"
            />
          </label>
          <button className="primary-button" disabled={busy || !username || !password} type="submit">
            {busy ? "Signing in..." : "Enter dashboard"}
          </button>
        </form>
      </section>
    </div>
  );
}

function AuthenticatedShell({
  token,
  user,
  onLogout,
  onToast,
}: {
  token: string;
  user: User;
  onLogout: () => Promise<void>;
  onToast: (toast: Toast) => void;
}) {
  const [data, setData] = useState<DashboardData>(defaultData);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("all");
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [sending, setSending] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [broadcastMessage, setBroadcastMessage] = useState("");
  const [broadcastTarget, setBroadcastTarget] = useState<"all" | "unpaid">("all");
  const [attendancePhone, setAttendancePhone] = useState("");
  const [attendanceName, setAttendanceName] = useState("");
  const [lastSendResult, setLastSendResult] = useState<SendResult | null>(null);
  const deferredSearch = useDeferredValue(search);
  const location = useLocation();

  const loadDashboard = async () => {
    setBusy(true);
    try {
      const summaryPromise = api.summary(token);
      const studentsPromise = api.students(token, { search: deferredSearch, fee_status: filter });
      const institutesPromise = user.role === "admin" ? api.institutes(token) : Promise.resolve({ institutes: [] });
      const [summaryResponse, studentsResponse, institutesResponse] = await Promise.all([
        summaryPromise,
        studentsPromise,
        institutesPromise,
      ]);
      setData({
        summary: summaryResponse.summary,
        students: studentsResponse.students,
        institutes: institutesResponse.institutes,
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to load dashboard";
      onToast({ type: "error", text: message });
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    loadDashboard();
  }, [deferredSearch, filter, token, user.role]);

  useEffect(() => {
    if (attendancePhone) {
      const match = data.students.find((student) => student.phone === attendancePhone);
      if (match) {
        setAttendanceName(match.name);
      }
    }
  }, [attendancePhone, data.students]);

  const unpaidStudents = data.students.filter((student) => !student.fee_paid);

  const markStatus = async (phone: string, next: "paid" | "unpaid") => {
    try {
      if (next === "paid") {
        await api.markPaid(token, phone);
        onToast({ type: "success", text: "Student marked as paid." });
      } else {
        await api.markUnpaid(token, phone);
        onToast({ type: "success", text: "Student marked as unpaid." });
      }
      await loadDashboard();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Status update failed";
      onToast({ type: "error", text: message });
    }
  };

  const submitImport = async () => {
    if (!selectedFile) return;
    setUploading(true);
    try {
      const response = await api.importStudents(token, selectedFile);
      onToast({ type: "success", text: `${response.imported} students imported for ${response.institute}.` });
      setSelectedFile(null);
      await loadDashboard();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Import failed";
      onToast({ type: "error", text: message });
    } finally {
      setUploading(false);
    }
  };

  const submitReminder = async () => {
    setSending(true);
    try {
      const response = await api.sendReminders(token);
      setLastSendResult(response);
      onToast({ type: "success", text: `Reminder job finished: ${response.success_count}/${response.total} succeeded.` });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Reminder send failed";
      onToast({ type: "error", text: message });
    } finally {
      setSending(false);
    }
  };

  const submitBroadcast = async () => {
    if (!broadcastMessage.trim()) {
      onToast({ type: "error", text: "Broadcast message cannot be empty." });
      return;
    }
    setSending(true);
    try {
      const response = await api.sendBroadcast(token, { message: broadcastMessage, target: broadcastTarget });
      setLastSendResult(response);
      onToast({ type: "success", text: `Broadcast finished: ${response.success_count}/${response.total} succeeded.` });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Broadcast failed";
      onToast({ type: "error", text: message });
    } finally {
      setSending(false);
    }
  };

  const submitAttendance = async () => {
    if (!attendancePhone || !attendanceName) {
      onToast({ type: "error", text: "Select a student before sending attendance alert." });
      return;
    }
    setSending(true);
    try {
      await api.sendAttendance(token, { phone: attendancePhone, student_name: attendanceName });
      onToast({ type: "success", text: `Attendance alert sent for ${attendanceName}.` });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Attendance alert failed";
      onToast({ type: "error", text: message });
    } finally {
      setSending(false);
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
          <p className="sidebar-copy">Production-ready control center for fee operations and communication flows.</p>
        </div>
        <nav className="nav-links">
          {navItems.map((item) => (
            <NavLink key={item.to} className={({ isActive }) => `nav-link${isActive ? " nav-link-active" : ""}`} to={item.to}>
              {item.label}
            </NavLink>
          ))}
        </nav>
        <button className="secondary-button" onClick={() => void onLogout()} type="button">
          Log out
        </button>
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
          <MetricCard
            label={user.role === "admin" ? "Institutes" : "Unpaid reminders"}
            value={String(user.role === "admin" ? data.summary?.institutes ?? 0 : unpaidStudents.length)}
            accent="slate"
          />
        </section>

        {busy ? <div className="panel muted-panel">Refreshing dashboard data...</div> : null}

        <Routes>
          <Route path="overview" element={<OverviewPage user={user} data={data} />} />
          <Route
            path="students"
            element={<StudentsPage students={data.students} onMarkStatus={markStatus} user={user} />}
          />
          <Route
            path="actions"
            element={
              user.role === "admin" ? (
                <Navigate to="/app/overview" replace />
              ) : (
                <MessagingPage
                  attendanceName={attendanceName}
                  attendancePhone={attendancePhone}
                  broadcastMessage={broadcastMessage}
                  broadcastTarget={broadcastTarget}
                  lastSendResult={lastSendResult}
                  onAttendanceNameChange={setAttendanceName}
                  onAttendancePhoneChange={setAttendancePhone}
                  onBroadcastMessageChange={setBroadcastMessage}
                  onBroadcastTargetChange={setBroadcastTarget}
                  onImport={submitImport}
                  onReminderSend={submitReminder}
                  onAttendanceSend={submitAttendance}
                  onBroadcastSend={submitBroadcast}
                  selectedFile={selectedFile}
                  setSelectedFile={setSelectedFile}
                  sending={sending}
                  students={data.students}
                  uploading={uploading}
                />
              )
            }
          />
          <Route
            path="institutes"
            element={user.role === "admin" ? <InstitutesPage institutes={data.institutes} /> : <Navigate to="/app/overview" replace />}
          />
          <Route path="*" element={<Navigate to="/app/overview" replace />} />
        </Routes>
      </main>
    </div>
  );
}

function MetricCard({ label, value, accent }: { label: string; value: string; accent: string }) {
  return (
    <article className={`metric-card metric-${accent}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

function OverviewPage({ user, data }: { user: User; data: DashboardData }) {
  return (
    <div className="page-grid">
      <section className="panel hero-panel">
        <p className="eyebrow">Command Snapshot</p>
        <h2>{user.role === "admin" ? "See the full network at a glance." : "Stay ahead of daily fee follow-ups."}</h2>
        <p>
          {user.role === "admin"
            ? "Use this workspace to monitor all institutes, spot gaps quickly, and expand the product safely."
            : "Review fee pressure, tidy student records, and trigger reminders without bouncing between scripts."}
        </p>
      </section>
      <section className="panel">
        <div className="panel-head">
          <h3>Recent student snapshot</h3>
          <span>{data.students.length} loaded</span>
        </div>
        <div className="mini-list">
          {data.students.slice(0, 5).map((student) => (
            <div className="mini-row" key={`${student.institute}-${student.phone}`}>
              <div>
                <strong>{student.name}</strong>
                <span>{student.batch}</span>
              </div>
              <span className={`pill ${student.fee_paid ? "pill-paid" : "pill-pending"}`}>
                {student.fee_paid ? "Paid" : "Pending"}
              </span>
            </div>
          ))}
          {!data.students.length ? <p className="muted-copy">No student data yet. Import a sheet to get started.</p> : null}
        </div>
      </section>
    </div>
  );
}

function StudentsPage({
  students,
  onMarkStatus,
  user,
}: {
  students: Student[];
  onMarkStatus: (phone: string, next: "paid" | "unpaid") => Promise<void>;
  user: User;
}) {
  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <h3>Student directory</h3>
          <span>Search, review fee status, and update records inline.</span>
        </div>
      </div>
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
            {students.map((student) => (
              <tr key={`${student.institute}-${student.phone}`}>
                <td>{student.name}</td>
                <td>{student.phone}</td>
                <td>{student.batch}</td>
                <td>Rs. {student.fee_amount}</td>
                <td>{student.fee_due_date}</td>
                {user.role === "admin" ? <td>{student.institute}</td> : null}
                <td>
                  <span className={`pill ${student.fee_paid ? "pill-paid" : "pill-pending"}`}>
                    {student.fee_paid ? "Paid" : "Pending"}
                  </span>
                </td>
                {user.role === "institute" ? (
                  <td>
                    <button
                      className="table-action"
                      onClick={() => void onMarkStatus(student.phone, student.fee_paid ? "unpaid" : "paid")}
                      type="button"
                    >
                      {student.fee_paid ? "Mark unpaid" : "Mark paid"}
                    </button>
                  </td>
                ) : null}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!students.length ? <p className="muted-copy">No students match the current filters.</p> : null}
    </section>
  );
}

function MessagingPage(props: {
  students: Student[];
  selectedFile: File | null;
  setSelectedFile: (file: File | null) => void;
  uploading: boolean;
  sending: boolean;
  broadcastMessage: string;
  broadcastTarget: "all" | "unpaid";
  attendancePhone: string;
  attendanceName: string;
  lastSendResult: SendResult | null;
  onBroadcastMessageChange: (value: string) => void;
  onBroadcastTargetChange: (value: "all" | "unpaid") => void;
  onAttendancePhoneChange: (value: string) => void;
  onAttendanceNameChange: (value: string) => void;
  onImport: () => Promise<void>;
  onReminderSend: () => Promise<void>;
  onAttendanceSend: () => Promise<void>;
  onBroadcastSend: () => Promise<void>;
}) {
  return (
    <div className="page-grid actions-grid">
      <section className="panel stack-gap">
        <div className="panel-head">
          <h3>Import students</h3>
          <span>Expected columns: name, phone, batch, fee_amount, fee_due_date</span>
        </div>
        <label className="file-drop">
          <input
            type="file"
            accept=".xlsx"
            onChange={(event) => props.setSelectedFile(event.target.files?.[0] ?? null)}
          />
          <span>{props.selectedFile ? props.selectedFile.name : "Choose an Excel file"}</span>
        </label>
        <button className="primary-button" disabled={!props.selectedFile || props.uploading} onClick={() => void props.onImport()} type="button">
          {props.uploading ? "Importing..." : "Import now"}
        </button>
      </section>

      <section className="panel stack-gap">
        <div className="panel-head">
          <h3>Fee reminders</h3>
          <span>Send the approved template to all unpaid students.</span>
        </div>
        <button className="primary-button" disabled={props.sending} onClick={() => void props.onReminderSend()} type="button">
          {props.sending ? "Sending..." : "Send reminder to all unpaid"}
        </button>
      </section>

      <section className="panel stack-gap">
        <div className="panel-head">
          <h3>Attendance alert</h3>
          <span>Select a student and notify the parent instantly.</span>
        </div>
        <select value={props.attendancePhone} onChange={(event) => props.onAttendancePhoneChange(event.target.value)}>
          <option value="">Select student</option>
          {props.students.map((student) => (
            <option key={student.phone} value={student.phone}>
              {student.name} - {student.phone}
            </option>
          ))}
        </select>
        <input value={props.attendanceName} onChange={(event) => props.onAttendanceNameChange(event.target.value)} placeholder="Student name" />
        <button className="secondary-button" disabled={props.sending} onClick={() => void props.onAttendanceSend()} type="button">
          Send attendance alert
        </button>
      </section>

      <section className="panel stack-gap">
        <div className="panel-head">
          <h3>Broadcast</h3>
          <span>Send custom updates to all students or only unpaid records.</span>
        </div>
        <textarea value={props.broadcastMessage} onChange={(event) => props.onBroadcastMessageChange(event.target.value)} placeholder="Holiday notice, exam date, result update..." rows={6} />
        <div className="segmented-control">
          <button
            className={props.broadcastTarget === "all" ? "segment-active" : ""}
            onClick={() => props.onBroadcastTargetChange("all")}
            type="button"
          >
            All students
          </button>
          <button
            className={props.broadcastTarget === "unpaid" ? "segment-active" : ""}
            onClick={() => props.onBroadcastTargetChange("unpaid")}
            type="button"
          >
            Unpaid only
          </button>
        </div>
        <button className="primary-button" disabled={props.sending} onClick={() => void props.onBroadcastSend()} type="button">
          Send broadcast
        </button>
      </section>

      <section className="panel span-two-columns">
        <div className="panel-head">
          <h3>Last send result</h3>
          <span>Per-recipient success and failure visibility.</span>
        </div>
        {props.lastSendResult ? (
          <>
            <div className="result-summary">
              <span>Total: {props.lastSendResult.total}</span>
              <span>Success: {props.lastSendResult.success_count}</span>
              <span>Failed: {props.lastSendResult.failure_count}</span>
            </div>
            <div className="mini-list">
              {props.lastSendResult.results.map((result) => (
                <div className="mini-row" key={`${result.phone}-${result.status_code}`}>
                  <div>
                    <strong>{result.name}</strong>
                    <span>{result.phone}</span>
                  </div>
                  <span className={`pill ${result.success ? "pill-paid" : "pill-pending"}`}>
                    {result.success ? `OK ${result.status_code}` : `Fail ${result.status_code}`}
                  </span>
                </div>
              ))}
            </div>
          </>
        ) : (
          <p className="muted-copy">No send action has been run in this session yet.</p>
        )}
      </section>
    </div>
  );
}

function InstitutesPage({ institutes }: { institutes: Institute[] }) {
  return (
    <section className="panel">
      <div className="panel-head">
        <h3>Institutes</h3>
        <span>Admin-only overview of every onboarded institute account.</span>
      </div>
      <div className="mini-list">
        {institutes.map((institute) => (
          <div className="mini-row" key={institute.username}>
            <div>
              <strong>{institute.name}</strong>
              <span>{institute.username}</span>
            </div>
          </div>
        ))}
        {!institutes.length ? <p className="muted-copy">No institutes found yet.</p> : null}
      </div>
    </section>
  );
}

export default App;