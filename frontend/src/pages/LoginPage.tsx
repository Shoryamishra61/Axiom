import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { authApi } from '../api'
import { useAuthStore, useToastStore } from '../store'

export default function LoginPage() {
  const navigate = useNavigate()
  const setAuth = useAuthStore((s) => s.setAuth)
  const toast = useToastStore((s) => s.add)
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [form, setForm] = useState({ email: 'shoryamishra61@gmail.com', password: 'password', name: '' })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      if (mode === 'register') {
        await authApi.register({ email: form.email, password: form.password, name: form.name })
        toast('success', 'Account created — please sign in')
        setMode('login')
      } else {
        const { access_token } = await authApi.login({ email: form.email, password: form.password })
        setAuth(access_token, null)          // set token first so interceptor works
        const user = await authApi.me()
        setAuth(access_token, user)
        navigate('/', { replace: true })
      }
    } catch (err: any) {
      setError(err.response?.data?.error ?? err.response?.data?.detail ?? 'Something went wrong')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-surface flex items-center justify-center p-6">
      <div className="panel w-full max-w-sm p-8">
        <div className="text-center">
          <h1 className="text-2xl font-semibold tracking-tight">Welcome to Axiom</h1>
          <p className="text-sm text-text-secondary mt-1">Sign in to manage your background jobs</p>
        </div>
        <form onSubmit={submit} className="flex flex-col gap-4">
          {mode === 'register' && (
            <label className="flex flex-col gap-1">
              <span className="text-xs text-text-secondary">Name</span>
              <input
                id="name"
                type="text"
                required
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                className="bg-surface-2 border border-border rounded px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-accent"
              />
            </label>
          )}
          <label className="flex flex-col gap-1">
            <span className="text-xs text-text-secondary">Email</span>
            <input
              id="email"
              type="email"
              required
              autoComplete="email"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              className="bg-surface-2 border border-border rounded px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-accent"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-text-secondary">Password</span>
            <input
              id="password"
              type="password"
              required
              minLength={8}
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              className="bg-surface-2 border border-border rounded px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-accent"
            />
          </label>
          {error && (
            <p className="text-xs text-status-failed" role="alert">{error}</p>
          )}
          <button
            type="submit"
            disabled={loading}
            className="btn btn-primary w-full justify-center mt-2"
          >
            {loading ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Create account'}
          </button>
        </form>
        <p className="text-xs text-text-secondary text-center mt-4">
          {mode === 'login' ? "Don't have an account? " : 'Already have an account? '}
          <button
            onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError('') }}
            className="text-accent hover:underline"
          >
            {mode === 'login' ? 'Register' : 'Sign in'}
          </button>
        </p>
      </div>
    </div>
  )
}
