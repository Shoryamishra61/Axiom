export default function EmptyState({ title, description, action }: {
  title: string
  description?: string
  action?: React.ReactNode
}) {
  return (
    <div className="flex flex-col items-center justify-center py-20 gap-3 text-center">
      <div className="text-4xl text-text-muted" aria-hidden="true">○</div>
      <h2 className="text-base font-medium text-text-primary">{title}</h2>
      {description && <p className="text-sm text-text-secondary max-w-sm">{description}</p>}
      {action}
    </div>
  )
}
