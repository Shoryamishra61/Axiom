import { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { jobApi } from '../api'
import { useToastStore } from '../store'
import StatusPill from '../components/StatusPill'
import SkeletonTable from '../components/SkeletonTable'
import EmptyState from '../components/EmptyState'
import JobDetailDrawer from '../components/JobDetailDrawer'

const STATUSES = ['', 'queued', 'scheduled', 'claimed', 'running', 'completed', 'failed', 'dead', 'cancelled']

export default function JobExplorerPage() {
  const { queueId } = useParams<{ queueId: string }>()
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(1)
  const [selectedJob, setSelectedJob] = useState<any>(null)
  const [creating, setCreating] = useState(false)
  const [form, setForm] = useState({ type: 'immediate', payload: '{}', runAt: '', cron: '', priority: 0 })
  const qc = useQueryClient()
  const toast = useToastStore((s) => s.add)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['jobs', queueId, status, page],
    queryFn: () => jobApi.list(queueId!, { ...(status ? { status } : {}), page, page_size: 25 }),
    enabled: !!queueId,
    refetchInterval: 5000,
  })
  const jobs = data?.items ?? []

  const createMut = useMutation({
    mutationFn: () => {
      const payload = JSON.parse(form.payload)
      const body: any = { job_type: form.type, payload, priority: form.priority }
      if (form.type === 'delayed' || form.type === 'scheduled') body.run_at = new Date(form.runAt).toISOString()
      if (form.type === 'cron') body.cron_expr = form.cron
      if (form.type === 'batch') {
        if (!Array.isArray(payload)) throw new Error('Batch payload must be a JSON array of job payloads')
        body.payload = {}
        body.batch_jobs = payload.map((item) => ({ job_type: 'immediate', payload: item, priority: form.priority }))
      }
      return jobApi.create(queueId!, body, crypto.randomUUID())
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['jobs', queueId] })
      toast('success', 'Job submitted')
      setCreating(false)
      setForm({ type: 'immediate', payload: '{}', runAt: '', cron: '', priority: 0 })
    },
    onError: (e: any) => toast('error', e.response?.data?.error ?? e.message ?? 'Job submission failed'),
  })

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Job Explorer</h1>
        <div className="flex items-center gap-3">
          <button id="tour-submit-success" className="btn btn-ghost border border-border" onClick={() => {
            const body = { job_type: 'immediate', payload: { duration_ms: 2000, message: "Simulated success task" }, priority: 1 }
            jobApi.create(queueId!, body, crypto.randomUUID()).then(() => {
              qc.invalidateQueries({ queryKey: ['jobs', queueId] })
              toast('success', 'Success job submitted')
            })
          }}>
            Submit Success Job
          </button>
          <button id="tour-submit-failing" className="btn btn-ghost border border-border" onClick={() => {
            const body = { job_type: 'immediate', payload: { fail: true, error: "Simulated task failure for testing retries" }, priority: 1 }
            jobApi.create(queueId!, body, crypto.randomUUID()).then(() => {
              qc.invalidateQueries({ queryKey: ['jobs', queueId] })
              toast('success', 'Failing job submitted')
            })
          }}>
            Submit Failing Job
          </button>
          <Link id="tour-dlq-btn" to={`/queues/${queueId}/dlq`} className="btn btn-ghost border border-border">
            View DLQ
          </Link>
          <button className="btn btn-primary" onClick={() => setCreating((value) => !value)}>
            {creating ? 'Cancel' : '+ Submit Job'}
          </button>
          <label htmlFor="status-filter" className="text-xs text-text-secondary">Status:</label>
          <select
            id="status-filter"
            value={status}
            onChange={(e) => { setStatus(e.target.value); setPage(1) }}
            className="bg-surface-2 border border-border rounded px-3 py-1.5 text-sm text-text-primary focus:outline-none focus:border-accent"
          >
            {STATUSES.map((s) => <option key={s} value={s}>{s || 'All'}</option>)}
          </select>
        </div>
      </div>

      {creating && (
        <div className="panel p-4 grid grid-cols-1 md:grid-cols-2 gap-3">
          <label className="flex flex-col gap-1">
            <span className="text-xs text-text-secondary">Type</span>
            <select value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })} className="field">
              {['immediate', 'delayed', 'scheduled', 'cron', 'batch'].map((type) => <option key={type}>{type}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-text-secondary">Priority</span>
            <input type="number" min="0" value={form.priority} onChange={(e) => setForm({ ...form, priority: Number(e.target.value) })} className="field" />
          </label>
          {(form.type === 'delayed' || form.type === 'scheduled') && (
            <label className="flex flex-col gap-1 md:col-span-2">
              <span className="text-xs text-text-secondary">Run at</span>
              <input type="datetime-local" required value={form.runAt} onChange={(e) => setForm({ ...form, runAt: e.target.value })} className="field" />
            </label>
          )}
          {form.type === 'cron' && (
            <label className="flex flex-col gap-1 md:col-span-2">
              <span className="text-xs text-text-secondary">Cron expression</span>
              <input placeholder="0 * * * *" required value={form.cron} onChange={(e) => setForm({ ...form, cron: e.target.value })} className="field" />
            </label>
          )}
          <label className="flex flex-col gap-1 md:col-span-2">
            <span className="text-xs text-text-secondary">{form.type === 'batch' ? 'Payloads (JSON array)' : 'Payload (JSON object)'}</span>
            <textarea rows={5} value={form.payload} onChange={(e) => setForm({ ...form, payload: e.target.value })} className="field font-mono" />
          </label>
          <button className="btn btn-primary md:col-span-2" disabled={createMut.isPending || ((form.type === 'delayed' || form.type === 'scheduled') && !form.runAt) || (form.type === 'cron' && !form.cron)} onClick={() => createMut.mutate()}>
            {createMut.isPending ? 'Submitting…' : 'Submit Job'}
          </button>
        </div>
      )}

      {isLoading && <SkeletonTable cols={6} rows={10} />}

      {isError && <EmptyState title="Could not load jobs" description="Check the API connection and try again." />}

      {!isLoading && jobs.length === 0 && (
        <EmptyState
          title={status ? `No ${status} jobs` : 'No jobs in this queue'}
          description={status ? 'Try another status or clear the filter.' : 'Submit the first job to start processing.'}
          action={status
            ? <button className="btn btn-ghost" onClick={() => { setStatus(''); setPage(1) }}>Clear filter</button>
            : <button className="btn btn-primary" onClick={() => setCreating(true)}>+ Submit Job</button>}
        />
      )}

      {jobs.length > 0 && (
        <div className="panel overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Type</th>
                <th>Status</th>
                <th>Priority</th>
                <th>Attempts</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((j: any, i: number) => (
                <tr
                  key={j.id}
                  id={i === 0 ? "tour-job-row" : undefined}
                  className="group cursor-pointer hover:bg-surface-2/50 transition-colors"
                  onClick={() => setSelectedJob(j)}
                  tabIndex={0}
                  onKeyDown={(e) => e.key === 'Enter' && setSelectedJob(j)}
                  aria-label={`View details for job ${j.id}`}
                >
                  <td className="font-mono text-xs text-text-secondary">{j.id.slice(0, 8)}…</td>
                  <td className="capitalize">{j.job_type}</td>
                  <td><StatusPill status={j.status} /></td>
                  <td className="tabular-nums">{j.priority}</td>
                  <td className="tabular-nums">{j.attempt_count} / {j.max_attempts}</td>
                  <td className="text-text-secondary tabular-nums">
                    {new Date(j.created_at).toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {data?.total > data?.page_size && (
        <div className="flex items-center justify-end gap-3">
          <button className="btn btn-ghost" disabled={page === 1} onClick={() => setPage((value) => value - 1)}>Previous</button>
          <span className="text-xs text-text-secondary">Page {page} of {Math.ceil(data.total / data.page_size)}</span>
          <button className="btn btn-ghost" disabled={page * data.page_size >= data.total} onClick={() => setPage((value) => value + 1)}>Next</button>
        </div>
      )}

      {selectedJob && (
        <JobDetailDrawer job={selectedJob} onClose={() => setSelectedJob(null)} />
      )}
    </div>
  )
}
