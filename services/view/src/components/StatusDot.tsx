interface StatusDotProps {
  status: 'flagged' | 'clean' | 'pending'
  flagType?: string
}

export function StatusDot({ status, flagType }: StatusDotProps) {
  if (status === 'flagged') {
    return (
      <span className="flex items-center gap-1.5">
        <span className="inline-block h-3 w-3 rounded-full bg-red-500 shrink-0" />
        <span className="text-sm text-red-700 dark:text-red-400">
          Flagged{flagType ? ` (${flagType})` : ''}
        </span>
      </span>
    )
  }

  if (status === 'clean') {
    return (
      <span className="flex items-center gap-1.5">
        <span className="inline-block h-3 w-3 rounded-full bg-green-500 shrink-0" />
        <span className="text-sm text-green-700 dark:text-green-400">Clean</span>
      </span>
    )
  }

  return (
    <span className="flex items-center gap-1.5">
      <span className="inline-block h-3 w-3 rounded-full bg-gray-400 shrink-0" />
      <span className="text-sm text-zinc-500 dark:text-zinc-400">Pending</span>
    </span>
  )
}
