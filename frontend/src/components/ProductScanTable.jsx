import { useState, useEffect } from 'react'
import { api } from '../api.js'

const BADGE = {
  updatable: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-400',
  skip: 'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-500',
  dirty: 'bg-amber-50 text-amber-700 dark:bg-amber-900/20 dark:text-amber-400',
}

const E2E_BADGE = {
  passed: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-400',
  failed: 'bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-400',
  no_tests: 'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400',
  error: 'bg-amber-50 text-amber-700 dark:bg-amber-900/20 dark:text-amber-400',
}

export default function ProductScanTable() {
  const [products, setProducts] = useState([])
  const [scanning, setScanning] = useState(false)
  const [analyzing, setAnalyzing] = useState({})
  const [e2eTesting, setE2ETesting] = useState({})
  const [filter, setFilter] = useState('all')

  useEffect(() => { api.products().then(setProducts).catch(() => {}) }, [])

  const scan = async () => {
    setScanning(true)
    try { setProducts(await api.scan()) }
    finally { setScanning(false) }
  }

  const analyze = async (id) => {
    setAnalyzing(a => ({ ...a, [id]: true }))
    try {
      await api.analyzeProduct(id)
      setProducts(await api.products())
    } finally {
      setAnalyzing(a => ({ ...a, [id]: false }))
    }
  }

  const setSkip = async (id, skip) => {
    await api.setSkipPersistent(id, skip)
    setProducts(await api.products())
  }

  const runE2E = async (id) => {
    setE2ETesting(t => ({ ...t, [id]: 'running' }))
    try {
      await api.runE2ETest(id)
      // Poll until complete
      for (let i = 0; i < 90; i++) {
        await new Promise(r => setTimeout(r, 2000))
        const results = await api.getE2EResults(id)
        const latest = results?.[0]
        if (latest && latest.status !== 'running' && latest.status !== 'pending') {
          setE2ETesting(t => ({ ...t, [id]: latest.status }))
          setProducts(await api.products())
          return
        }
      }
      setE2ETesting(t => ({ ...t, [id]: 'error' }))
    } catch {
      setE2ETesting(t => ({ ...t, [id]: 'error' }))
    }
  }

  const filtered = products.filter(p => {
    if (filter === 'updatable') return p.updatable && !p.skip_persistent
    if (filter === 'skipped') return !p.updatable || p.skip_persistent
    return true
  })

  const updatable = products.filter(p => p.updatable && !p.skip_persistent).length
  const skipped = products.length - updatable

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white">Product Scan</h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
            {updatable} updatable · {skipped} skipped
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden text-xs">
            {['all', 'updatable', 'skipped'].map(f => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`px-3 py-1.5 capitalize transition-colors ${
                  filter === f
                    ? 'bg-gray-900 text-white dark:bg-white dark:text-gray-900'
                    : 'text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800'
                }`}
              >
                {f}
              </button>
            ))}
          </div>
          <button
            onClick={scan}
            disabled={scanning}
            className="px-4 py-2 text-sm bg-gray-900 text-white dark:bg-white dark:text-gray-900 rounded-xl hover:opacity-90 disabled:opacity-50 transition-opacity"
          >
            {scanning ? 'Scanning...' : 'Re-scan'}
          </button>
        </div>
      </div>

      <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-100 dark:border-gray-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100 dark:border-gray-800">
              {['Product', 'Stack', 'Git', 'Confidence', 'Health', 'Status', 'E2E', 'Actions'].map(h => (
                <th key={h} className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50 dark:divide-gray-800">
            {filtered.map(p => (
              <tr key={p.id} className="hover:bg-gray-50/50 dark:hover:bg-gray-800/30 transition-colors">
                <td className="px-4 py-3.5">
                  <div className="font-medium text-gray-900 dark:text-white">{p.name}</div>
                  <div className="text-xs text-gray-400 truncate max-w-40" title={p.path}>{p.path}</div>
                </td>
                <td className="px-4 py-3.5 text-gray-600 dark:text-gray-400">{p.detected_stack || '—'}</td>
                <td className="px-4 py-3.5">
                  <span className={`text-xs px-2 py-0.5 rounded-full ${
                    p.git_status === 'clean' ? BADGE.updatable :
                    p.git_status === 'dirty' ? BADGE.dirty : BADGE.skip
                  }`}>
                    {p.git_status || 'none'}
                  </span>
                </td>
                <td className="px-4 py-3.5">
                  <div className="flex items-center gap-2">
                    <div className="w-16 h-1.5 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-blue-500 rounded-full"
                        style={{ width: `${Math.round(p.code_confidence_score * 100)}%` }}
                      />
                    </div>
                    <span className="text-xs text-gray-400">{Math.round(p.code_confidence_score * 100)}%</span>
                  </div>
                </td>
                <td className="px-4 py-3.5">
                  {p.health_score > 0 ? (
                    <div className="flex items-center gap-1.5">
                      <div className="w-12 h-1.5 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full ${
                            p.health_score > 0.7 ? 'bg-emerald-500' :
                            p.health_score > 0.4 ? 'bg-amber-500' : 'bg-red-500'
                          }`}
                          style={{ width: `${Math.round(p.health_score * 100)}%` }}
                        />
                      </div>
                      <span className="text-xs text-gray-400">{Math.round(p.health_score * 100)}%</span>
                    </div>
                  ) : (
                    <span className="text-xs text-gray-300 dark:text-gray-600">—</span>
                  )}
                </td>
                <td className="px-4 py-3.5">
                  {p.skip_persistent ? (
                    <span className="text-xs px-2 py-0.5 rounded-full bg-purple-50 text-purple-700 dark:bg-purple-900/20 dark:text-purple-400">
                      Skipped always
                    </span>
                  ) : p.updatable ? (
                    <span className={`text-xs px-2 py-0.5 rounded-full ${BADGE.updatable}`}>Updatable</span>
                  ) : (
                    <span className={`text-xs px-2 py-0.5 rounded-full ${BADGE.skip}`} title={p.skip_reason}>
                      {p.skip_reason?.slice(0, 24) || 'Skipped'}
                    </span>
                  )}
                </td>
                <td className="px-4 py-3.5">
                  {(() => {
                    const state = e2eTesting[p.id] || p.last_e2e_status
                    if (!state) return <span className="text-xs text-gray-300 dark:text-gray-600">—</span>
                    const label = state === 'running' ? 'Testing...' :
                      state === 'passed' ? 'E2E ✓' :
                      state === 'failed' ? 'E2E ✗' :
                      state === 'no_tests' ? 'No tests' : state
                    return (
                      <span className={`text-xs px-2 py-0.5 rounded-full ${E2E_BADGE[state] || E2E_BADGE.error}`}>
                        {label}
                      </span>
                    )
                  })()}
                </td>
                <td className="px-4 py-3.5">
                  <div className="flex items-center gap-2 flex-wrap">
                    {p.updatable && (
                      <button
                        onClick={() => analyze(p.id)}
                        disabled={analyzing[p.id]}
                        className="text-xs text-blue-600 dark:text-blue-400 hover:underline disabled:opacity-50"
                      >
                        {analyzing[p.id] ? 'Analyzing...' : 'Analyze'}
                      </button>
                    )}
                    <button
                      onClick={() => runE2E(p.id)}
                      disabled={e2eTesting[p.id] === 'running'}
                      className="text-xs text-blue-600 dark:text-blue-400 hover:underline disabled:opacity-50"
                    >
                      {e2eTesting[p.id] === 'running' ? 'Testing...' : 'E2E Testing'}
                    </button>
                    <button
                      onClick={() => setSkip(p.id, !p.skip_persistent)}
                      className="text-xs text-gray-400 hover:text-red-500 dark:hover:text-red-400"
                    >
                      {p.skip_persistent ? 'Unskip' : 'Skip always'}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {filtered.length === 0 && (
          <div className="py-16 text-center text-gray-400">
            <div className="text-3xl mb-3">🔍</div>
            <div>No products found. Click Re-scan to discover projects.</div>
          </div>
        )}
      </div>
    </div>
  )
}
