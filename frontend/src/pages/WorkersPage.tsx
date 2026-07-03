import { useQuery } from '@tanstack/react-query'
import { metricsApi } from '../api'
import StatusPill from '../components/StatusPill'
import SkeletonTable from '../components/SkeletonTable'
import EmptyState from '../components/EmptyState'

export default function WorkersPage() {
  const { data: workers = [], isLoading, isError } = useQuery({
    queryKey: ['workers'],
    queryFn: metricsApi.workers,
    refetchInterval: 5000,
  })

  return (
    <div className="flex flex-col gap-6">
      <h1 id="tour-workers-section" className="text-lg font-semibold">Worker Fleet</h1>

      {isLoading && <SkeletonTable cols={5} rows={4} />}
      {isError && <EmptyState title="Could not load workers" description="Check the API connection and try again." />}

      {!isLoading && workers.length === 0 && (
        <div id="tour-workers-empty">
          <EmptyState title="No workers registered" description="Start a worker process to see it here." />
        </div>
      )}

      {workers.length > 0 && (
        <div className="panel overflow-hidden">
          <table id="tour-workers-table" className="data-table">
            <thead>
              <tr>
                <th>Worker ID</th>
                <th>Hostname</th>
                <th>PID</th>
                <th>Status</th>
                <th>Active jobs</th>
                <th>Last seen</th>
                <th>Started</th>
              </tr>
            </thead>
            <tbody>
              {workers.map((w: any) => (
                <tr key={w.id}>
                  <td className="font-mono text-xs text-text-secondary">{w.id.slice(0, 8)}…</td>
                  <td>{w.hostname}</td>
                  <td className="tabular-nums">{w.pid}</td>
                  <td><StatusPill status={w.status} /></td>
                  <td className="tabular-nums">{w.active_jobs}</td>
                  <td className="text-text-secondary tabular-nums">
                    {new Date(w.last_seen).toLocaleString()}
                  </td>
                  <td className="text-text-secondary tabular-nums">
                    {new Date(w.started_at).toLocaleString()}
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
