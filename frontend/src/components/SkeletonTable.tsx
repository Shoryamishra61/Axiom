// Skeleton loader for tables — matches data structure, no full-page spinner
export default function SkeletonTable({ cols = 5, rows = 8 }: { cols?: number; rows?: number }) {
  return (
    <div className="panel overflow-hidden" role="status" aria-label="Loading data">
      <table className="data-table">
        <thead>
          <tr>
            {Array.from({ length: cols }).map((_, i) => (
              <th key={i}>
                <div className="h-3 w-20 bg-surface-2 rounded animate-pulse" />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: rows }).map((_, r) => (
            <tr key={r}>
              {Array.from({ length: cols }).map((_, c) => (
                <td key={c}>
                  <div className="h-3 bg-surface-2 rounded animate-pulse" style={{ width: `${60 + Math.random() * 40}%` }} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
