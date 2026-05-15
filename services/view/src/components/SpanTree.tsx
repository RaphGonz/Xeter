'use client'

import { useState, useMemo } from 'react'
import { ChevronRight } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { SpanInTrace } from '@/lib/api'

interface SpanTreeProps {
  spans: SpanInTrace[]
  onSpanClick: (spanId: string) => void
}

interface TreeNode {
  span: SpanInTrace
  children: TreeNode[]
  depth: number
}

function buildTree(spans: SpanInTrace[]): TreeNode[] {
  const byId = new Map<string, SpanInTrace>(spans.map((s) => [s.span_id, s]))
  const childrenMap = new Map<string | null, SpanInTrace[]>()

  for (const span of spans) {
    const parentKey = span.parent_span_id ?? null
    // Validate parent exists — orphaned spans treated as roots
    const resolvedKey =
      parentKey !== null && byId.has(parentKey) ? parentKey : null
    const bucket = childrenMap.get(resolvedKey) ?? []
    bucket.push(span)
    childrenMap.set(resolvedKey, bucket)
  }

  function buildNodes(parentKey: string | null, depth: number): TreeNode[] {
    return (childrenMap.get(parentKey) ?? []).map((span) => ({
      span,
      children: buildNodes(span.span_id, depth + 1),
      depth,
    }))
  }

  return buildNodes(null, 0)
}

function formatDuration(startTime: string, endTime: string): string {
  const ms = new Date(endTime).getTime() - new Date(startTime).getTime()
  if (ms >= 1000) return `${(ms / 1000).toFixed(2)}s`
  return `${ms}ms`
}

interface SpanRowProps {
  node: TreeNode
  collapsed: Set<string>
  onToggle: (spanId: string) => void
  onSpanClick: (spanId: string) => void
}

function SpanRow({ node, collapsed, onToggle, onSpanClick }: SpanRowProps) {
  const { span, children, depth } = node
  const isCollapsed = collapsed.has(span.span_id)
  const hasChildren = children.length > 0
  const indentPx = depth * 20  // 20px per depth level

  return (
    <>
      <div
        className="flex cursor-pointer items-center gap-2 rounded-sm px-2 py-1.5 text-sm hover:bg-muted/50"
        style={{ paddingLeft: `${indentPx + 8}px` }}
        onClick={() => onSpanClick(span.span_id)}
      >
        {/* Chevron toggle — only on parent spans */}
        <span
          className="shrink-0 text-zinc-400 dark:text-zinc-500"
          style={{ width: '16px' }}
          onClick={(e) => {
            if (!hasChildren) return
            e.stopPropagation()
            onToggle(span.span_id)
          }}
        >
          {hasChildren && (
            <ChevronRight
              className={cn(
                'h-4 w-4 transition-transform duration-150',
                !isCollapsed && 'rotate-90',
              )}
            />
          )}
        </span>

        {/* Tool name or model fallback */}
        <span className="flex-1 truncate font-mono text-xs text-zinc-900 dark:text-zinc-50">
          {span.tool_name ?? span.model}
        </span>

        {/* Duration */}
        <span className="shrink-0 tabular-nums text-xs text-zinc-500 dark:text-zinc-400">
          {formatDuration(span.start_time, span.end_time)}
        </span>

        {/* Flag count badge — hidden when zero */}
        {span.flags.length > 0 && (
          <span className="shrink-0 inline-flex items-center rounded-full bg-zinc-100 px-2 py-0.5 text-xs font-medium text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300">
            {span.flags.length} {span.flags.length === 1 ? 'flag' : 'flags'}
          </span>
        )}
      </div>

      {/* Children — render only when not collapsed */}
      {hasChildren && !isCollapsed && (
        <>
          {children.map((child) => (
            <SpanRow
              key={child.span.span_id}
              node={child}
              collapsed={collapsed}
              onToggle={onToggle}
              onSpanClick={onSpanClick}
            />
          ))}
        </>
      )}
    </>
  )
}

export function SpanTree({ spans, onSpanClick }: SpanTreeProps) {
  // All spans expanded by default (collapsed set is empty)
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())

  const roots = useMemo(() => buildTree(spans), [spans])

  function handleToggle(spanId: string) {
    setCollapsed((prev) => {
      const next = new Set(prev)
      if (next.has(spanId)) next.delete(spanId)
      else next.add(spanId)
      return next
    })
  }

  if (roots.length === 0) {
    return (
      <div className="rounded-md border border-zinc-200 px-4 py-8 text-center text-sm text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
        No spans in this trace yet.
      </div>
    )
  }

  return (
    <div className="rounded-md border border-zinc-200 dark:border-zinc-800">
      {roots.map((node) => (
        <SpanRow
          key={node.span.span_id}
          node={node}
          collapsed={collapsed}
          onToggle={handleToggle}
          onSpanClick={onSpanClick}
        />
      ))}
    </div>
  )
}
