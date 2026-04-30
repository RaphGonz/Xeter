import { create } from 'zustand'
import { useEffect } from 'react'

interface AuthState {
  token: string | null
  hydrated: boolean
  setToken: (t: string) => void
  clearToken: () => void
  hydrate: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  token: null,
  hydrated: false,
  setToken: (t: string) => set({ token: t }),
  clearToken: () => set({ token: null }),
  hydrate: () => set({ hydrated: true }),   // No storage read — token comes from API response
}))

export function useHydrateAuth() {
  const hydrate = useAuthStore((s) => s.hydrate)
  const hydrated = useAuthStore((s) => s.hydrated)
  useEffect(() => {
    if (!hydrated) hydrate()
  }, [hydrate, hydrated])
}
