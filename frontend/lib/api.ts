// Typed API client for the UQS FastAPI backend

import type { CacheStatus, ModelRegistryEntry, QueryResponse, UploadedDocument } from './types';

const isBrowser = typeof window !== 'undefined';
// Use relative proxy in the browser to defeat Mixed Content errors (HTTPS -> HTTP)
const BASE_URL = isBrowser 
  ? (process.env.NEXT_PUBLIC_API_URL || '/proxy') 
  : (process.env.BACKEND_API_URL || 'http://localhost:8000');

// ── Auth token ────────────────────────────────────────────────────────────────
let _authToken: string | null = null;

export function setAuthToken(token: string) {
  _authToken = token;
  if (typeof window !== 'undefined') localStorage.setItem('uqs_token', token);
}

export function getAuthToken(): string | null {
  if (_authToken) return _authToken;
  if (typeof window !== 'undefined') return localStorage.getItem('uqs_token');
  return null;
}

export function clearAuthToken() {
  _authToken = null;
  if (typeof window !== 'undefined') localStorage.removeItem('uqs_token');
}

// ── Base fetch ────────────────────────────────────────────────────────────────
async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getAuthToken();
  const headers: Record<string, string> = {
    ...(options.body && !(options.body instanceof FormData)
      ? { 'Content-Type': 'application/json' }
      : {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options.headers as Record<string, string> || {}),
  };
  const res = await fetch(`${BASE_URL}${path}`, { ...options, headers });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `API error ${res.status}`);
  }
  return res.json() as Promise<T>;
}

// ── Dev token ─────────────────────────────────────────────────────────────────
export async function fetchDevToken(role = 'analyst'): Promise<string> {
  const data = await apiFetch<{ access_token: string }>(`/dev/token?role=${role}`, {
    method: 'POST',
  });
  return data.access_token;
}

// ── Health ────────────────────────────────────────────────────────────────────
export async function fetchHealth(): Promise<{
  status: string; llm_provider: string; llm_model: string; database: string; pipeline: string;
}> {
  return apiFetch('/health');
}

// ── Full query (no streaming) ─────────────────────────────────────────────────
export async function sendQuery(
  query: string,
  sessionId: string,
  useCaseContext = 'enterprise data analytics platform',
): Promise<QueryResponse> {
  return apiFetch<QueryResponse>('/api/query', {
    method: 'POST',
    body: JSON.stringify({ query, session_id: sessionId, use_case_context: useCaseContext }),
  });
}

// ── Streaming query (SSE) ─────────────────────────────────────────────────────
export interface StreamCallbacks {
  onToken: (token: string) => void;
  onMetadata: (meta: Omit<QueryResponse, 'answer'>) => void;
  onDone: () => void;
  onError: (err: string) => void;
}

/**
 * Stream a query response via SSE.
 * Falls back to regular POST if SSE fails.
 */
export async function streamQuery(
  query: string,
  sessionId: string,
  callbacks: StreamCallbacks,
  useCaseContext = 'enterprise data analytics platform',
): Promise<void> {
  const token = getAuthToken();
  const params = new URLSearchParams({
    query,
    session_id: sessionId,
    use_case_context: useCaseContext,
  });

  let usedSSE = false;

  try {
    const res = await fetch(`${BASE_URL}/api/query/stream?${params}`, {
      headers: {
        Accept: 'text/event-stream',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    });

    if (!res.ok || !res.body) {
      throw new Error(`SSE not available: ${res.status}`);
    }

    usedSSE = true;
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() ?? '';

      let currentEvent = '';
      for (const line of lines) {
        if (line.startsWith('event: ')) {
          currentEvent = line.slice(7).trim();
        } else if (line.startsWith('data: ')) {
          const raw = line.slice(6).trim();
          if (!raw || raw === '{}') {
            if (currentEvent === 'done') callbacks.onDone();
            continue;
          }
          try {
            const data = JSON.parse(raw);
            if (currentEvent === 'token' && data.token) {
              callbacks.onToken(data.token);
            } else if (currentEvent === 'metadata') {
              callbacks.onMetadata(data);
            } else if (currentEvent === 'error') {
              callbacks.onError(data.detail || 'Streaming error');
              return;
            }
          } catch {
            // ignore malformed JSON chunks
          }
        }
      }
    }

    if (usedSSE) callbacks.onDone();
  } catch (_sseErr) {
    // Fallback to regular POST
    try {
      const result = await sendQuery(query, sessionId, useCaseContext);
      // Simulate streaming by calling onToken for each word
      const words = result.answer.split(' ');
      for (let i = 0; i < words.length; i++) {
        callbacks.onToken(words[i] + (i < words.length - 1 ? ' ' : ''));
        await new Promise((r) => setTimeout(r, 8));
      }
      const { answer: _a, ...meta } = result;
      callbacks.onMetadata(meta);
      callbacks.onDone();
    } catch (fallbackErr) {
      callbacks.onError(fallbackErr instanceof Error ? fallbackErr.message : 'Request failed');
    }
  }
}

// ── Documents ─────────────────────────────────────────────────────────────────
export async function uploadDocument(file: File, sessionId: string): Promise<UploadedDocument & { message: string }> {
  const form = new FormData();
  form.append('file', file);
  form.append('session_id', sessionId);
  return apiFetch('/api/documents/upload', { method: 'POST', body: form });
}

export async function listDocuments(): Promise<{ sources: string[]; total_chunks: number }> {
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
export async function flushCache(granularity?: string) {
  const q = granularity ? `?granularity=${granularity}` : '';
  return apiFetch(`/api/admin/cache/flush${q}`, { method: 'POST' });
}

export async function triggerRetraining() {
  return apiFetch('/api/admin/models/retrain', { method: 'POST' });
}
