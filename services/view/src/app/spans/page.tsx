'use client'

import { useEffect, useState, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { listSpans, timeRangeToISO } from '@/lib/api'
import type { SpanListItem } from '@/lib/api'
import { useAuthStore, useHydrateAuth } from '@/lib/auth'
import { useSpanFilters } from '@/hooks/useSpanFilters'
import { FilterBar } from '@/components/FilterBar'
import { SpanTable } from '@/components/SpanTable'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'

export default function SpansPage() {
  useHydrateAuth()

  const router = useRouter()
  const token = useAuthStore((s) => s.token)
  const hydrated = useAuthStore((s) => s.hydrated)
  const clearToken = useAuthStore((s) => s.clearToken)

  const { flagType, agentName, timeRange } = useSpanFilters()

  const [spans, setSpans] = useState<SpanListItem[]>([])
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchSpans = useCallback(async () => {
    if (!token) return

    setLoading(true)
    setError(null)

    try {
      const { from_time, to_time } = timeRangeToISO(timeRange)
      const result = await listSpans(token, {
        flag_type: flagType || undefined,
        agent_name: agentName || undefined,
        from_time,
        to_time,
        limit: 50,
      })
      setSpans(result.spans)
      setNextCursor(result.next_cursor)
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to load spans'
      if (msg.includes('401') || msg.includes('HTTP 401')) {
        clearToken()
        router.replace('/login')
        return
      }
      setError(msg)
    } finally {
      setLoading(false)
    }
  }, [token, flagType, agentName, timeRange, clearToken, router])

  useEffect(() => {
    if (!hydrated) return
    if (!token) {
      router.replace('/login')
      return
    }
    fetchSpans()
  }, [hydrated, token, flagType, agentName, timeRange, fetchSpans, router])

  async function handleLoadMore() {
    if (!token || !nextCursor) return

    setLoadingMore(true)
    setError(null)

    try {
      const { from_time, to_time } = timeRangeToISO(timeRange)
      const result = await listSpans(token, {
        flag_type: flagType || undefined,
        agent_name: agentName || undefined,
        from_time,
        to_time,
        cursor: nextCursor,
        limit: 50,
      })
      setSpans((prev) => [...prev, ...result.spans])
      setNextCursor(result.next_cursor)
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to load more spans'
      setError(msg)
    } finally {
      setLoadingMore(false)
    }
  }

  function handleSpanClick(spanId: string) {
    console.log('span clicked:', spanId)
  }

  const agentNames = Array.from(new Set(spans.map((s) => s.agent_name))).sort()

  if (!hydrated) {
    return null
  }

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <div className="mb-6 flex items-center justify-between">
        <h2 className="text-xl font-semibold text-zinc-900 dark:text-zinc-50">
          Spans
        </h2>
      </div>

      <div className="mb-4">
        <FilterBar agentNames={agentNames} />
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
      ) : spans.length === 0 ? (
        <div className="rounded-md border border-zinc-200 px-4 py-12 text-center text-sm text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
          No spans found for the current filters.
        </div>
      ) : (
        <SpanTable spans={spans} onSpanClick={handleSpanClick} />
      )}

      {nextCursor && !loading && (
        <div className="mt-4 flex justify-center">
          <Button
            variant="outline"
            onClick={handleLoadMore}
            disabled={loadingMore}
          >
            {loadingMore ? 'Loading…' : 'Load more'}
          </Button>
        </div>
      )}
    </div>
  )
}
