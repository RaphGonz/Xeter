'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useAuthStore, useHydrateAuth } from '@/lib/auth'

export default function Home() {
  const router = useRouter()
  useHydrateAuth()
  const token = useAuthStore((s) => s.token)
  const hydrated = useAuthStore((s) => s.hydrated)

  useEffect(() => {
    if (!hydrated) return
    if (token) {
      router.replace('/spans')
    } else {
      router.replace('/login')
    }
  }, [token, hydrated, router])

  return null
}
