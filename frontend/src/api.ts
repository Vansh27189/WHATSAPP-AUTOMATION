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
};

export type Institute = {
  name: string;
  username: string;
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

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

async function request<T>(path: string, init: RequestInit = {}, token?: string): Promise<T> {
  const headers = new Headers(init.headers ?? {});
  if (!(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
  });

  if (!response.ok) {
    let message = `Request failed with status ${response.status}`;
    try {
      const payload = await response.json();
      message = payload.detail ?? message;
    } catch {
      const text = await response.text();
      if (text) {
        message = text;
      }
    }
    throw new Error(message);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

export const api = {
  login: (username: string, password: string) =>
    request<{ token: string; user: User }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  me: (token: string) => request<User>("/api/auth/me", {}, token),
  logout: (token: string) => request<{ success: boolean }>("/api/auth/logout", { method: "POST" }, token),
  summary: (token: string, institute?: string) => {
    const query = institute ? `?institute=${encodeURIComponent(institute)}` : "";
    return request<{ summary: Summary }>(`/api/dashboard/summary${query}`, {}, token);
  },
  students: (token: string, params: { search?: string; fee_status?: string; institute?: string }) => {
    const query = new URLSearchParams();
    if (params.search) query.set("search", params.search);
    if (params.fee_status) query.set("fee_status", params.fee_status);
    if (params.institute) query.set("institute", params.institute);
    return request<{ students: Student[] }>(`/api/students?${query.toString()}`, {}, token);
  },
  institutes: (token: string) => request<{ institutes: Institute[] }>("/api/institutes", {}, token),
  markPaid: (token: string, phone: string, institute?: string) =>
    request<{ success: boolean; message: string }>(`/api/students/${phone}/mark-paid`, {
      method: "POST",
      body: JSON.stringify({ institute }),
    }, token),
  markUnpaid: (token: string, phone: string, institute?: string) =>
    request<{ success: boolean; message: string }>(`/api/students/${phone}/mark-unpaid`, {
      method: "POST",
      body: JSON.stringify({ institute }),
    }, token),
  importStudents: (token: string, file: File, institute?: string) => {
    const form = new FormData();
    form.append("file", file);
    if (institute) form.append("institute", institute);
    return request<{ success: boolean; imported: number; institute: string }>("/api/students/import", {
      method: "POST",
      body: form,
    }, token);
  },
  sendReminders: (token: string, institute?: string) =>
    request<SendResult>("/api/messages/reminders/send", {
      method: "POST",
      body: JSON.stringify({ institute }),
    }, token),
  sendBroadcast: (token: string, payload: { message: string; target: "all" | "unpaid"; institute?: string }) =>
    request<SendResult>("/api/messages/broadcast/send", {
      method: "POST",
      body: JSON.stringify(payload),
    }, token),
  sendAttendance: (token: string, payload: { phone: string; student_name: string; institute?: string }) =>
    request<{ success: boolean; message: string }>("/api/messages/attendance/send", {
      method: "POST",
      body: JSON.stringify(payload),
    }, token),
};