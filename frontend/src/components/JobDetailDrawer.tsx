import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { jobApi } from '../api'
import StatusPill from '../components/StatusPill'

interface Props { job: any; onClose: () => void }

function ExecutionCard({ execution }: { execution: any }) {
  const { data: logs = [] } = useQuery({
    queryKey: ['logs', execution.id],
    queryFn: () => jobApi.logs(execution.id),
    refetchInterval: execution.status === 'running' ? 5000 : false,
  })

  return (
    <div className="panel p-4 flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-text-secondary">Attempt #{execution.attempt}</span>
        <StatusPill status={execution.status} />
      </div>
      <div className="text-xs text-text-muted">
        Worker: {execution.worker_id?.slice(0, 8) ?? '—'} · Started: {new Date(execution.started_at).toLocaleString()}
        {execution.finished_at && ` · Finished: ${new Date(execution.finished_at).toLocaleString()}`}
        {execution.duration_ms != null && ` · ${execution.duration_ms}ms`}
      </div>
      {execution.error_msg && <pre className="bg-status-failed/10 border border-status-failed/20 rounded p-2 text-xs text-status-failed whitespace-pre-wrap break-all">{execution.error_msg}</pre>}
      {logs.length > 0 && (
        <div className="bg-surface-2 rounded p-3 flex flex-col gap-1" aria-label="Execution logs">
          {logs.map((log: any) => (
            <div key={log.id} className="font-mono text-xs">
              <span className="text-text-muted">{new Date(log.logged_at).toLocaleTimeString()} </span>
              <span className={log.level === 'error' ? 'text-status-failed' : 'text-text-secondary'}>{log.level.toUpperCase()} {log.message}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function JobDetailDrawer({ job, onClose }: Props) {
  const [tab, setTab] = useState<'overview' | 'executions' | 'payload'>('overview')

  const { data: executions = [] } = useQuery({
    queryKey: ['executions', job.id],
    queryFn: () => jobApi.executions(job.id),
    refetchInterval: job.status === 'running' || job.status === 'claimed' ? 5000 : false,
  })

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/50 z-40"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Drawer */}
      <aside
        className="fixed right-0 top-0 h-full w-full max-w-xl bg-surface-1 border-l border-border z-50 flex flex-col overflow-hidden"
        role="dialog"
        aria-label={`Job details for ${job.id.slice(0, 8)}`}
        aria-modal="true"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <div className="flex flex-col gap-0.5">
            <span className="text-xs text-text-muted font-mono">{job.id}</span>
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium capitalize">{job.job_type} job</span>
              <StatusPill status={job.status} />
            </div>
          </div>
          <button
            className="btn btn-ghost p-2"
            onClick={onClose}
            aria-label="Close job detail panel"
          >
            ✕
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-border px-6">
          {(['overview', 'executions', 'payload'] as const).map((t) => (
            <button
              key={t}
              className={`px-4 py-2 text-sm capitalize border-b-2 transition-colors ${
                tab === t
                  ? 'border-accent text-text-primary'
                  : 'border-transparent text-text-secondary hover:text-text-primary'
              }`}
              onClick={() => setTab(t)}
            >
              {t}
            </button>
          ))}
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-6">
          {tab === 'overview' && (
            <dl className="flex flex-col gap-4">
              {[
                ['Status', <StatusPill status={job.status} />],
                ['Type', job.job_type],
                ['Priority', job.priority],
                ['Attempts', `${job.attempt_count} / ${job.max_attempts}`],
                ['Scheduled at', new Date(job.run_at).toLocaleString()],
                ['Created', new Date(job.created_at).toLocaleString()],
                ['Completed', job.completed_at ? new Date(job.completed_at).toLocaleString() : '—'],
                ['Batch ID', job.batch_id ?? '—'],
              ].map(([label, value]) => (
                <div key={String(label)} className="flex flex-col gap-1">
                  <dt className="text-xs text-text-muted">{label}</dt>
                  <dd className="text-sm text-text-primary">{value as any}</dd>
                </div>
              ))}
            </dl>
          )}

          {tab === 'payload' && (
            <pre className="bg-surface-2 rounded p-4 text-xs text-text-secondary overflow-x-auto whitespace-pre-wrap break-all">
              {JSON.stringify(job.payload, null, 2)}
            </pre>
          )}

          {tab === 'executions' && (
            <div className="flex flex-col gap-4">
              {executions.length === 0 && (
                <p className="text-sm text-text-muted">No executions recorded yet.</p>
              )}
              {executions.map((ex: any) => <ExecutionCard key={ex.id} execution={ex} />)}
            </div>
          )}
        </div>
      </aside>
    </>
  )
}
