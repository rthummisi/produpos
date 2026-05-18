const BASE = 'http://localhost:8091'

async function req(method, path, body) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
  }
  if (body !== undefined) opts.body = JSON.stringify(body)
  const res = await fetch(BASE + path, opts)
  if (!res.ok) {
    const err = await res.text()
    throw new Error(err || res.statusText)
  }
  const ct = res.headers.get('content-type') || ''
  if (ct.includes('application/json')) return res.json()
  return res.text()
}

export const api = {
  health: () => req('GET', '/health'),
  scan: () => req('POST', '/api/scan'),
  products: () => req('GET', '/api/products'),
  product: (id) => req('GET', `/api/products/${id}`),
  analyzeProduct: (id) => req('POST', `/api/products/${id}/analyze`),
  proposeFeature: (id) => req('POST', `/api/products/${id}/propose`),
  proposeBacklog: (id) => req('POST', `/api/products/${id}/propose-backlog`),
  setMode: (id, mode) => req('POST', `/api/products/${id}/mode`, { mode }),
  bulkSetMode: (product_ids, mode) => req('POST', '/api/bulk/products/mode', { product_ids, mode }),
  setSelected: (id, selected) => req('POST', `/api/products/${id}/selected`, { selected }),
  setManualFeature: (id, feature) => req('POST', `/api/products/${id}/manual-feature`, { feature }),
  uploadManualFeatureFile: async (id, file) => {
    const form = new FormData()
    form.append('file', file)
    const res = await fetch(`${BASE}/api/products/${id}/manual-feature-file`, {
      method: 'POST',
      body: form,
    })
    if (!res.ok) {
      const err = await res.text()
      throw new Error(err || res.statusText)
    }
    return res.json()
  },
  setExclusions: (id, patterns) => req('POST', `/api/products/${id}/exclude-files`, { patterns }),
  setSkipPersistent: (id, skip) => req('POST', `/api/products/${id}/skip-persistent`, { skip }),
  getBacklog: (id) => req('GET', `/api/products/${id}/backlog`),
  selectFromBacklog: (pid, bid) => req('POST', `/api/products/${pid}/backlog/${bid}/select`),
  getSnapshots: (id) => req('GET', `/api/products/${id}/snapshots`),
  rollback: (id, snapshot_id) => req('POST', `/api/products/${id}/rollback`, { snapshot_id }),
  getDiff: (pid, runItemId) => req('GET', `/api/products/${pid}/diff?run_item_id=${runItemId}`),

  runE2ETest: (id) => req('POST', `/api/products/${id}/e2e-test`),
  runAndE2E: (id, dry_run = false) => req('POST', `/api/products/${id}/run-and-e2e?dry_run=${dry_run}`),
  getE2EResults: (id) => req('GET', `/api/products/${id}/e2e-results`),

  startRun: (product_ids, dry_run) => req('POST', '/api/run', { product_ids, dry_run }),
  runSingle: (id, dry_run = false) => req('POST', `/api/run/${id}?dry_run=${dry_run}`),
  runs: () => req('GET', '/api/runs'),
  run: (id) => req('GET', `/api/runs/${id}`),
  jobLogs: (id) => req('GET', `/api/jobs/${id}/logs`),

  reports: () => req('GET', '/api/reports'),
  report: (name) => req('GET', `/api/reports/${name}`),
  exportReport: (name, format) => `${BASE}/api/reports/${name}/export?format=${format}`,

  schedules: () => req('GET', '/api/schedules'),
  createSchedule: (data) => req('POST', '/api/schedules', data),
  deleteSchedule: (id) => req('DELETE', `/api/schedules/${id}`),
  toggleSchedule: (id) => req('PATCH', `/api/schedules/${id}/toggle`),

  settings: () => req('GET', '/api/settings'),
  updateSetting: (key, value) => req('POST', '/api/settings', { key, value }),

  guardian: () => req('GET', '/api/guardian'),
  runGuardian: () => req('POST', '/api/guardian/run'),
}

export function createWebSocket(jobId, onMessage) {
  const ws = new WebSocket(`ws://localhost:8091/ws/logs/${jobId}`)
  ws.onmessage = (e) => {
    if (e.data !== 'ping') onMessage(e.data)
  }
  return ws
}
