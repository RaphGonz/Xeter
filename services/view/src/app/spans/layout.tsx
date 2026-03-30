'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { NavBar } from '@/components/NavBar'
import { useAuthStore } from '@/lib/auth'

export default function SpansLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const token = useAuthStore((s) => s.token)

  useEffect(() => {
    if (!token) {
      router.replace('/login')
    }
  }, [token, router])

  if (!token) {
    return null
  }

  return (
    <div className="flex flex-col min-h-screen">
      <NavBar />
      <main className="flex-1">{children}</main>
    </div>
  )
}
