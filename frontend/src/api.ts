export type User = {
  username: string;
  role: "admin" | "institute";
  institute?: string | null;
};

export type Student = {
  name: string;
  phone: string;
  batch: string;
  fee_amount: number;
  fee_due_date: string;
  institute: string;
  fee_paid: boolean;
  created_at?: string | null;
  updated_at?: string | null;
};

export type Institute = {
  name: string;
  username: string;
  created_at?: string | null;
  updated_at?: string | null;
};

export type Summary = {
  total_students: number;
  fees_paid: number;
  fees_pending: number;
  institutes?: number | null;
};

export type SendResult = {
  total: number;
  success_count: number;
  failure_count: number;
  results: Array<{
    name: string;
    phone: string;
    status_code: number;
    success: boolean;
  }>;
};

export type StudentsResponse = {
  students: Student[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
};

type Session = {
  token: string;
  refreshToken: string;
  user: User;
};

class UnauthorizedError extends Error {}

const API_BASE = import.meta.env.VITE_API_BASE ?? "";
const STORAGE_KEY = "coachingbot_auth";
let refreshPromise: Promise<string | null> | null = null;

function getSession(): Session | null {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as Session;
  } catch {
    localStorage.removeItem(STORAGE_KEY);
    return null;
  }
}

function setSession(session: Session) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
}

function clearSession() {
  localStorage.removeItem(STORAGE_KEY);
}

function messageFromPayload(payload: unknown): string {
  if (typeof payload === "string") return payload;
  if (payload && typeof payload === "object") {
    const detail = (payload as { detail?: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object") {
      const nestedMessage = (detail as { message?: unknown }).message;
      if (typeof nestedMessage === "string") return nestedMessage;
      return JSON.stringify(detail);
    }
  }
  return "Request failed";
}

async function rawRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    let payload: unknown = null;
    try {
      payload = await response.json();
    } catch {
      payload = await response.text();
    }
    if (response.status === 401) {
      throw new UnauthorizedError(messageFromPayload(payload));
    }
    throw new Error(messageFromPayload(payload));
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

async function refreshAccessToken(): Promise<string | null> {
  if (refreshPromise) return refreshPromise;
  const session = getSession();
  if (!session?.refreshToken) return null;

  refreshPromise = rawRequest<{ token: string; refresh_token?: string; user: User }>("/api/auth/refresh", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: session.refreshToken }),
  })
    .then((payload) => {
      const nextSession: Session = {
        token: payload.token,
        refreshToken: payload.refresh_token ?? session.refreshToken,
        user: payload.user,
      };
      setSession(nextSession);
      return nextSession.token;
    })
    .catch(() => {
      clearSession();
      return null;
    })
    .finally(() => {
      refreshPromise = null;
    });

  return refreshPromise;
}

async function request<T>(path: string, init: RequestInit = {}, retryOnAuth = true): Promise<T> {
  const session = getSession();
  const headers = new Headers(init.headers ?? {});
  if (!(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (session?.token) {
    headers.set("Authorization", `Bearer ${session.token}`);
  }

  try {
    return await rawRequest<T>(path, { ...init, headers });
  } catch (error) {
    if (error instanceof UnauthorizedError && retryOnAuth && path !== "/api/auth/refresh") {
      const nextToken = await refreshAccessToken();
      if (nextToken) {
        return request<T>(path, init, false);
      }
      clearSession();
    }
    throw error;
  }
}

export const api = {
  getStoredSession: getSession,
  clearStoredSession: clearSession,
  async login(username: string, password: string) {
    const payload = await rawRequest<{ token: string; refresh_token: string; user: User }>("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    setSession({ token: payload.token, refreshToken: payload.refresh_token, user: payload.user });
    return payload;
  },
  async me() {
    return request<User>("/api/auth/me");
  },
  async logout() {
    const session = getSession();
    try {
      await request<{ success: boolean }>("/api/auth/logout", {
        method: "POST",
        body: JSON.stringify({ refresh_token: session?.refreshToken ?? null }),
      }, false);
    } finally {
      clearSession();
    }
  },
  summary(institute?: string) {
    const query = institute ? `?institute=${encodeURIComponent(institute)}` : "";
    return request<{ summary: Summary }>(`/api/dashboard/summary${query}`);
  },
  students(params: { search?: string; fee_status?: string; institute?: string; page?: number; page_size?: number }) {
    const query = new URLSearchParams();
    if (params.search) query.set("search", params.search);
    if (params.fee_status) query.set("fee_status", params.fee_status);
    if (params.institute) query.set("institute", params.institute);
    if (params.page) query.set("page", String(params.page));
    if (params.page_size) query.set("page_size", String(params.page_size));
    return request<StudentsResponse>(`/api/students?${query.toString()}`);
  },
  institutes() {
    return request<{ institutes: Institute[] }>("/api/institutes");
  },
  markPaid(phone: string, institute?: string) {
    return request<{ success: boolean; message: string }>(`/api/students/${phone}/mark-paid`, {
      method: "POST",
      body: JSON.stringify({ institute }),
    });
  },
  markUnpaid(phone: string, institute?: string) {
    return request<{ success: boolean; message: string }>(`/api/students/${phone}/mark-unpaid`, {
      method: "POST",
      body: JSON.stringify({ institute }),
    });
  },
  importStudents(file: File, institute?: string, dryRun = false) {
    const form = new FormData();
    form.append("file", file);
    if (institute) form.append("institute", institute);
    const query = dryRun ? "?dry_run=true" : "";
    return request<{ success: boolean; imported: number; institute: string; results: Array<Record<string, unknown>>; counts?: Record<string, number> }>(`/api/students/import${query}`, {
      method: "POST",
      body: form,
    });
  },
  sendReminders(institute?: string) {
    return request<SendResult>("/api/messages/reminders/send", {
      method: "POST",
      body: JSON.stringify({ institute }),
    });
  },
  sendBroadcast(payload: { message: string; target: "all" | "unpaid"; institute?: string }) {
    return request<SendResult>("/api/messages/broadcast/send", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
  sendAttendance(payload: { phone: string; student_name: string; institute?: string }) {
    return request<{ success: boolean; message: string }>("/api/messages/attendance/send", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
};

export { UnauthorizedError };
