'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { NavBar } from '@/components/NavBar'
import { useAuthStore, useHydrateAuth } from '@/lib/auth'

export default function SpansLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  useHydrateAuth()
  const token = useAuthStore((s) => s.token)
  const hydrated = useAuthStore((s) => s.hydrated)

  useEffect(() => {
    if (hydrated && !token) {
      router.replace('/login')
    }
  }, [token, hydrated, router])

  if (!hydrated || !token) {
    return null
  }

  return (
    <div className="flex flex-col min-h-screen">
      <NavBar />
      <main className="flex-1">{children}</main>
    </div>
  )
}
