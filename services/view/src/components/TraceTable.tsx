'use client'

import { useRouter } from 'next/navigation'
import { formatDistanceToNow } from 'date-fns'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import type { TraceListItem } from '@/lib/api'

interface TraceTableProps {
  traces: TraceListItem[]
}

export function TraceTable({ traces }: TraceTableProps) {
  const router = useRouter()

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-36 font-mono">Trace ID</TableHead>
          <TableHead className="w-24 text-right">Spans</TableHead>
          <TableHead className="w-24 text-right">Flags</TableHead>
          <TableHead className="w-36 text-right">Start</TableHead>
          <TableHead className="w-28 text-right">Duration</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {traces.map((trace) => (
          <TableRow
            key={trace.trace_id}
            className="cursor-pointer hover:bg-muted/50"
            onClick={() => router.push(`/traces/${trace.trace_id}`)}
          >
            <TableCell>
              <span
                className="font-mono text-xs text-zinc-900 dark:text-zinc-50"
                title={trace.trace_id}
              >
                {trace.trace_id.slice(0, 8)}
              </span>
            </TableCell>
            <TableCell className="text-right tabular-nums">
              {trace.span_count}
            </TableCell>
            <TableCell className="text-right tabular-nums">
              {trace.flag_count > 0 ? (
                <span className="inline-flex items-center rounded-full bg-zinc-100 px-2 py-0.5 text-xs font-medium text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300">
                  {trace.flag_count} {trace.flag_count === 1 ? 'flag' : 'flags'}
                </span>
              ) : (
                <span className="text-zinc-400 dark:text-zinc-500">—</span>
              )}
            </TableCell>
            <TableCell className="text-right text-zinc-500 dark:text-zinc-400">
              {formatDistanceToNow(new Date(trace.start_time), { addSuffix: true })}
            </TableCell>
            <TableCell className="text-right tabular-nums text-zinc-500 dark:text-zinc-400">
              {trace.duration >= 1
                ? `${trace.duration.toFixed(2)}s`
                : `${Math.round(trace.duration * 1000)}ms`}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
