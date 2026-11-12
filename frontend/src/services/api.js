const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1'

async function request(path, options = {}) {
  let response
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers: { 'Content-Type': 'application/json', ...options.headers },
    })
  } catch {
    throw new Error(`Cannot reach MineArena API at ${API_BASE}. Start the backend and try again.`)
  }
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = data?.error
    throw new Error(detail?.message || `Request failed with status ${response.status}.`)
  }
  return data
}

export function getHealth() {
  return request('/health')
}

export function processDocument(payload) {
  return request('/gateway/process', { method: 'POST', body: JSON.stringify(payload) })
}

export async function getAudit(limit = 50) {
  const data = await request(`/audit?limit=${limit}`)
  return data.records || []
}
