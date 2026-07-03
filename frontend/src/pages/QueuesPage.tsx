import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { projectApi, queueApi } from '../api'
import { useToastStore } from '../store'
import SkeletonTable from '../components/SkeletonTable'
import EmptyState from '../components/EmptyState'

export default function QueuesPage() {
  const qc = useQueryClient()
  const toast = useToastStore((s) => s.add)
  const [creating, setCreating] = useState(false)
  const [editing, setEditing] = useState<string | null>(null)
  const [form, setForm] = useState({ projectId: '', name: '', priority: 0, concurrency: 10, strategy: 'exponential', attempts: 3, baseDelay: 1000, maxDelay: 60000 })

  const { data: projects = [] } = useQuery({ queryKey: ['projects'], queryFn: projectApi.list })
  
  // Auto-select first project if none is selected and projects are available
  useEffect(() => {
    if (projects.length > 0 && !form.projectId) {
      setForm(f => ({ ...f, projectId: projects[0].id }))
    }
  }, [projects, form.projectId])

  const { data: queues = [], isLoading, isError } = useQuery({
    queryKey: ['queues', form.projectId],
    queryFn: async () => {
      if (!form.projectId) return []
      const list = await queueApi.list(form.projectId)
      return Promise.all(list.map(async (queue: any) => ({ ...queue, metrics: await queueApi.metrics(queue.id) })))
    },
    enabled: !!form.projectId,
    refetchInterval: 5000,
  })

  const createMut = useMutation({
    mutationFn: () => queueApi.create(form.projectId, {
      name: form.name,
      priority: form.priority,
      concurrency_limit: form.concurrency,
      retry_policy: { strategy: form.strategy, max_attempts: form.attempts, base_delay_ms: form.baseDelay, max_delay_ms: form.maxDelay },
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['queues'] })
      toast('success', `Queue "${form.name}" created`)
      setCreating(false)
      setForm((f) => ({ ...f, name: '' }))
    },
    onError: (e: any) => toast('error', e.response?.data?.error ?? e.response?.data?.detail ?? 'Failed to create queue'),
  })

  const updateMut = useMutation({
    mutationFn: () => queueApi.update(form.projectId, editing!, {
      priority: form.priority,
      concurrency_limit: form.concurrency,
      retry_policy: { strategy: form.strategy, max_attempts: form.attempts, base_delay_ms: form.baseDelay, max_delay_ms: form.maxDelay },
    }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['queues'] }); setEditing(null); toast('success', 'Queue configuration updated') },
    onError: (e: any) => toast('error', e.response?.data?.error ?? 'Update failed'),
  })

  const editQueue = (queue: any) => {
    setEditing(queue.id)
    setCreating(false)
    setForm((value) => ({
      ...value,
      priority: queue.priority,
      concurrency: queue.concurrency_limit,
      strategy: queue.retry_policy?.strategy ?? 'exponential',
      attempts: queue.retry_policy?.max_attempts ?? 3,
      baseDelay: queue.retry_policy?.base_delay_ms ?? 1000,
      maxDelay: queue.retry_policy?.max_delay_ms ?? 60000,
    }))
  }

  const togglePause = useMutation({
    mutationFn: ({ projectId, queueId, paused }: any) =>
      paused ? queueApi.resume(projectId, queueId) : queueApi.pause(projectId, queueId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['queues'] }),
    onError: (e: any) => toast('error', e.response?.data?.error ?? e.response?.data?.detail ?? 'Failed'),
  })

  useEffect(() => {
    if (projects.length > 0 && !form.projectId) {
      setForm(f => ({ ...f, projectId: projects[0].id }));
    }
  }, [projects, form.projectId]);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Queues</h1>
        <button id="tour-create-queue" className="btn btn-primary" onClick={() => { setEditing(null); setCreating((v) => !v) }}>
          {creating ? 'Cancel' : '+ New Queue'}
        </button>
      </div>

      {/* Project selector */}
      <div className="flex items-center gap-3">
        <label htmlFor="project-select" id="tour-project-select" className="text-xs text-text-secondary">Project:</label>
        <select
          id="project-select"
          value={form.projectId}
          onChange={(e) => { setEditing(null); setCreating(false); setForm((f) => ({ ...f, projectId: e.target.value })) }}
          className="bg-surface-2 border border-border rounded pl-3 pr-8 py-1.5 text-sm text-text-primary focus:outline-none focus:border-accent cursor-pointer"
          style={{ backgroundImage: 'url("data:image/svg+xml;charset=US-ASCII,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%22292.4%22%20height%3D%22292.4%22%3E%3Cpath%20fill%3D%22%231d1d1f%22%20d%3D%22M287%2069.4a17.6%2017.6%200%200%200-13-5.4H18.4c-5%200-9.3%201.8-12.9%205.4A17.6%2017.6%200%200%200%200%2082.2c0%205%201.8%209.3%205.4%2012.9l128%20127.9c3.6%203.6%207.8%205.4%2012.8%205.4s9.2-1.8%2012.8-5.4L287%2095c3.5-3.5%205.4-7.8%205.4-12.8%200-5-1.9-9.2-5.5-12.8z%22%2F%3E%3C%2Fsvg%3E")', backgroundRepeat: 'no-repeat', backgroundPosition: 'right 0.7rem top 50%', backgroundSize: '0.65rem auto', appearance: 'none' }}
        >
          <option value="">Select a project…</option>
          {projects.map((p: any) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>
      </div>

      {/* Create queue form */}
      {(creating || editing) && form.projectId && (
        <div className="panel p-4 grid grid-cols-1 md:grid-cols-2 gap-3 max-w-2xl">
          <h2 className="text-sm font-medium md:col-span-2">{creating ? 'New Queue' : 'Queue configuration'}</h2>
          {creating && (
          <label className="flex flex-col gap-1">
            <span className="text-xs text-text-secondary">Name</span>
            <input
              type="text" required value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              className="field"
            />
          </label>
          )}
          <label className="flex flex-col gap-1">
            <span className="text-xs text-text-secondary">Priority</span>
            <input type="number" min={0} value={form.priority} onChange={(e) => setForm((f) => ({ ...f, priority: Number(e.target.value) }))} className="field" />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-text-secondary">Concurrency limit</span>
            <input
              type="number" min={1} max={1000} value={form.concurrency}
              onChange={(e) => setForm((f) => ({ ...f, concurrency: Number(e.target.value) }))}
              className="field"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-text-secondary">Retry strategy</span>
            <select value={form.strategy} onChange={(e) => setForm((f) => ({ ...f, strategy: e.target.value }))} className="field">
              {['fixed', 'linear', 'exponential'].map((strategy) => <option key={strategy}>{strategy}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-text-secondary">Max attempts</span>
            <input type="number" min={1} max={100} value={form.attempts} onChange={(e) => setForm((f) => ({ ...f, attempts: Number(e.target.value) }))} className="field" />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-text-secondary">Base delay (ms)</span>
            <input type="number" min={0} value={form.baseDelay} onChange={(e) => setForm((f) => ({ ...f, baseDelay: Number(e.target.value) }))} className="field" />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-text-secondary">Max delay (ms)</span>
            <input type="number" min={form.baseDelay} value={form.maxDelay} onChange={(e) => setForm((f) => ({ ...f, maxDelay: Number(e.target.value) }))} className="field" />
          </label>
          <button
            className="btn btn-primary md:col-span-2"
            onClick={() => creating ? createMut.mutate() : updateMut.mutate()}
            disabled={(creating && !form.name) || createMut.isPending || updateMut.isPending || form.maxDelay < form.baseDelay}
          >
            {createMut.isPending || updateMut.isPending ? 'Saving…' : creating ? 'Create Queue' : 'Save Configuration'}
          </button>
        </div>
      )}

      {!form.projectId && (
        <EmptyState title="Select a project" description="Choose a project above to view its queues." />
      )}

      {form.projectId && isLoading && <SkeletonTable cols={5} rows={6} />}
      {form.projectId && isError && <EmptyState title="Could not load queues" description="Check the API connection and try again." />}

      {form.projectId && !isLoading && queues.length === 0 && (
        <EmptyState
          title="No queues yet"
          description="Create your first queue to start dispatching jobs."
          action={<button className="btn btn-primary" onClick={() => setCreating(true)}>+ New Queue</button>}
        />
      )}

      {queues.length > 0 && (
        <div className="panel overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Priority</th>
                <th>Concurrency</th>
                <th>Status</th>
                <th>Health</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {queues.map((q: any, i: number) => (
                <tr key={q.id}>
                  <td className="font-medium">
                    <Link id={i === 0 ? "tour-queue-link" : undefined} to={`/queues/${q.id}/jobs`} className="text-accent hover:underline">
                      {q.name}
                    </Link>
                  </td>
                  <td className="tabular-nums">{q.priority}</td>
                  <td className="tabular-nums">{q.concurrency_limit}</td>
                  <td>
                    <span className={`pill ${q.is_paused ? 'pill-failed' : 'pill-running'}`}>
                      {q.is_paused ? 'Paused' : 'Active'}
                    </span>
                  </td>
                  <td className="text-xs tabular-nums text-text-secondary">
                    {q.metrics.pending} pending · {q.metrics.running} running · {q.metrics.dead} dead
                  </td>
                  <td className="whitespace-nowrap">
                    <div className="flex items-center gap-2">
                      <button className="btn btn-ghost text-xs border border-border/50" onClick={() => editQueue(q)}>Configure</button>
                      <button
                        id={i === 0 ? "tour-pause-btn" : undefined}
                        className={`btn ${q.is_paused ? 'btn-primary' : 'btn-ghost border border-border/50'} text-xs`}
                        onClick={() => togglePause.mutate({ projectId: form.projectId, queueId: q.id, paused: q.is_paused })}
                        aria-label={q.is_paused ? `Resume queue ${q.name}` : `Pause queue ${q.name}`}
                      >
                        {q.is_paused ? 'Resume' : 'Pause'}
                      </button>
                      <Link
                        to={`/queues/${q.id}/dlq`}
                        className="btn btn-ghost text-xs border border-border/50"
                        aria-label={`View dead letter queue for ${q.name}`}
                      >
                        DLQ
                      </Link>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
