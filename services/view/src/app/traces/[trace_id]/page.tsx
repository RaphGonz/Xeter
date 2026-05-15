'use client'

import { useEffect, useState, use } from 'react'
import { useRouter } from 'next/navigation'
import { getTraceDetail } from '@/lib/api'
import type { TraceDetailResponse } from '@/lib/api'
import { useAuthStore, useHydrateAuth } from '@/lib/auth'
import { SpanTree } from '@/components/SpanTree'
import { SpanDetailPanel } from '@/components/SpanDetailPanel'
import { Skeleton } from '@/components/ui/skeleton'
import { formatDistanceToNow } from 'date-fns'

interface PageProps {
  params: Promise<{ trace_id: string }>
}

export default function TraceDetailPage({ params }: PageProps) {
  useHydrateAuth()

  const { trace_id: traceId } = use(params)
  const router = useRouter()
  const token = useAuthStore((s) => s.token)
  const hydrated = useAuthStore((s) => s.hydrated)
  const clearToken = useAuthStore((s) => s.clearToken)

  const [traceData, setTraceData] = useState<TraceDetailResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedSpanId, setSelectedSpanId] = useState<string | null>(null)

  useEffect(() => {
    if (!hydrated) return
    if (!token) {
      router.replace('/login')
      return
    }

    setLoading(true)
    setError(null)

    getTraceDetail(token, traceId)
      .then((data) => setTraceData(data))
      .catch((err) => {
        const msg = err instanceof Error ? err.message : 'Failed to load trace'
        if (msg.includes('401') || msg.includes('HTTP 401')) {
          clearToken()
          router.replace('/login')
          return
        }
        setError(msg)
      })
      .finally(() => setLoading(false))
  }, [hydrated, token, traceId, clearToken, router])

  if (!hydrated) return null

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <div className="mb-6">
        <h2 className="font-mono text-xl font-semibold text-zinc-900 dark:text-zinc-50">
          Trace{' '}
          <span title={traceId}>{traceId.slice(0, 8)}</span>
        </h2>

        {traceData && (
          <div className="mt-1 flex gap-4 text-sm text-zinc-500 dark:text-zinc-400">
            {traceData.trace.start_time && (
              <span>
                {formatDistanceToNow(new Date(traceData.trace.start_time), { addSuffix: true })}
              </span>
            )}
            <span>
              {traceData.trace.duration >= 1
                ? `${traceData.trace.duration.toFixed(2)}s`
                : `${Math.round(traceData.trace.duration * 1000)}ms`}
            </span>
            <span>{traceData.spans.length} span{traceData.spans.length !== 1 ? 's' : ''}</span>
            {traceData.trace.flags.length > 0 && (
              <span className="inline-flex items-center rounded-full bg-zinc-100 px-2 py-0.5 text-xs font-medium text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300">
                {traceData.trace.flags.length} trace-level {traceData.trace.flags.length === 1 ? 'flag' : 'flags'}
              </span>
            )}
          </div>
        )}
      </div>

      {error && (
        <div className="mb-4 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-400">
          {error}
        </div>
      )}

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-10 w-full rounded-md" />
          ))}
        </div>
      ) : traceData ? (
        <SpanTree
          spans={traceData.spans}
          onSpanClick={(id) => setSelectedSpanId(id)}
        />
      ) : null}

      <SpanDetailPanel
        spanId={selectedSpanId}
        open={selectedSpanId !== null}
        onClose={() => setSelectedSpanId(null)}
      />
    </div>
  )
}
