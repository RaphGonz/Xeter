export interface LoginResponse {
  session_token: string
}

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const res = await fetch(path, options)
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

export interface SpanListParams {
  flag_type?: string
  agent_name?: string
  from_time?: string
  to_time?: string
  limit?: number
  offset?: number
}

export async function listSpans(token: string, params: SpanListParams = {}) {
  const qs = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') {
      qs.set(k, String(v))
    }
  })
  const query = qs.toString() ? `?${qs.toString()}` : ''
  return request<unknown>(`/api/spans${query}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
}

export async function getSpanDetail(token: string, spanId: string) {
  return request<unknown>(`/api/spans/${spanId}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
}

export async function diagnose(
  token: string,
  spanId: string,
  flags: string[],
) {
  return request<unknown>('/api/diagnose', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ span_id: spanId, flags }),
  })
}
