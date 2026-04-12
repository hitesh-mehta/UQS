// Typed API client for the UQS FastAPI backend

import type { QueryResponse, CacheStatus, ModelRegistryEntry, UploadedDocument } from './types';

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// ── Auth token (stored in memory for SPA simplicity) ──────────────────────────
let _authToken: string | null = null;

export function setAuthToken(token: string) {
  _authToken = token;
  if (typeof window !== 'undefined') {
    localStorage.setItem('uqs_token', token);
  }
}

export function getAuthToken(): string | null {
  if (_authToken) return _authToken;
  if (typeof window !== 'undefined') {
    return localStorage.getItem('uqs_token');
  }
  return null;
}

export function clearAuthToken() {
  _authToken = null;
  if (typeof window !== 'undefined') {
    localStorage.removeItem('uqs_token');
  }
}

// ── Base fetch util ───────────────────────────────────────────────────────────
async function apiFetch<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getAuthToken();
  const headers: Record<string, string> = {
    ...(options.body && !(options.body instanceof FormData)
      ? { 'Content-Type': 'application/json' }
      : {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options.headers as Record<string, string> || {}),
  };

  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `API error ${res.status}`);
  }

  return res.json() as Promise<T>;
}

// ── Dev: get a test token ──────────────────────────────────────────────────────
export async function fetchDevToken(role = 'analyst'): Promise<string> {
  const data = await apiFetch<{ access_token: string }>(`/dev/token?role=${role}`, {
    method: 'POST',
  });
  return data.access_token;
}

// ── Health ────────────────────────────────────────────────────────────────────
export async function fetchHealth(): Promise<{
  status: string;
  llm_provider: string;
  llm_model: string;
  database: string;
}> {
  return apiFetch('/health');
}

// ── Query ─────────────────────────────────────────────────────────────────────
export async function sendQuery(
  query: string,
  sessionId: string,
  useCaseContext = 'enterprise data analytics platform'
): Promise<QueryResponse> {
  return apiFetch<QueryResponse>('/api/query', {
    method: 'POST',
    body: JSON.stringify({ query, session_id: sessionId, use_case_context: useCaseContext }),
  });
}

// ── Documents ─────────────────────────────────────────────────────────────────
export async function uploadDocument(
  file: File,
  sessionId: string
): Promise<UploadedDocument & { message: string }> {
  const form = new FormData();
  form.append('file', file);
  form.append('session_id', sessionId);
  return apiFetch('/api/documents/upload', {
    method: 'POST',
    body: form,
  });
}

export async function listDocuments(): Promise<{
  sources: string[];
  total_chunks: number;
}> {
  return apiFetch('/api/documents/list');
}

// ── Cache ─────────────────────────────────────────────────────────────────────
export async function fetchCacheStatus(): Promise<CacheStatus> {
  return apiFetch('/api/admin/cache/status');
}

// ── Models ────────────────────────────────────────────────────────────────────
export async function fetchModelRegistry(): Promise<Record<string, ModelRegistryEntry>> {
  return apiFetch('/api/admin/models/registry');
}

// ── Admin ─────────────────────────────────────────────────────────────────────
export async function flushCache(granularity?: string): Promise<{ flushed: Record<string, number> }> {
  const q = granularity ? `?granularity=${granularity}` : '';
  return apiFetch(`/api/admin/cache/flush${q}`, { method: 'POST' });
}

export async function rollbackModel(target: string, toVersion: number) {
  return apiFetch(`/api/admin/models/rollback?target=${target}&to_version=${toVersion}`, {
    method: 'POST',
  });
}

export async function triggerRetraining() {
  return apiFetch('/api/admin/models/retrain', { method: 'POST' });
}
