'use client'

import { useQueryState, parseAsString } from 'nuqs'

export function useSpanFilters() {
  const [flagType, setFlagType] = useQueryState(
    'flag_type',
    parseAsString.withDefault(''),
  )
  const [agentName, setAgentName] = useQueryState(
    'agent_name',
    parseAsString.withDefault(''),
  )
  const [timeRange, setTimeRange] = useQueryState(
    'time_range',
    parseAsString.withDefault('24h'),
  )

  return {
    flagType,
    setFlagType,
    agentName,
    setAgentName,
    timeRange,
    setTimeRange,
  }
}
