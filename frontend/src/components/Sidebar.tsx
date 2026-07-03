import { NavLink } from 'react-router-dom'

const links = [
  { to: '/', label: 'Dashboard', icon: '▦' },
  { to: '/queues', label: 'Queues', icon: '☰' },
  { to: '/workers', label: 'Workers', icon: '◎' },
]

export default function Sidebar() {
  return (
    <nav
      className="w-56 shrink-0 bg-surface-1 border-r border-border flex flex-col"
      aria-label="Primary navigation"
    >
      <div className="h-14 flex items-center px-4 border-b border-border">
        <span className="text-base font-semibold text-text-primary tracking-tight">Axiom</span>
      </div>
      <ul className="flex flex-col gap-0.5 p-2 flex-1" role="list">
        {links.map(({ to, label, icon }) => (
          <li key={to}>
            <NavLink
              to={to}
              end={to === '/'}
              id={`tour-nav-${label.toLowerCase()}`}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors ${
                  isActive
                    ? 'bg-surface-2 text-text-primary font-medium'
                    : 'text-text-secondary hover:text-text-primary hover:bg-surface-2/50'
                }`
              }
            >
              <span aria-hidden="true">{icon}</span>
              {label}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  )
}
