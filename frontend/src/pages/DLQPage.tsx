import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import { dlqApi } from '../api'
import { useToastStore } from '../store'
import SkeletonTable from '../components/SkeletonTable'
import EmptyState from '../components/EmptyState'

export default function DLQPage() {
  const { queueId } = useParams<{ queueId: string }>()
  const qc = useQueryClient()
  const toast = useToastStore((s) => s.add)

  const { data: entries = [], isLoading } = useQuery({
    queryKey: ['dlq', queueId],
    queryFn: () => dlqApi.list(queueId!),
    enabled: !!queueId,
  })

  const retryMut = useMutation({
    mutationFn: (entryId: string) => dlqApi.retry(queueId!, entryId),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['dlq'] }); toast('success', 'Job re-queued') },
    onError: (e: any) => toast('error', e.response?.data?.error ?? e.response?.data?.detail ?? 'Retry failed'),
  })

  const deleteMut = useMutation({
    mutationFn: (entryId: string) => dlqApi.delete(queueId!, entryId),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['dlq'] }); toast('success', 'Entry deleted') },
    onError: (e: any) => toast('error', e.response?.data?.error ?? e.response?.data?.detail ?? 'Delete failed'),
  })

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-lg font-semibold">Dead Letter Queue</h1>

      {isLoading && <SkeletonTable cols={5} rows={6} />}

      {!isLoading && entries.length === 0 && (
        <EmptyState
          title="No dead jobs"
          description="Jobs that exhaust all retry attempts will appear here."
        />
      )}

      {entries.length > 0 && (
        <div className="panel overflow-hidden">
          <table className="data-table">
            <thead>
              <tr>
                <th>Job ID</th>
                <th>Attempts</th>
                <th>Failure reason</th>
                <th>Dead at</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e: any, i: number) => (
                <tr key={e.id}>
                  <td className="font-mono text-xs text-text-secondary">{e.job_id.slice(0, 8)}…</td>
                  <td className="tabular-nums">{e.attempt_count}</td>
                  <td className="text-status-failed max-w-xs truncate">{e.failure_reason ?? '—'}</td>
                  <td className="text-text-secondary tabular-nums">
                    {new Date(e.dead_at).toLocaleString()}
                  </td>
                  <td className="flex gap-2">
                    <button
                      id={i === 0 ? "tour-dlq-retry" : undefined}
                      className="btn btn-primary text-xs"
                      onClick={() => retryMut.mutate(e.id)}
                      disabled={retryMut.isPending}
                      aria-label={`Retry dead job ${e.job_id.slice(0, 8)}`}
                    >
                      Retry
                    </button>
                    <button
                      className="btn btn-danger text-xs"
                      onClick={() => deleteMut.mutate(e.id)}
                      disabled={deleteMut.isPending}
                      aria-label={`Delete DLQ entry ${e.id.slice(0, 8)}`}
                    >
                      Delete
                    </button>
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
