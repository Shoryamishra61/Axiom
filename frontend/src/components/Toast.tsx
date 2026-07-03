import { useToastStore } from '../store'

export default function Toast() {
  const { toasts, remove } = useToastStore()
  return (
    <div
      className="fixed bottom-6 right-6 flex flex-col gap-2 z-50"
      role="region"
      aria-label="Notifications"
      aria-live="polite"
    >
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`flex items-center gap-3 px-4 py-3 rounded-lg shadow-lg text-sm font-medium border ${
            t.type === 'success'
              ? 'bg-status-completed/20 text-status-completed border-status-completed/30'
              : 'bg-status-failed/20 text-status-failed border-status-failed/30'
          }`}
        >
          <span>{t.message}</span>
          <button
            onClick={() => remove(t.id)}
            aria-label="Dismiss notification"
            className="ml-2 opacity-60 hover:opacity-100"
          >
            ✕
          </button>
        </div>
      ))}
    </div>
  )
}
