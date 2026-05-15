'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { PayloadTabs } from '@/components/PayloadTabs'
import { getSpanDetail, diagnose, getDiagnosis } from '@/lib/api'
import type { SpanDetail, SpanDetailFlag, DiagnosisResponse } from '@/lib/api'
import { cn } from '@/lib/utils'
import { formatDistanceToNow } from 'date-fns'
import { useAuthStore } from '@/lib/auth'

interface SpanDetailPanelProps {
  spanId: string | null
  open: boolean
  onClose: () => void
}

function MetaRow({ label, value }: { label: string; value: string | number | null | undefined }) {
  if (value === null || value === undefined) return null
  return (
    <div className="flex gap-2 border-b border-zinc-100 py-1.5 last:border-0 dark:border-zinc-800">
      <dt className="w-36 shrink-0 text-xs font-medium text-zinc-500 dark:text-zinc-400">{label}</dt>
      <dd className="min-w-0 flex-1 break-words font-mono text-xs text-zinc-800 dark:text-zinc-200">{String(value)}</dd>
    </div>
  )
}

function DiagnosisCard({ result }: { result: DiagnosisResponse }) {
  const verdictColors: Record<string, string> = {
    model: 'bg-orange-100 text-orange-700 border-orange-200 dark:bg-orange-950/40 dark:text-orange-400 dark:border-orange-800',
    architecture: 'bg-yellow-100 text-yellow-700 border-yellow-200 dark:bg-yellow-950/40 dark:text-yellow-400 dark:border-yellow-800',
    prompt: 'bg-blue-100 text-blue-700 border-blue-200 dark:bg-blue-950/40 dark:text-blue-400 dark:border-blue-800',
  }
  const severityColors: Record<string, string> = {
    critical: 'bg-red-100 text-red-700 border-red-200 dark:bg-red-950/40 dark:text-red-400 dark:border-red-800',
    high: 'bg-orange-100 text-orange-700 border-orange-200 dark:bg-orange-950/40 dark:text-orange-400 dark:border-orange-800',
    medium: 'bg-yellow-100 text-yellow-700 border-yellow-200 dark:bg-yellow-950/40 dark:text-yellow-400 dark:border-yellow-800',
    low: 'bg-zinc-100 text-zinc-600 border-zinc-200 dark:bg-zinc-800 dark:text-zinc-400 dark:border-zinc-700',
  }

  return (
    <div className="rounded-md border border-zinc-200 bg-white p-3 dark:border-zinc-700 dark:bg-zinc-900">
      <div className="mb-2 flex items-center gap-2">
        <Badge className={cn('border', verdictColors[result.verdict] ?? '')}>
          {result.verdict}
        </Badge>
        <Badge className={cn('border', severityColors[result.severity] ?? '')}>
          {result.severity}
        </Badge>
      </div>
      <dl>
        {result.affected_field && (
          <MetaRow label="Affected field" value={result.affected_field} />
        )}
        {result.recommended_fix && (
          <MetaRow label="Fix" value={result.recommended_fix} />
        )}
      </dl>
      <p className="mt-1 text-xs text-zinc-400 dark:text-zinc-500">
        Diagnosed {formatDistanceToNow(new Date(result.diagnosed_at), { addSuffix: true })}
      </p>
    </div>
  )
}

function FlagSection({
  flags,
  spanId,
  token,
}: {
  flags: SpanDetailFlag[]
  spanId: string
  token: string
}) {
  const [diagLoading, setDiagLoading] = useState(false)
  const [diagResult, setDiagResult] = useState<DiagnosisResponse | null>(null)
  const [diagError, setDiagError] = useState<string | null>(null)

  // Auto-load existing diagnosis when panel opens for this span
  useEffect(() => {
    let cancelled = false
    async function loadExisting() {
      setDiagLoading(true)
      setDiagError(null)
      try {
        const result = await getDiagnosis(token, spanId)
        if (!cancelled) setDiagResult(result)
      } catch (err) {
        const msg = err instanceof Error ? err.message : ''
        // 404 = no prior diagnosis — expected state, not an error to surface
        if (!cancelled && !msg.includes('404') && !msg.includes('HTTP 404')) {
          setDiagError(msg)
        }
      } finally {
        if (!cancelled) setDiagLoading(false)
      }
    }
    loadExisting()
    return () => { cancelled = true }
  }, [spanId, token])

  async function handleDiagnose() {
    setDiagLoading(true)
    setDiagResult(null)
    setDiagError(null)
    try {
      const result = await diagnose(token, spanId)
      setDiagResult(result)
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Diagnostic request failed'
      setDiagError(msg)
    } finally {
      setDiagLoading(false)
    }
  }

  return (
    <section className="rounded-md border border-red-200 bg-red-50 p-3 dark:border-red-900 dark:bg-red-950/30">
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-red-700 dark:text-red-400">
        Flags
      </h3>
      <div className="space-y-2">
        {flags.map((flag, i) => (
          <div key={i} className="space-y-1">
            <div className="flex items-center gap-2">
              <Badge variant="destructive">{flag.flag_type}</Badge>
              <span className="font-mono text-xs text-zinc-700 dark:text-zinc-300">
                score: {flag.score.toFixed(4)}
              </span>
            </div>
            {flag.detail && (
              <pre className="max-h-32 overflow-auto whitespace-pre-wrap rounded bg-white/50 p-2 font-mono text-xs text-zinc-700 dark:bg-black/20 dark:text-zinc-300">
                {JSON.stringify(flag.detail, null, 2)}
              </pre>
            )}
          </div>
        ))}
      </div>
      <div className="mt-3 space-y-2">
        <Button
          size="sm"
          variant="outline"
          onClick={handleDiagnose}
        >
          Diagnose
        </Button>
        {diagError && (
          <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-400">
            {diagError}
          </div>
        )}
        {diagLoading && (
          <div className="space-y-2">
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-4 w-3/4" />
            <p className="text-xs text-zinc-400 dark:text-zinc-500">
              Analyzing… (this may take a few seconds)
            </p>
          </div>
        )}
        {!diagLoading && diagResult && (
          <DiagnosisCard result={diagResult} />
        )}
      </div>
    </section>
  )
}

function LoadingSkeleton() {
  return (
    <div className="space-y-4 p-4">
      <Skeleton className="h-6 w-3/4" />
      <Skeleton className="h-4 w-1/2" />
      <Skeleton className="h-24 w-full" />
      <Skeleton className="h-32 w-full" />
      <Skeleton className="h-48 w-full" />
    </div>
  )
}

export function SpanDetailPanel({ spanId, open, onClose }: SpanDetailPanelProps) {
  const router = useRouter()
  const token = useAuthStore((s) => s.token)
  const clearToken = useAuthStore((s) => s.clearToken)

  const [detail, setDetail] = useState<SpanDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!spanId || !open) {
      setDetail(null)
      setError(null)
      return
    }
    if (!token) return

    setLoading(true)
    setError(null)
    setDetail(null)

    getSpanDetail(token, spanId)
      .then((data) => {
        setDetail(data)
      })
      .catch((err) => {
        const msg = err instanceof Error ? err.message : 'Failed to load span'
        if (msg.includes('401') || msg.includes('HTTP 401')) {
          clearToken()
          router.replace('/login')
          return
        }
        setError(msg)
      })
      .finally(() => {
        setLoading(false)
      })
  }, [spanId, open, token, clearToken, router])

  function formatToolArguments(raw: string | null): string {
    if (!raw) return ''
    try {
      return JSON.stringify(JSON.parse(raw), null, 2)
    } catch {
      return raw
    }
  }

  return (
    <Sheet open={open} onOpenChange={(isOpen) => { if (!isOpen) onClose() }}>
      <SheetContent side="right" className="w-full sm:max-w-2xl overflow-y-auto" showCloseButton>
        {loading && <LoadingSkeleton />}

        {error && !loading && (
          <div className="p-4">
            <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-400">
              {error}
            </div>
          </div>
        )}

        {detail && !loading && (
          <div className="flex flex-col gap-5 p-4 pb-8">
            {/* Breadcrumb — always shown when span has trace_id */}
            <nav className="flex items-center gap-1 font-mono text-xs text-zinc-400 dark:text-zinc-500">
              <span>Traces</span>
              <span className="mx-0.5">›</span>
              <Link
                href={`/traces/${detail.trace_id}`}
                className="hover:text-zinc-900 dark:hover:text-zinc-50 transition-colors"
                onClick={(e) => e.stopPropagation()}
              >
                {detail.trace_id.slice(0, 8)}
              </Link>
              <span className="mx-0.5">›</span>
              <span>{detail.span_id.slice(0, 8)}</span>
            </nav>

            {/* Header */}
            <SheetHeader className="p-0">
              <SheetTitle className="font-mono text-sm">
                {detail.span_id.length > 40
                  ? `${detail.span_id.slice(0, 40)}…`
                  : detail.span_id}
              </SheetTitle>
            </SheetHeader>

            {/* Flag section + diagnosis */}
            {token && (
              <FlagSection key={detail.span_id} flags={detail.flags} spanId={detail.span_id} token={token} />
            )}

            {/* Scores section */}
            {detail.scores.length > 0 && (
              <section>
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
                  Scores
                </h3>
                <div className="overflow-hidden rounded-md border border-zinc-200 dark:border-zinc-700">
                  {detail.scores.map((s, i) => (
                    <div
                      key={i}
                      className="flex items-center gap-2 border-b border-zinc-100 px-3 py-1.5 last:border-0 odd:bg-zinc-50 dark:border-zinc-800 dark:odd:bg-zinc-900/50"
                    >
                      <span className="flex-1 text-xs text-zinc-700 dark:text-zinc-300">
                        {s.analyzer_name} / {s.metric_name}
                      </span>
                      <span className="font-mono text-xs font-medium text-zinc-900 dark:text-zinc-100">
                        {s.score.toFixed(4)}
                      </span>
                    </div>
                  ))}
                </div>
              </section>
            )}

            {/* Span metadata */}
            <section>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
                Metadata
              </h3>
              <dl className="overflow-hidden rounded-md border border-zinc-200 px-3 dark:border-zinc-700">
                <MetaRow label="Agent name" value={detail.agent_name} />
                <MetaRow label="Agent model" value={detail.agent_model} />
                <MetaRow label="Status" value={detail.status} />
                <MetaRow label="Tool name" value={detail.tool_name} />
                <MetaRow label="Tool description" value={detail.tool_description} />
                <MetaRow label="Tool output" value={detail.tool_output} />
                <MetaRow label="Duration (ms)" value={detail.duration_ms} />
                <MetaRow label="Time begin" value={detail.time_begin} />
                <MetaRow label="Time end" value={detail.time_end} />
                <MetaRow label="Parent span ID" value={detail.parent_span_id} />
                {detail.tool_arguments && (
                  <div className="border-b border-zinc-100 py-1.5 last:border-0 dark:border-zinc-800">
                    <dt className="mb-1 text-xs font-medium text-zinc-500 dark:text-zinc-400">Tool arguments</dt>
                    <dd>
                      <pre className="overflow-auto rounded bg-zinc-50 p-2 font-mono text-xs text-zinc-800 dark:bg-zinc-900 dark:text-zinc-200 max-h-40 whitespace-pre-wrap">
                        {formatToolArguments(detail.tool_arguments)}
                      </pre>
                    </dd>
                  </div>
                )}
              </dl>
            </section>

            {/* Payload tabs */}
            <section>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
                Payloads
              </h3>
              <PayloadTabs
                prompt={detail.prompt}
                response={detail.response}
                rawResponse={detail.raw_response}
              />
            </section>
          </div>
        )}
      </SheetContent>
    </Sheet>
  )
}
