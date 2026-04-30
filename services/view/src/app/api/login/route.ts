import { cookies } from 'next/headers'
import { NextRequest, NextResponse } from 'next/server'

const PRESENTER_URL = process.env.PRESENTER_URL ?? 'http://localhost:8000'
const IS_PROD = process.env.ENVIRONMENT === 'production'

export async function POST(req: NextRequest) {
  const body = await req.json()

  const presenterRes = await fetch(`${PRESENTER_URL}/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

  if (!presenterRes.ok) {
    const err = await presenterRes.json().catch(() => ({}))
    return NextResponse.json(err, { status: presenterRes.status })
  }

  const data = await presenterRes.json()

  // Store refresh_token as httpOnly cookie — browser JS must never see it
  const cookieStore = await cookies()  // MUST be awaited in Next.js 15+
  cookieStore.set('xeter_refresh', data.refresh_token, {
    httpOnly: true,
    secure: IS_PROD,
    sameSite: IS_PROD ? 'strict' : 'lax',
    path: '/',
    maxAge: 30 * 24 * 60 * 60,  // 30 days in seconds
  })

  // Return only session_token to browser — refresh_token is stripped
  return NextResponse.json({ session_token: data.session_token })
}
