import { useAuthStore } from '@/lib/auth'

export interface LoginResponse {
  session_token: string
}

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const res = await fetch(path, options)

  if (res.status === 401) {
    // Attempt transparent token refresh via httpOnly cookie
    const refreshRes = await fetch('/api/auth/refresh', { method: 'POST' })
    if (!refreshRes.ok) {
      // Refresh failed — clear token and let caller handle
      useAuthStore.getState().clearToken()
      throw new Error('HTTP 401')
    }
    const { session_token } = await refreshRes.json()
    useAuthStore.getState().setToken(session_token)

    // Retry the original request once with new token
    const retryOptions: RequestInit = {
      ...options,
      headers: {
        ...(options.headers as Record<string, string> ?? {}),
        Authorization: `Bearer ${session_token}`,
      },
    }
    const retry = await fetch(path, retryOptions)
    if (!retry.ok) {
      const body = await retry.json().catch(() => ({}))
      throw new Error(body.message ?? `HTTP ${retry.status}`)
    }
    return retry.json() as Promise<T>
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.message ?? `HTTP ${res.status}`)
  }
  return res.json() as Promise<T>
}

export async function login(
  email: string,
  password: string,
): Promise<LoginResponse> {
  return request<LoginResponse>('/api/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
}

const TIME_RANGE_MS: Record<string, number> = {
  '15m': 15 * 60 * 1000,
  '1h': 3600000,
  '6h': 6 * 3600000,
  '24h': 86400000,
  '7d': 7 * 86400000,
  '30d': 30 * 86400000,
}

export function timeRangeToISO(preset: string): { from_time: string; to_time: string } {
  const ms = TIME_RANGE_MS[preset] ?? TIME_RANGE_MS['24h']
  const now = Date.now()
  return {
    from_time: new Date(now - ms).toISOString().replace('Z', ''),
    to_time: new Date(now).toISOString().replace('Z', ''),
  }
}

export interface SpanFlag {
  flag_type: string
  score: number
}

export interface SpanListItem {
  span_id: string
  trace_id: string
  agent_name: string
  agent_model: string
  tool_name: string | null
  time_begin: string
  duration_ms: number | null
  status: 'flagged' | 'clean' | 'pending'
  flags: SpanFlag[]
}

export interface SpanListResponse {
  spans: SpanListItem[]
  next_cursor: string | null
}

export interface SpanListParams {
  flag_type?: string
  agent_name?: string
  from_time?: string
  to_time?: string
  cursor?: string
  limit?: number
}

export async function listSpans(
  token: string,
  params: SpanListParams = {},
): Promise<SpanListResponse> {
  const qs = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') {
      qs.set(k, String(v))
    }
  })
  const query = qs.toString() ? `?${qs.toString()}` : ''
  return request<SpanListResponse>(`/api/spans${query}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
}

export interface SpanDetailFlag {
  flag_type: string
  score: number
  detail: Record<string, unknown> | null
  created_at: string
}

export interface SpanScore {
  analyzer_name: string
  metric_name: string
  score: number
}

export interface SpanDetail {
  span_id: string
  trace_id: string
  parent_span_id: string | null
  agent_name: string
  agent_model: string
  tool_name: string | null
  tool_description: string | null
  tool_arguments: string | null
  tool_output: string | null
  time_begin: string
  time_end: string
  duration_ms: number | null
  status: 'flagged' | 'clean' | 'pending'
  flags: SpanDetailFlag[]
  scores: SpanScore[]
  prompt: string | null
  response: string | null
  raw_response: string | null
}

export interface DiagnosisResponse {
  diagnosis_id: string
  span_id: string
  verdict: string
  severity: string
  affected_field: string | null
  recommended_fix: string | null
  diagnosed_at: string
}

export async function getSpanDetail(token: string, spanId: string): Promise<SpanDetail> {
  return request<SpanDetail>(`/api/spans/${spanId}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
}

export async function diagnose(
  token: string,
  spanId: string,
): Promise<DiagnosisResponse> {
  return request<DiagnosisResponse>('/api/diagnose', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ span_id: spanId }),
  })
}

export async function getDiagnosis(
  token: string,
  spanId: string,
): Promise<DiagnosisResponse> {
  return request<DiagnosisResponse>(`/api/diagnose/${spanId}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
}
