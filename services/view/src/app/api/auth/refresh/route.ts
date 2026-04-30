import { cookies } from 'next/headers'
import { NextResponse } from 'next/server'

const PRESENTER_URL = process.env.PRESENTER_URL ?? 'http://localhost:8000'

export async function POST() {
  const cookieStore = await cookies()  // MUST be awaited in Next.js 15+
  const refreshToken = cookieStore.get('xeter_refresh')?.value

  if (!refreshToken) {
    return NextResponse.json({ error: 'no_refresh_token' }, { status: 401 })
  }

  const presenterRes = await fetch(`${PRESENTER_URL}/auth/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken }),
  })

  if (!presenterRes.ok) {
    return NextResponse.json({ error: 'refresh_failed' }, { status: 401 })
  }

  const data = await presenterRes.json()
  return NextResponse.json({ session_token: data.session_token })
}
