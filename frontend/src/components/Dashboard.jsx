import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api.js'

function formatLastUpdated(value) {
  if (!value) return 'Not updated yet'
  const normalized = /z$/i.test(value) ? value : `${value}Z`
  const date = new Date(normalized)
  if (Number.isNaN(date.getTime())) return 'Not updated yet'
  return date.toLocaleString([], {
    timeZone: 'America/Los_Angeles',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    timeZoneName: 'short',
  })
}

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

function GuardianPanel({ guardian, onRerun }) {
  const [running, setRunning] = useState(false)
  if (!guardian) return null

  const rerun = async () => {
    setRunning(true)
    try { await api.runGuardian() } finally { setRunning(false) }
  }

  const hasNews = guardian.new_products > 0 || guardian.versions_synced > 0 ||
                  guardian.tags_created > 0 || guardian.changelogs_created > 0

  return (
    <div className={`rounded-2xl border px-5 py-4 mb-6 ${
      guardian.errors > 0
        ? 'bg-red-50 border-red-100 dark:bg-red-900/10 dark:border-red-900/30'
        : hasNews
          ? 'bg-blue-50 border-blue-100 dark:bg-blue-900/10 dark:border-blue-900/20'
          : 'bg-emerald-50 border-emerald-100 dark:bg-emerald-900/10 dark:border-emerald-900/20'
    }`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-base">{guardian.errors > 0 ? '⚠️' : hasNews ? '🔄' : '✅'}</span>
          <div>
            <div className="text-sm font-medium text-gray-900 dark:text-white">
              Guardian {guardian.ready ? 'scan complete' : 'scanning...'}
            </div>
            <div className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 flex flex-wrap gap-3">
              {guardian.new_products > 0 && (
                <span className="text-blue-700 dark:text-blue-400 font-medium">
                  {guardian.new_products} new product{guardian.new_products !== 1 ? 's' : ''} detected
                </span>
              )}
              {guardian.versions_synced > 0 && (
                <span>{guardian.versions_synced} version{guardian.versions_synced !== 1 ? 's' : ''} synced</span>
              )}
              {guardian.tags_created > 0 && (
                <span>{guardian.tags_created} tag{guardian.tags_created !== 1 ? 's' : ''} created</span>
              )}
              {guardian.changelogs_created > 0 && (
                <span>{guardian.changelogs_created} CHANGELOG{guardian.changelogs_created !== 1 ? 's' : ''} created</span>
              )}
              {guardian.errors > 0 && (
                <span className="text-red-600 dark:text-red-400">{guardian.errors} error{guardian.errors !== 1 ? 's' : ''}</span>
              )}
              {!hasNews && guardian.errors === 0 && guardian.ready && (
                <span>All products clean ✓</span>
              )}
            </div>
          </div>
        </div>
        <button
          onClick={rerun}
          disabled={running}
          className="text-xs text-gray-500 dark:text-gray-400 hover:underline disabled:opacity-50"
        >
          {running ? 'Running...' : 'Re-run'}
        </button>
      </div>
    </div>
  )
}

export default function Dashboard() {
  const [health, setHealth] = useState(null)
  const [products, setProducts] = useState([])
  const [scanning, setScanning] = useState(false)
  const [updating, setUpdating] = useState(false)
  const [dryRun, setDryRun] = useState(false)
  const [runs, setRuns] = useState([])
  const [runStarted, setRunStarted] = useState(false)
  const [guardian, setGuardian] = useState(null)
  const nav = useNavigate()

  const load = () => {
    api.health().then(h => {
      setHealth(h)
      if (h.guardian) setGuardian(h.guardian)
    }).catch(() => {})
    api.products().then(setProducts).catch(() => {})
    api.runs().then(setRuns).catch(() => {})
  }

  useEffect(() => {
    load()
    // Poll guardian until it's ready
    const poll = setInterval(() => {
      api.health().then(h => {
        if (h.guardian?.ready) {
          setGuardian(h.guardian)
          clearInterval(poll)
          // refresh products after guardian scan
          api.products().then(setProducts).catch(() => {})
        }
      }).catch(() => {})
    }, 3000)
    return () => clearInterval(poll)
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

  const handleUpdateAll = async () => {
    setUpdating(true)
    setRunStarted(false)
    try {
      await api.startRun(null, dryRun)
      setRunStarted(true)
      setTimeout(() => nav('/console'), 600)
    } catch (e) {
      alert('Failed to start run: ' + e.message)
    } finally {
      setUpdating(false)
    }
  }

  const updatable = products.filter(p => p.updatable && !p.skip_persistent)
  const skipped = products.filter(p => !p.updatable || p.skip_persistent)
  const lastRun = runs[0]

  return (
    <div className="p-8 max-w-6xl mx-auto">
      {/* Header */}
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
            className="px-4 py-2 text-sm font-medium border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 rounded-xl hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-50 transition-colors"
          >
            {scanning ? 'Scanning...' : 'Scan Projects'}
          </button>
        </div>
      </div>

      {/* Guardian status */}
      <GuardianPanel guardian={guardian} onRerun={load} />

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
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

      {/* Update All action bar */}
      {updatable.length > 0 && (
        <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-100 dark:border-gray-800 px-6 py-5 mb-6">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-sm font-medium text-gray-900 dark:text-white mb-1">
                Update All Products
              </div>
              <div className="text-xs text-gray-500 dark:text-gray-400">
                <span className="text-gray-400">Each product uses its saved proposal and shows its last successful update time</span>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <label className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={dryRun}
                  onChange={e => setDryRun(e.target.checked)}
                  className="rounded border-gray-300 dark:border-gray-600"
                />
                Dry run
              </label>
              <button
                onClick={() => nav('/review')}
                className="px-4 py-2 text-sm border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 rounded-xl hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
              >
                Review first
              </button>
              <button
                onClick={handleUpdateAll}
                disabled={updating || runStarted}
                className="px-5 py-2 text-sm font-medium bg-gray-900 text-white dark:bg-white dark:text-gray-900 rounded-xl hover:opacity-90 disabled:opacity-50 transition-opacity"
              >
                {runStarted ? 'Started ✓' : updating ? 'Starting...' : `Update all ${updatable.length}`}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Products list */}
      {products.length > 0 && (
        <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-100 dark:border-gray-800">
          <div className="px-6 py-4 border-b border-gray-100 dark:border-gray-800 flex items-center justify-between">
            <span className="text-sm font-medium text-gray-900 dark:text-white">Products Detected</span>
            <button onClick={() => nav('/scan')} className="text-xs text-blue-600 dark:text-blue-400 hover:underline">
              View all →
            </button>
          </div>
          {/* Table header */}
          <div className="px-6 py-2 grid grid-cols-12 gap-2 border-b border-gray-50 dark:border-gray-800">
            <span className="col-span-4 text-xs font-medium text-gray-400 uppercase tracking-wider">Product</span>
            <span className="col-span-3 text-xs font-medium text-gray-400 uppercase tracking-wider">Stack</span>
            <span className="col-span-2 text-xs font-medium text-gray-400 uppercase tracking-wider">Version</span>
            <span className="col-span-1 text-xs font-medium text-gray-400 uppercase tracking-wider">Last Updated</span>
            <span className="col-span-2 text-xs font-medium text-gray-400 uppercase tracking-wider">Status</span>
          </div>
          <div className="divide-y divide-gray-50 dark:divide-gray-800">
            {products.map(p => (
              <div key={p.id} className="px-6 py-3 grid grid-cols-12 gap-2 items-center hover:bg-gray-50/50 dark:hover:bg-gray-800/20 transition-colors">
                <span className="col-span-4 text-sm font-medium text-gray-900 dark:text-white truncate">{p.name}</span>
                <span className="col-span-3 text-xs text-gray-400 truncate">{p.detected_stack || '—'}</span>
                <span className="col-span-2 text-xs font-mono font-medium text-gray-700 dark:text-gray-300">
                  {p.current_version ? `v${p.current_version}` : <span className="text-gray-300 dark:text-gray-600">—</span>}
                </span>
                <span className="col-span-1 text-xs text-gray-400">{formatLastUpdated(p.last_update_at)}</span>
                <span className="col-span-2">
                  <span className={`text-xs px-2 py-0.5 rounded-full ${
                    p.updatable && !p.skip_persistent
                      ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400'
                      : 'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-500'
                  }`}>
                    {p.skip_persistent ? 'Skipped' : p.updatable ? 'Ready' : 'Skip'}
                  </span>
                </span>
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
