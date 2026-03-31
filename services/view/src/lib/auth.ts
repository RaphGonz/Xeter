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
  setToken: (t: string) => {
    sessionStorage.setItem('xeter_token', t)
    set({ token: t })
  },
  clearToken: () => {
    sessionStorage.removeItem('xeter_token')
    set({ token: null })
  },
  hydrate: () => {
    const t = sessionStorage.getItem('xeter_token') ?? null
    set({ token: t, hydrated: true })
  },
}))

export function useHydrateAuth() {
  const hydrate = useAuthStore((s) => s.hydrate)
  const hydrated = useAuthStore((s) => s.hydrated)
  useEffect(() => {
    if (!hydrated) hydrate()
  }, [hydrate, hydrated])
}
