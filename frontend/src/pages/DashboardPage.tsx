import { useQuery } from '@tanstack/react-query'
import { metricsApi } from '../api'
import SkeletonTable from '../components/SkeletonTable'
import EmptyState from '../components/EmptyState'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend
} from 'recharts'

function MetricCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="panel p-6 flex flex-col gap-1">
      <span className="text-xs text-text-muted">{label}</span>
      <span className="text-2xl font-semibold text-text-primary tabular-nums">{value}</span>
    </div>
  )
}

export default function DashboardPage() {
  const { data: metrics, isLoading, isError } = useQuery({
    queryKey: ['system-metrics'],
    queryFn: metricsApi.system,
    refetchInterval: 5000,
  })

  if (isLoading) return <SkeletonTable cols={4} rows={3} />
  if (isError) return <EmptyState title="Could not load system health" description="Check the API connection and try again." />

  const chartData = metrics?.throughput?.map((point: any) => ({
    name: new Date(point.time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    completed: point.completed,
    failed: point.failed,
  })) ?? []
  const hasThroughput = chartData.some((point: any) => point.completed || point.failed)

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 id="tour-dashboard" className="text-lg font-semibold text-text-primary tracking-tight">Dashboard</h1>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        <MetricCard label="Total Queues" value={metrics?.total_queues ?? 0} />
        <MetricCard label="Active Workers" value={metrics?.active_workers ?? 0} />
        <MetricCard label="Jobs Pending" value={metrics?.jobs_pending ?? 0} />
        <MetricCard label="Jobs Running" value={metrics?.jobs_running ?? 0} />
        <MetricCard label="Completed / hr" value={metrics?.jobs_completed_last_hour ?? 0} />
        <MetricCard label="Failed / hr" value={metrics?.jobs_failed_last_hour ?? 0} />
      </div>

      <div className="panel p-6">
        <h2 className="text-sm font-medium text-text-secondary mb-4">Job Throughput</h2>
        {!hasThroughput && <p className="text-xs text-text-muted mb-2">No executions in the last 12 hours.</p>}
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={chartData} barSize={32}>
            <CartesianGrid strokeDasharray="3 3" stroke="#30363d" />
            <XAxis dataKey="name" tick={{ fill: '#8b949e', fontSize: 12 }} />
            <YAxis allowDecimals={false} domain={[0, 'auto']} tick={{ fill: '#8b949e', fontSize: 12 }} />
            <Tooltip
              contentStyle={{ background: '#161b22', border: '1px solid #30363d', fontSize: 12 }}
              labelStyle={{ color: '#e6edf3' }}
            />
            <Legend />
            <Bar dataKey="completed" fill="#3fb950" radius={[3, 3, 0, 0]} />
            <Bar dataKey="failed" fill="#f85149" radius={[3, 3, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
