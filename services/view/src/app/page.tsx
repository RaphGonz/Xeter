'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useAuthStore } from '@/lib/auth'

export default function Home() {
  const router = useRouter()
  const token = useAuthStore((s) => s.token)

  useEffect(() => {
    if (token) {
      router.replace('/spans')
    } else {
      router.replace('/login')
    }
  }, [token, router])

  return null
}
