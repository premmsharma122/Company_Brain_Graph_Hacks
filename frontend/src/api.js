import axios from 'axios'

const http = axios.create({ baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000', timeout: 60000 })

export const getHealth = () => http.get('/health').then((r) => r.data)
export const getDemoQuestions = () => http.get('/api/demo-questions').then((r) => r.data)
export const getOverview = () => http.get('/api/graph/overview').then((r) => r.data)
export const getSubgraph = (ids, expand = true) =>
  http.get('/api/subgraph', { params: { ids: ids.join(','), expand } }).then((r) => r.data)
export const getNode = (id) => http.get(`/api/node/${encodeURIComponent(id)}`).then((r) => r.data)
export const getPeople = () => http.get('/api/people').then((r) => r.data)
export const chat = (question) => http.post('/api/chat', { question }).then((r) => r.data)
export const ingest = (payload) => http.post('/api/ingest', payload).then((r) => r.data)

export const errorText = (e) => e?.response?.data?.detail || e?.message || 'Request failed'
