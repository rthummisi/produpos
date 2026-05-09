import { useState, useEffect, useRef } from 'react'
import { api, createWebSocket } from '../api.js'

export default function RunConsole() {
  const [runs, setRuns] = useState([])
  const [activeRunId, setActiveRunId] = useState(null)
  const [logs, setLogs] = useState([])
  const [ws, setWs] = useState(null)
  const [autoScroll, setAutoScroll] = useState(true)
  const logRef = useRef(null)

  useEffect(() => {
    api.runs().then(r => {
      setRuns(r)
      if (r.length > 0 && r[0].status === 'running') {
        selectRun(r[0].id)
      }
    }).catch(() => {})
  }, [])

  useEffect(() => {
    if (autoScroll && logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight
    }
  }, [logs])

  const selectRun = (runId) => {
    if (ws) ws.close()
    setActiveRunId(runId)
    setLogs([])

    api.jobLogs(runId).then(data => {
      setLogs(data.logs || [])
    }).catch(() => {})

    const newWs = createWebSocket(runId, (msg) => {
      setLogs(prev => [...prev, msg])
    })
    setWs(newWs)
  }

  const activeRun = runs.find(r => r.id === activeRunId)

  const statusColor = (s) => ({
    completed: 'text-emerald-600 dark:text-emerald-400',
    running: 'text-blue-600 dark:text-blue-400',
    failed: 'text-red-600 dark:text-red-400',
    pending: 'text-gray-400',
  })[s] || 'text-gray-400'

  const lineColor = (line) => {
    const l = line.toLowerCase()
    if (l.includes('error') || l.includes('failed') || l.includes('fail')) return 'text-red-400 dark:text-red-300'
    if (l.includes('warning') || l.includes('warn')) return 'text-amber-400 dark:text-amber-300'
    if (l.includes('done') || l.includes('complete') || l.includes('updated') || l.includes('committed'))
      return 'text-emerald-400 dark:text-emerald-300'
    if (l.includes('skipped')) return 'text-gray-500'
    return 'text-gray-300 dark:text-gray-400'
  }

  return (
    <div className="p-8 h-screen flex flex-col">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white">Run Console</h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">Real-time agent logs</p>
        </div>
        <label className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400 cursor-pointer">
          <input
            type="checkbox"
            checked={autoScroll}
            onChange={e => setAutoScroll(e.target.checked)}
            className="rounded"
          />
          Auto-scroll
        </label>
      </div>

      <div className="flex gap-6 flex-1 min-h-0">
        {/* Run list */}
        <div className="w-56 shrink-0 space-y-1.5">
          <div className="text-xs font-medium text-gray-400 uppercase tracking-wider mb-3">Runs</div>
          {runs.length === 0 && (
            <div className="text-xs text-gray-400">No runs yet. Start a run from the Review page.</div>
          )}
          {runs.map(r => (
            <button
              key={r.id}
              onClick={() => selectRun(r.id)}
              className={`w-full text-left px-3 py-2.5 rounded-xl transition-colors ${
                activeRunId === r.id
                  ? 'bg-gray-900 text-white dark:bg-white dark:text-gray-900'
                  : 'bg-white dark:bg-gray-900 border border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800'
              }`}
            >
              <div className="text-xs font-medium mb-0.5 truncate">
                {new Date(r.started_at).toLocaleDateString()} {new Date(r.started_at).toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'})}
              </div>
              <div className={`text-xs ${activeRunId === r.id ? 'text-gray-300' : statusColor(r.status)}`}>
                {r.status} · {r.updated_count}/{r.total_products}
              </div>
            </button>
          ))}
        </div>

        {/* Console */}
        <div className="flex-1 flex flex-col min-w-0">
          {activeRun && (
            <div className="mb-3 flex items-center gap-4 text-xs text-gray-500 dark:text-gray-400">
              <span className={statusColor(activeRun.status)}>{activeRun.status}</span>
              <span>Updated: {activeRun.updated_count}</span>
              <span>Skipped: {activeRun.skipped_count}</span>
              <span>Failed: {activeRun.failed_count}</span>
              {activeRun.estimated_cost_usd > 0 && (
                <span>Cost: ${activeRun.estimated_cost_usd.toFixed(4)}</span>
              )}
            </div>
          )}
          <div
            ref={logRef}
            className="flex-1 bg-gray-950 dark:bg-black rounded-2xl p-5 font-mono text-xs overflow-auto scrollbar-thin"
          >
            {logs.length === 0 && (
              <div className="text-gray-600 italic">Waiting for log output...</div>
            )}
            {logs.map((line, i) => (
              <div key={i} className={`leading-relaxed ${lineColor(line)}`}>
                {line}
              </div>
            ))}
            {activeRun?.status === 'running' && (
              <div className="text-blue-400 animate-pulse mt-1">▋</div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
