'use client'

import { ChevronDownIcon } from 'lucide-react'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuLabel,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useSpanFilters } from '@/hooks/useSpanFilters'

const FLAG_TYPE_OPTIONS: { value: string; label: string }[] = [
  { value: '', label: 'All flag types' },
  { value: 'wrong_tool', label: 'wrong_tool' },
  { value: 'wrong_tool_args', label: 'wrong_tool_args' },
  { value: 'no_tool', label: 'no_tool' },
  { value: 'excessive_tool', label: 'excessive_tool' },
  { value: 'parsing_error', label: 'parsing_error' },
]

const TIME_RANGE_OPTIONS: { value: string; label: string }[] = [
  { value: '15m', label: 'Last 15 min' },
  { value: '1h', label: 'Last hour' },
  { value: '6h', label: 'Last 6 hours' },
  { value: '24h', label: 'Last 24 hours' },
  { value: '7d', label: 'Last 7 days' },
  { value: '30d', label: 'Last 30 days' },
]

interface FilterBarProps {
  agentNames?: string[]
}

export function FilterBar({ agentNames = [] }: FilterBarProps) {
  const { flagType, setFlagType, agentName, setAgentName, timeRange, setTimeRange } =
    useSpanFilters()

  const flagTypeLabel =
    FLAG_TYPE_OPTIONS.find((o) => o.value === flagType)?.label ?? 'All flag types'

  const agentNameLabel = agentName || 'All agents'

  const timeRangeLabel =
    TIME_RANGE_OPTIONS.find((o) => o.value === timeRange)?.label ?? 'Last 24 hours'

  return (
    <div className="flex flex-wrap items-center gap-2">
      {/* Flag type */}
      <DropdownMenu>
        <DropdownMenuTrigger className="flex items-center gap-1 rounded-md border border-zinc-200 bg-white px-3 py-1.5 text-sm text-zinc-700 shadow-xs hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300 dark:hover:bg-zinc-800">
          {flagTypeLabel}
          <ChevronDownIcon className="h-3.5 w-3.5 opacity-50" />
        </DropdownMenuTrigger>
        <DropdownMenuContent>
          <DropdownMenuGroup>
            <DropdownMenuLabel>Flag type</DropdownMenuLabel>
          </DropdownMenuGroup>
          <DropdownMenuSeparator />
          {FLAG_TYPE_OPTIONS.map((opt) => (
            <DropdownMenuItem
              key={opt.value}
              onClick={() => setFlagType(opt.value || null)}
            >
              {opt.label}
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>

      {/* Agent name */}
      <DropdownMenu>
        <DropdownMenuTrigger className="flex items-center gap-1 rounded-md border border-zinc-200 bg-white px-3 py-1.5 text-sm text-zinc-700 shadow-xs hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300 dark:hover:bg-zinc-800">
          {agentNameLabel}
          <ChevronDownIcon className="h-3.5 w-3.5 opacity-50" />
        </DropdownMenuTrigger>
        <DropdownMenuContent>
          <DropdownMenuGroup>
            <DropdownMenuLabel>Agent</DropdownMenuLabel>
          </DropdownMenuGroup>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={() => setAgentName(null)}>
            All agents
          </DropdownMenuItem>
          {agentNames.map((name) => (
            <DropdownMenuItem key={name} onClick={() => setAgentName(name)}>
              {name}
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>

      {/* Time range */}
      <DropdownMenu>
        <DropdownMenuTrigger className="flex items-center gap-1 rounded-md border border-zinc-200 bg-white px-3 py-1.5 text-sm text-zinc-700 shadow-xs hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300 dark:hover:bg-zinc-800">
          {timeRangeLabel}
          <ChevronDownIcon className="h-3.5 w-3.5 opacity-50" />
        </DropdownMenuTrigger>
        <DropdownMenuContent>
          <DropdownMenuGroup>
            <DropdownMenuLabel>Time range</DropdownMenuLabel>
          </DropdownMenuGroup>
          <DropdownMenuSeparator />
          {TIME_RANGE_OPTIONS.map((opt) => (
            <DropdownMenuItem
              key={opt.value}
              onClick={() => setTimeRange(opt.value)}
            >
              {opt.label}
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  )
}
