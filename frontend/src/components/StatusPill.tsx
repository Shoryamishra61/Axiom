// Maps job/execution status string to pill CSS class + label
const STATUS_MAP: Record<string, { cls: string; label: string }> = {
  queued:    { cls: 'pill-queued',    label: 'Queued' },
  scheduled: { cls: 'pill-scheduled', label: 'Scheduled' },
  claimed:   { cls: 'pill-claimed',   label: 'Claimed' },
  running:   { cls: 'pill-running',   label: 'Running' },
  completed: { cls: 'pill-completed', label: 'Completed' },
  failed:    { cls: 'pill-failed',    label: 'Failed' },
  cancelled: { cls: 'pill-dead',      label: 'Cancelled' },
  dead:      { cls: 'pill-dead',      label: 'Dead' },
  active:    { cls: 'pill-running',   label: 'Active' },
  idle:      { cls: 'pill-queued',    label: 'Idle' },
}

export default function StatusPill({ status }: { status: string }) {
  const { cls, label } = STATUS_MAP[status] ?? { cls: 'pill-queued', label: status }
  // pill = color + text — never color alone (WCAG)
  return <span className={`pill ${cls}`}>{label}</span>
}
