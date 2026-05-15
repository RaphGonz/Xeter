'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useAuthStore } from '@/lib/auth'

export function NavBar() {
  const router = useRouter()
  const clearToken = useAuthStore((s) => s.clearToken)

  function handleLogout() {
    clearToken()
    router.replace('/login')
  }

  return (
    <nav className="sticky top-0 z-40 w-full border-b border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
      <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
        <div className="flex items-center gap-6">
          <Link
            href="/spans"
            className="text-lg font-bold tracking-tight text-zinc-900 dark:text-zinc-50"
          >
            Xeter
          </Link>
          <Link
            href="/spans"
            className="text-sm text-zinc-500 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-50 transition-colors"
          >
            Spans
          </Link>
          <Link
            href="/traces"
            className="text-sm text-zinc-500 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-50 transition-colors"
          >
            Traces
          </Link>
          <Link
            href="#"
            className="text-sm text-zinc-500 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-50 transition-colors"
          >
            Docs
          </Link>
        </div>

        <DropdownMenu>
          <DropdownMenuTrigger className="text-sm text-zinc-500 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-50 transition-colors px-2 py-1 rounded">
            Account
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={handleLogout}>Logout</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </nav>
  )
}
