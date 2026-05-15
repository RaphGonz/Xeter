'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { listTraces } from '@/lib/api'
import type { TraceListItem } from '@/lib/api'
import { useAuthStore, useHydrateAuth } from '@/lib/auth'
import { TraceTable } from '@/components/TraceTable'
import { Skeleton } from '@/components/ui/skeleton'

export default function TracesPage() {
  useHydrateAuth()

  const router = useRouter()
  const token = useAuthStore((s) => s.token)
  const hydrated = useAuthStore((s) => s.hydrated)
  const clearToken = useAuthStore((s) => s.clearToken)

  const [traces, setTraces] = useState<TraceListItem[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!hydrated) return
    if (!token) {
      router.replace('/login')
      return
    }

    setLoading(true)
    setError(null)

    listTraces(token, { limit: 50 })
      .then((result) => {
        setTraces(result.traces)
      })
      .catch((err) => {
        const msg = err instanceof Error ? err.message : 'Failed to load traces'
        if (msg.includes('401') || msg.includes('HTTP 401')) {
          clearToken()
          router.replace('/login')
          return
        }
        setError(msg)
      })
      .finally(() => setLoading(false))
  }, [hydrated, token, clearToken, router])

  if (!hydrated) return null

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <div className="mb-6 flex items-center justify-between">
        <h2 className="text-xl font-semibold text-zinc-900 dark:text-zinc-50">
          Traces
        </h2>
      </div>

      {error && (
        <div className="mb-4 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-400">
          {error}
        </div>
      )}

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-12 w-full rounded-md" />
          ))}
        </div>
      ) : traces.length === 0 ? (
        <div className="rounded-md border border-zinc-200 px-4 py-12 text-center dark:border-zinc-800">
          <p className="text-sm font-medium text-zinc-900 dark:text-zinc-50">
            No traces recorded yet
          </p>
          <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
            Traces appear here once your agents start making tool calls.
            Each trace groups all spans from a single agent run.
          </p>
        </div>
      ) : (
        <TraceTable traces={traces} />
      )}
    </div>
  )
}
