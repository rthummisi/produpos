import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api.js'

function Stat({ label, value, sub, color = 'gray' }) {
  const colors = {
    gray: 'text-gray-900 dark:text-white',
    green: 'text-emerald-600 dark:text-emerald-400',
    red: 'text-red-600 dark:text-red-400',
    blue: 'text-blue-600 dark:text-blue-400',
    amber: 'text-amber-600 dark:text-amber-400',
  }
  return (
    <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-100 dark:border-gray-800 p-6">
      <div className="text-xs font-medium text-gray-400 uppercase tracking-widest mb-2">{label}</div>
      <div className={`text-3xl font-semibold ${colors[color]}`}>{value}</div>
      {sub && <div className="text-xs text-gray-400 mt-1">{sub}</div>}
    </div>
  )
}

export default function Dashboard() {
  const [health, setHealth] = useState(null)
  const [products, setProducts] = useState([])
  const [scanning, setScanning] = useState(false)
  const [runs, setRuns] = useState([])
  const nav = useNavigate()

  useEffect(() => {
    api.health().then(setHealth).catch(() => {})
    api.products().then(setProducts).catch(() => {})
    api.runs().then(setRuns).catch(() => {})
  }, [])

  const handleScan = async () => {
    setScanning(true)
    try {
      const result = await api.scan()
      setProducts(result)
    } finally {
      setScanning(false)
    }
  }

  const updatable = products.filter(p => p.updatable && !p.skip_persistent)
  const skipped = products.filter(p => !p.updatable || p.skip_persistent)
  const lastRun = runs[0]

  return (
    <div className="p-8 max-w-6xl mx-auto">
      <div className="mb-8 flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900 dark:text-white">ProdupOS</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Local-first AI product update operating system
          </p>
        </div>
        <div className="flex items-center gap-3">
          {health && (
            <span className={`flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full ${
              health.ai_enabled
                ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400'
                : 'bg-amber-50 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400'
            }`}>
              <span className="w-1.5 h-1.5 rounded-full bg-current" />
              {health.ai_enabled ? 'AI active' : 'Fallback mode'}
            </span>
          )}
          <button
            onClick={handleScan}
            disabled={scanning}
            className="px-4 py-2 text-sm font-medium bg-gray-900 text-white dark:bg-white dark:text-gray-900 rounded-xl hover:opacity-90 disabled:opacity-50 transition-opacity"
          >
            {scanning ? 'Scanning...' : 'Scan Projects'}
          </button>
          <button
            onClick={() => nav('/review')}
            className="px-4 py-2 text-sm font-medium border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 rounded-xl hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
          >
            Review & Run
          </button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <Stat label="Total Products" value={products.length} />
        <Stat label="Updatable" value={updatable.length} color="green" />
        <Stat label="Skipped" value={skipped.length} color="amber" />
        <Stat
          label="Last Run"
          value={lastRun ? (lastRun.status === 'completed' ? `${lastRun.updated_count} updated` : lastRun.status) : '—'}
          sub={lastRun ? new Date(lastRun.started_at).toLocaleDateString() : 'No runs yet'}
          color={lastRun?.updated_count > 0 ? 'green' : 'gray'}
        />
      </div>

      {/* Products preview */}
      {products.length > 0 && (
        <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-100 dark:border-gray-800">
          <div className="px-6 py-4 border-b border-gray-100 dark:border-gray-800 flex items-center justify-between">
            <span className="text-sm font-medium text-gray-900 dark:text-white">Products Detected</span>
            <button onClick={() => nav('/scan')} className="text-xs text-blue-600 dark:text-blue-400 hover:underline">
              View all →
            </button>
          </div>
          <div className="divide-y divide-gray-50 dark:divide-gray-800">
            {products.slice(0, 6).map(p => (
              <div key={p.id} className="px-6 py-3.5 flex items-center justify-between">
                <div>
                  <span className="text-sm font-medium text-gray-900 dark:text-white">{p.name}</span>
                  <span className="ml-2 text-xs text-gray-400">{p.detected_stack || 'Unknown stack'}</span>
                </div>
                <div className="flex items-center gap-3">
                  {p.current_version && (
                    <span className="text-xs text-gray-400">v{p.current_version}</span>
                  )}
                  <span className={`text-xs px-2 py-0.5 rounded-full ${
                    p.updatable && !p.skip_persistent
                      ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400'
                      : 'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-500'
                  }`}>
                    {p.skip_persistent ? 'Skipped (persistent)' : p.updatable ? 'Updatable' : p.skip_reason || 'Skip'}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {products.length === 0 && (
        <div className="text-center py-20 text-gray-400">
          <div className="text-5xl mb-4">⚡</div>
          <div className="text-lg font-medium text-gray-600 dark:text-gray-300 mb-2">Ready to scan</div>
          <div className="text-sm">Click "Scan Projects" to discover products in your projects folder</div>
        </div>
      )}
    </div>
  )
}
