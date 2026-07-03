import { lazy, Suspense } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { useAuthStore } from './store'
import Layout from './components/Layout'
import Toast from './components/Toast'
import TourGuide from './components/TourGuide'

const LoginPage = lazy(() => import('./pages/LoginPage'))
const DashboardPage = lazy(() => import('./pages/DashboardPage'))
const QueuesPage = lazy(() => import('./pages/QueuesPage'))
const JobExplorerPage = lazy(() => import('./pages/JobExplorerPage'))
const DLQPage = lazy(() => import('./pages/DLQPage'))
const WorkersPage = lazy(() => import('./pages/WorkersPage'))

function RequireAuth({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token)
  return token ? <>{children}</> : <Navigate to="/login" replace />
}

export default function App() {
  return (
    <BrowserRouter>
      <Toast />
      <TourGuide />
      <Suspense fallback={<div className="min-h-screen bg-surface" role="status" aria-label="Loading page" />}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route element={<RequireAuth><Layout /></RequireAuth>}>
            <Route index element={<DashboardPage />} />
            <Route path="queues" element={<QueuesPage />} />
            <Route path="queues/:queueId/jobs" element={<JobExplorerPage />} />
            <Route path="queues/:queueId/dlq" element={<DLQPage />} />
            <Route path="workers" element={<WorkersPage />} />
          </Route>
        </Routes>
      </Suspense>
    </BrowserRouter>
  )
}
