/**
 * Application API client.
 *
 * This deliberately reproduces the surface of the Atoms `@metagptx/web-sdk`
 * client — `client.auth.*`, `client.entities.<name>.*`, `client.apiCall.invoke`
 * — so that migrating off Atoms touches ONE file instead of the 45 call sites
 * spread across 15 components. Those components never learn that Supabase
 * exists.
 *
 * Two contracts are load-bearing and must not drift, because every caller
 * depends on them:
 *
 *   success -> resolves to `{ data }`      (callers read `res.data?.items` etc.)
 *   failure -> throws an Error with `.data` set to the parsed response body
 *              (callers read `err?.data?.detail`)
 *
 * Auth is Supabase. The session's access token is attached as a bearer token on
 * every request; the backend verifies it against the project's published ES256
 * JWKS (see backend/core/supabase_auth.py). No token is ever read from, or
 * trusted in, the frontend beyond passing it along.
 */
/* eslint-disable @typescript-eslint/no-explicit-any */
import { createClient as createSupabaseClient, type SupabaseClient } from '@supabase/supabase-js';

const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL ?? '';
const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY ?? '';

/** Where the FastAPI backend lives. Same-origin in production behind a proxy. */
const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '');

export const supabase: SupabaseClient | null =
  SUPABASE_URL && SUPABASE_ANON_KEY
    ? createSupabaseClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
        auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
      })
    : null;

export interface ApiResponse<T = any> {
  data: T;
}

/** Error shape callers already expect: `err.data.detail` and `err.message`. */
export class ApiError extends Error {
  data: unknown;
  status: number;

  constructor(message: string, status: number, data: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
  }
}

async function accessToken(): Promise<string | null> {
  if (!supabase) return null;
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  query?: Record<string, string | number | undefined | null>;
  timeout?: number;
}

async function request<T = any>(path: string, options: RequestOptions = {}): Promise<ApiResponse<T>> {
  const { method = 'GET', body, query, timeout = 30000 } = options;

  const url = new URL(`${API_BASE_URL}${path}`, window.location.origin);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== null && value !== '') {
        url.searchParams.set(key, String(value));
      }
    }
  }

  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  const token = await accessToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  // AbortController rather than a racing timer, so a slow request is actually
  // cancelled instead of merely abandoned while still consuming a connection.
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeout);

  let response: Response;
  try {
    response = await fetch(url.toString(), {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
  } catch (cause) {
    window.clearTimeout(timer);
    const aborted = cause instanceof DOMException && cause.name === 'AbortError';
    throw new ApiError(
      aborted ? 'Request timed out' : 'Network request failed',
      0,
      { detail: aborted ? 'timeout' : 'network_error' },
    );
  }
  window.clearTimeout(timer);

  const text = await response.text();
  let parsed: unknown = null;
  if (text) {
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = { detail: text };
    }
  }

  if (!response.ok) {
    const detail =
      (parsed as { detail?: unknown } | null)?.detail ?? response.statusText ?? 'Request failed';
    throw new ApiError(
      typeof detail === 'string' ? detail : `Request failed with ${response.status}`,
      response.status,
      parsed,
    );
  }

  return { data: parsed as T };
}

/** CRUD for one generated entity router at /api/v1/entities/<name>. */
function entity(name: string) {
  const base = `/api/v1/entities/${name}`;

  return {
    /**
     * `query` is sent as a JSON string because that is what the backend's
     * generated routers accept (`query: str = Query(None, ...)`).
     */
    query: async <T = any>(args: {
      query?: Record<string, unknown>;
      sort?: string;
      skip?: number;
      limit?: number;
    } = {}) =>
      request<T>(base, {
        query: {
          query: args.query && Object.keys(args.query).length ? JSON.stringify(args.query) : undefined,
          sort: args.sort,
          skip: args.skip,
          limit: args.limit,
        },
      }),

    get: async <T = any>(args: { id: string | number }) => request<T>(`${base}/${args.id}`),

    create: async <T = any>(args: { data: Record<string, unknown> }) =>
      request<T>(base, { method: 'POST', body: args.data }),

    update: async <T = any>(args: { id: string | number; data: Record<string, unknown> }) =>
      request<T>(`${base}/${args.id}`, { method: 'PUT', body: args.data }),

    delete: async <T = any>(args: { id: string | number }) =>
      request<T>(`${base}/${args.id}`, { method: 'DELETE' }),
  };
}

/**
 * Entity names are listed explicitly rather than proxied. A typo like
 * `client.entities.leed.query()` then fails at build time instead of issuing a
 * request to a route that does not exist.
 */
const entities = {
  leads: entity('leads'),
  lead_notes: entity('lead_notes'),
  workspaces: entity('workspaces'),
  workspace_members: entity('workspace_members'),
  credit_ledger: entity('credit_ledger'),
  provider_connections: entity('provider_connections'),
  offer_profiles: entity('offer_profiles'),
  search_jobs: entity('search_jobs'),
  ai_interaction_logs: entity('ai_interaction_logs'),
};

export interface AuthUser {
  id: string;
  email: string;
  name?: string;
  role: string;
}

const auth = {
  /** Resolve the current session. Returns `{ data: null }` when signed out. */
  me: async (): Promise<ApiResponse<AuthUser | null>> => {
    if (!supabase) return { data: null };

    const { data, error } = await supabase.auth.getUser();
    if (error || !data.user) return { data: null };

    const user = data.user;
    // Application role comes from app_metadata, which only the service key can
    // write. user_metadata is user-writable — reading a role from there would
    // let any signed-in user promote themselves.
    const appMetadata = (user.app_metadata ?? {}) as Record<string, unknown>;
    const userMetadata = (user.user_metadata ?? {}) as Record<string, unknown>;

    return {
      data: {
        id: user.id,
        email: user.email ?? '',
        name: (userMetadata.full_name as string) ?? (userMetadata.name as string) ?? undefined,
        role: (appMetadata.app_role as string) ?? 'user',
      },
    };
  },

  /** Send the user to the sign-in screen. */
  toLogin: () => {
    window.location.href = '/login';
  },

  login: () => {
    window.location.href = '/login';
  },

  signInWithPassword: async (email: string, password: string) => {
    if (!supabase) throw new ApiError('Authentication is not configured', 0, { detail: 'no_auth' });
    const { data, error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) throw new ApiError(error.message, error.status ?? 400, { detail: error.message });
    return { data };
  },

  signUp: async (email: string, password: string) => {
    if (!supabase) throw new ApiError('Authentication is not configured', 0, { detail: 'no_auth' });
    const { data, error } = await supabase.auth.signUp({
      email,
      password,
      options: { emailRedirectTo: `${window.location.origin}/auth/callback` },
    });
    if (error) throw new ApiError(error.message, error.status ?? 400, { detail: error.message });
    return { data };
  },

  resetPassword: async (email: string) => {
    if (!supabase) throw new ApiError('Authentication is not configured', 0, { detail: 'no_auth' });
    const { error } = await supabase.auth.resetPasswordForEmail(email, {
      redirectTo: `${window.location.origin}/reset-password`,
    });
    if (error) throw new ApiError(error.message, error.status ?? 400, { detail: error.message });
  },

  logout: async () => {
    if (supabase) await supabase.auth.signOut();
    window.location.href = '/';
  },

  /** Subscribe to sign-in / sign-out. Returns an unsubscribe function. */
  onChange: (callback: () => void) => {
    if (!supabase) return () => undefined;
    const { data } = supabase.auth.onAuthStateChange(() => callback());
    return () => data.subscription.unsubscribe();
  },
};

const apiCall = {
  /** Call a non-entity backend route. Mirrors the Atoms SDK's signature. */
  invoke: async <T = any>(args: {
    url: string;
    method?: string;
    data?: Record<string, unknown>;
    options?: { timeout?: number };
  }): Promise<ApiResponse<T>> => {
    const method = (args.method ?? 'GET').toUpperCase();
    const sendsBody = method !== 'GET' && method !== 'HEAD';

    return request<T>(args.url, {
      method,
      body: sendsBody ? args.data ?? {} : undefined,
      query: sendsBody ? undefined : (args.data as Record<string, string> | undefined),
      timeout: args.options?.timeout,
    });
  },
};

const utils = {
  openUrl: (url: string) => {
    // noopener/noreferrer: without them the opened page can reach back through
    // window.opener and navigate this tab.
    window.open(url, '_blank', 'noopener,noreferrer');
  },
};

export const client = { auth, entities, apiCall, utils };
export default client;
