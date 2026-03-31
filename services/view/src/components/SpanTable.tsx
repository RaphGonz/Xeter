'use client'

import { formatDistanceToNow } from 'date-fns'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { StatusDot } from '@/components/StatusDot'
import type { SpanListItem } from '@/lib/api'

interface SpanTableProps {
  spans: SpanListItem[]
  onSpanClick: (spanId: string) => void
}

export function SpanTable({ spans, onSpanClick }: SpanTableProps) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-44">Status</TableHead>
          <TableHead>Agent / Span ID</TableHead>
          <TableHead className="w-20 text-right">Score</TableHead>
          <TableHead className="w-28 text-right">Time</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {spans.map((span) => {
          const topFlag = span.flags.length
            ? span.flags.reduce((best, f) => (f.score > best.score ? f : best))
            : null

          const relativeTime = formatDistanceToNow(new Date(span.time_begin), {
            addSuffix: true,
          })

          return (
            <TableRow
              key={span.span_id}
              className="cursor-pointer hover:bg-muted/50"
              onClick={() => onSpanClick(span.span_id)}
            >
              <TableCell>
                <StatusDot
                  status={span.status}
                  flagType={topFlag?.flag_type}
                />
              </TableCell>
              <TableCell>
                <div className="flex flex-col gap-0.5">
                  <span className="font-medium text-zinc-900 dark:text-zinc-50">
                    {span.agent_name}
                  </span>
                  <span className="font-mono text-xs text-zinc-400 dark:text-zinc-500">
                    {span.span_id.length > 20
                      ? `${span.span_id.slice(0, 20)}…`
                      : span.span_id}
                  </span>
                </div>
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {topFlag != null ? topFlag.score.toFixed(2) : '—'}
              </TableCell>
              <TableCell className="text-right text-zinc-500 dark:text-zinc-400">
                {relativeTime}
              </TableCell>
            </TableRow>
          )
        })}
      </TableBody>
    </Table>
  )
}
