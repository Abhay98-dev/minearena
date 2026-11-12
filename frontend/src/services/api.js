const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1'

export class ApiError extends Error {
  constructor(message, { status, code, details, requestId } = {}) {
    super(message)
    this.status = status
    this.code = code
    this.details = details || {}
    this.requestId = requestId
  }
}

async function request(path, options = {}) {
  let response
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers: { 'Content-Type': 'application/json', ...options.headers },
    })
  } catch {
    throw new ApiError(`Cannot reach MineArena API at ${API_BASE}. Start the backend and try again.`, { code: 'NETWORK' })
  }
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    const e = data?.error || {}
    throw new ApiError(e.message || `Request failed with status ${response.status}.`, {
      status: response.status, code: e.code, details: e.details, requestId: e.request_id,
    })
  }
  return data
}

export function getHealth() {
  return request('/health')
}

export function getEngines() {
  return request('/engines')
}

export function processDocument(payload) {
  return request('/gateway/process', { method: 'POST', body: JSON.stringify(payload) })
}

export function processWordDocument(file, { task, provider }) {
  const query = new URLSearchParams({ filename: file.name, task, provider })
  return request(`/gateway/process-file?${query}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' },
    body: file,
  })
}

export async function getAudit(limit = 50) {
  const data = await request(`/audit?limit=${limit}`)
  return data.records || []
}

export function getMetrics() {
  return request('/metrics')
}

export function getEvaluation() {
  return request('/evaluation')
}
