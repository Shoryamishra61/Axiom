import axios from 'axios'
import { useAuthStore } from './store'

const api = axios.create({ baseURL: '/api/v1' })

api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) useAuthStore.getState().logout()
    return Promise.reject(err)
  }
)

export default api

// ---- Typed API helpers ----

export const authApi = {
  register: (data: { email: string; name: string; password: string }) =>
    api.post('/auth/register', data).then((r) => r.data),
  login: (data: { email: string; password: string }) =>
    api.post('/auth/login', data).then((r) => r.data),
  me: () => api.get('/auth/me').then((r) => r.data),
}

export const orgApi = {
  list: () => api.get('/orgs').then((r) => r.data),
  create: (data: { name: string }) => api.post('/orgs', data).then((r) => r.data),
}

export const projectApi = {
  list: () => api.get('/projects').then((r) => r.data),
  create: (data: { name: string; org_id: string }) => api.post('/projects', data).then((r) => r.data),
}

export const queueApi = {
  list: (projectId: string) => api.get(`/projects/${projectId}/queues`).then((r) => r.data),
  create: (projectId: string, data: object) =>
    api.post(`/projects/${projectId}/queues`, data).then((r) => r.data),
  update: (projectId: string, queueId: string, data: object) =>
    api.patch(`/projects/${projectId}/queues/${queueId}`, data).then((r) => r.data),
  pause: (projectId: string, queueId: string) =>
    api.post(`/projects/${projectId}/queues/${queueId}/pause`).then((r) => r.data),
  resume: (projectId: string, queueId: string) =>
    api.post(`/projects/${projectId}/queues/${queueId}/resume`).then((r) => r.data),
  metrics: (queueId: string) => api.get(`/queues/${queueId}/metrics`).then((r) => r.data),
}

export const jobApi = {
  list: (queueId: string, params?: object) =>
    api.get(`/queues/${queueId}/jobs`, { params }).then((r) => r.data),
  get: (jobId: string) => api.get(`/jobs/${jobId}`).then((r) => r.data),
  executions: (jobId: string) => api.get(`/jobs/${jobId}/executions`).then((r) => r.data),
  logs: (execId: string) => api.get(`/executions/${execId}/logs`).then((r) => r.data),
  scheduled: (queueId: string) => api.get(`/queues/${queueId}/scheduled-jobs`).then((r) => r.data),
  create: (queueId: string, data: object, idempotencyKey?: string) =>
    api.post(`/queues/${queueId}/jobs`, data, {
      headers: idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : {},
    }).then((r) => r.data),
  cancel: (jobId: string) => api.delete(`/jobs/${jobId}`).then((r) => r.data),
}

export const dlqApi = {
  list: (queueId: string) => api.get(`/queues/${queueId}/dlq`).then((r) => r.data),
  retry: (queueId: string, entryId: string) =>
    api.post(`/queues/${queueId}/dlq/${entryId}/retry`).then((r) => r.data),
  delete: (queueId: string, entryId: string) =>
    api.delete(`/queues/${queueId}/dlq/${entryId}`).then((r) => r.data),
}

export const metricsApi = {
  system: () => api.get('/metrics').then((r) => r.data),
  workers: () => api.get('/workers').then((r) => r.data),
}
