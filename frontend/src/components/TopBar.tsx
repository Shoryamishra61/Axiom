import { useAuthStore } from '../store'

export default function TopBar() {
  const { user, logout } = useAuthStore()
  return (
    <header className="h-14 shrink-0 bg-surface-1 border-b border-border flex items-center justify-between px-6">
      <span className="text-sm text-text-secondary">Distributed Job Scheduler</span>
      <div className="flex items-center gap-4">
        <span className="text-sm text-text-secondary" aria-label="Logged in as">{user?.email}</span>
        <button
          className="btn btn-ghost text-xs"
          onClick={logout}
          aria-label="Sign out"
        >
          Sign out
        </button>
      </div>
    </header>
  )
}
