import { create } from 'zustand'

interface AuthState {
  token: string | null
  setToken: (t: string) => void
  clearToken: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  token: typeof window !== 'undefined'
    ? (sessionStorage.getItem('xeter_token') ?? null)
    : null,
  setToken: (t: string) => {
    if (typeof window !== 'undefined') {
      sessionStorage.setItem('xeter_token', t)
    }
    set({ token: t })
  },
  clearToken: () => {
    if (typeof window !== 'undefined') {
      sessionStorage.removeItem('xeter_token')
    }
    set({ token: null })
  },
}))
