// API-клиент панели. Access-токен живёт только в памяти (не в localStorage),
// refresh — в httpOnly-cookie. При 401 один раз обновляем токен и повторяем запрос.

export class ApiError extends Error {
  status: number;
  code: string;
  extra: Record<string, unknown>;
  constructor(status: number, code: string, extra: Record<string, unknown> = {}) {
    super(code);
    this.status = status;
    this.code = code;
    this.extra = extra;
  }
}

export interface Staff {
  id: number;
  login: string;
  display_name: string;
  role: string;
  is_active: boolean;
  last_login_at: string | null;
  created_at: string;
  permissions: string[];
}

interface TokenOut {
  access_token: string;
  expires_in: number;
  staff: Staff;
}

export type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

export interface Client {
  login(login: string, password: string): Promise<Staff>;
  restore(): Promise<Staff | null>;
  logout(): Promise<void>;
  request<T>(method: string, path: string, body?: unknown): Promise<T>;
  blob(path: string): Promise<Blob>;
  onSessionLost(handler: () => void): void;
}

async function toError(response: Response): Promise<ApiError> {
  let code = `http_${response.status}`;
  let extra: Record<string, unknown> = {};
  try {
    const data = await response.json();
    const detail = data?.detail;
    if (detail && typeof detail === "object" && typeof detail.code === "string") {
      const { code: c, ...rest } = detail;
      code = c;
      extra = rest;
    } else if (response.status === 422) {
      code = "validation_error"; // ошибка формата от FastAPI
    }
  } catch {
    /* тело не JSON */
  }
  return new ApiError(response.status, code, extra);
}

export function createClient(fetchImpl: FetchLike = (i, init) => fetch(i, init)): Client {
  let token: string | null = null;
  let refreshing: Promise<Staff | null> | null = null;
  let lost: () => void = () => {};

  async function raw(method: string, path: string, body?: unknown, auth = true): Promise<Response> {
    const headers: Record<string, string> = {};
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (auth && token) headers.Authorization = `Bearer ${token}`;
    return fetchImpl(path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: "same-origin",
    });
  }

  function refresh(): Promise<Staff | null> {
    // Параллельные запросы с истёкшим токеном делят один refresh: токен одноразовый (ротация).
    refreshing ??= (async () => {
      try {
        const response = await raw("POST", "/admin/v1/auth/refresh", undefined, false);
        if (!response.ok) {
          token = null;
          return null;
        }
        const data = (await response.json()) as TokenOut;
        token = data.access_token;
        return data.staff;
      } catch {
        return null;
      } finally {
        refreshing = null;
      }
    })();
    return refreshing;
  }

  async function authed(method: string, path: string, body?: unknown): Promise<Response> {
    let response = await raw(method, path, body);
    if (response.status === 401 && token !== null) {
      if ((await refresh()) === null) {
        lost();
        return response;
      }
      response = await raw(method, path, body);
    }
    return response;
  }

  return {
    async login(login, password) {
      const response = await raw("POST", "/admin/v1/auth/login", { login, password }, false);
      if (!response.ok) throw await toError(response);
      const data = (await response.json()) as TokenOut;
      token = data.access_token;
      return data.staff;
    },
    async restore() {
      return refresh();
    },
    async logout() {
      try {
        await raw("POST", "/admin/v1/auth/logout", undefined, false);
      } finally {
        token = null;
      }
    },
    async request<T>(method: string, path: string, body?: unknown): Promise<T> {
      const response = await authed(method, path, body);
      if (!response.ok) throw await toError(response);
      return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
    },
    async blob(path) {
      const response = await authed("GET", path);
      if (!response.ok) throw await toError(response);
      return response.blob();
    },
    onSessionLost(handler) {
      lost = handler;
    },
  };
}
