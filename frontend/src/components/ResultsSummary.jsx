import { useState, useEffect } from 'react'
import { api } from '../api.js'

function StatusBadge({ status }) {
  const map = {
    updated: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-400',
    failed: 'bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-400',
    skipped: 'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-500',
    dry_run_complete: 'bg-blue-50 text-blue-700 dark:bg-blue-900/20 dark:text-blue-400',
    timed_out: 'bg-amber-50 text-amber-700 dark:bg-amber-900/20 dark:text-amber-400',
  }
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full ${map[status] || 'bg-gray-100 text-gray-500'}`}>
      {status?.replace('_', ' ')}
    </span>
  )
}

function RollbackButton({ item }) {
  const [snaps, setSnaps] = useState([])
  const [rolling, setRolling] = useState(false)
  const [done, setDone] = useState(false)

  const load = async () => {
    const data = await api.getSnapshots(item.product_id)
    setSnaps(data)
  }

  const rollback = async (snapId) => {
    setRolling(true)
    try {
      await api.rollback(item.product_id, snapId)
      setDone(true)
    } finally { setRolling(false) }
  }

  if (done) return <span className="text-xs text-emerald-600">Rolled back</span>

  const matchingSnap = snaps.find(s => s.run_item_id === item.id)

  return (
    <div>
      {snaps.length === 0 ? (
        <button onClick={load} className="text-xs text-gray-400 hover:text-red-500 dark:hover:text-red-400">
          Rollback
        </button>
      ) : matchingSnap ? (
        <button
          onClick={() => rollback(matchingSnap.id)}
          disabled={rolling || matchingSnap.restored}
          className="text-xs text-red-600 dark:text-red-400 hover:underline disabled:opacity-50"
        >
          {rolling ? 'Rolling back...' : matchingSnap.restored ? 'Already restored' : 'Confirm rollback'}
        </button>
      ) : (
        <span className="text-xs text-gray-300 dark:text-gray-600">No snapshot</span>
      )}
    </div>
  )
}

export default function ResultsSummary() {
  const [runs, setRuns] = useState([])
  const [selectedRun, setSelectedRun] = useState(null)
  const [report, setReport] = useState(null)
  const [reports, setReports] = useState([])

  useEffect(() => {
    api.runs().then(setRuns).catch(() => {})
    api.reports().then(setReports).catch(() => {})
  }, [])

  const loadRun = async (run) => {
    setSelectedRun(run)
    const full = await api.run(run.id)
    setReport(full)
  }

  const latestRun = report

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white">Results</h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">Run history and per-product outcomes</p>
        </div>
        {reports.length > 0 && (
          <div className="flex gap-2">
            <a
              href={api.exportReport(reports[0]?.name, 'csv')}
              download
              className="text-xs px-3 py-1.5 border border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-400 rounded-xl hover:bg-gray-50 dark:hover:bg-gray-800"
            >
              Export CSV
            </a>
            <a
              href={api.exportReport(reports[0]?.name, 'md')}
              download
              className="text-xs px-3 py-1.5 border border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-400 rounded-xl hover:bg-gray-50 dark:hover:bg-gray-800"
            >
              Export MD
            </a>
          </div>
        )}
      </div>

      <div className="flex gap-6">
        {/* Run list */}
        <div className="w-52 shrink-0 space-y-1.5">
          <div className="text-xs font-medium text-gray-400 uppercase tracking-wider mb-3">Runs</div>
          {runs.map(r => (
            <button
              key={r.id}
              onClick={() => loadRun(r)}
              className={`w-full text-left px-3 py-2.5 rounded-xl transition-colors ${
                selectedRun?.id === r.id
                  ? 'bg-gray-900 text-white dark:bg-white dark:text-gray-900'
                  : 'bg-white dark:bg-gray-900 border border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800'
              }`}
            >
              <div className="text-xs font-medium mb-0.5">
                {new Date(r.started_at).toLocaleDateString()}
              </div>
              <div className={`text-xs ${selectedRun?.id === r.id ? 'text-gray-300' : 'text-gray-400'}`}>
                {r.updated_count} updated · {r.failed_count} failed
              </div>
            </button>
          ))}
          {runs.length === 0 && <div className="text-xs text-gray-400">No runs yet.</div>}
        </div>

        {/* Results table */}
        <div className="flex-1 min-w-0">
          {latestRun ? (
            <>
              {/* Summary cards */}
              <div className="grid grid-cols-4 gap-3 mb-5">
                {[
                  { label: 'Total', value: latestRun.total_products },
                  { label: 'Updated', value: latestRun.updated_count, color: 'text-emerald-600 dark:text-emerald-400' },
                  { label: 'Skipped', value: latestRun.skipped_count },
                  { label: 'Failed', value: latestRun.failed_count, color: 'text-red-600 dark:text-red-400' },
                ].map(({ label, value, color }) => (
                  <div key={label} className="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-4">
                    <div className="text-xs text-gray-400 mb-1">{label}</div>
                    <div className={`text-2xl font-semibold ${color || 'text-gray-900 dark:text-white'}`}>{value}</div>
                  </div>
                ))}
              </div>

              {latestRun.estimated_cost_usd > 0 && (
                <div className="mb-4 text-xs text-gray-500 dark:text-gray-400">
                  Tokens used: {latestRun.total_tokens_used?.toLocaleString()} ·
                  Estimated cost: ${latestRun.estimated_cost_usd?.toFixed(4)}
                </div>
              )}

              {/* Product update table */}
              <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-100 dark:border-gray-800 overflow-hidden">
                <div className="px-5 py-3.5 border-b border-gray-50 dark:border-gray-800">
                  <span className="text-sm font-medium text-gray-900 dark:text-white">Product Update Table</span>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b border-gray-50 dark:border-gray-800">
                        {['Product', 'Status', 'Mode', 'Feature Implemented', 'Version Before', 'Version After', 'Git Branch', 'Commit', 'Actions'].map(h => (
                          <th key={h} className="px-4 py-3 text-left font-medium text-gray-400 uppercase tracking-wider whitespace-nowrap">
                            {h}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-50 dark:divide-gray-800">
                      {latestRun.items?.map(item => (
                        <tr key={item.id} className="hover:bg-gray-50/50 dark:hover:bg-gray-800/30 transition-colors">
                          <td className="px-4 py-3 font-medium text-gray-900 dark:text-white whitespace-nowrap">
                            {item.product_id}
                          </td>
                          <td className="px-4 py-3"><StatusBadge status={item.status} /></td>
                          <td className="px-4 py-3 text-gray-500 dark:text-gray-400 capitalize">—</td>
                          <td className="px-4 py-3 text-gray-700 dark:text-gray-300 max-w-xs truncate" title={item.feature_title}>
                            {item.feature_title || '—'}
                          </td>
                          <td className="px-4 py-3 text-gray-400 font-mono">
                            {item.version_before ? `v${item.version_before}` : '—'}
                          </td>
                          <td className="px-4 py-3 font-mono">
                            {item.version_after ? (
                              <span className="text-emerald-600 dark:text-emerald-400 font-medium">v{item.version_after}</span>
                            ) : '—'}
                          </td>
                          <td className="px-4 py-3 font-mono text-gray-400 max-w-32 truncate" title={item.git_branch}>
                            {item.git_branch || '—'}
                          </td>
                          <td className="px-4 py-3 font-mono text-gray-400">
                            {item.git_commit ? (
                              <span title={item.git_commit}>{item.git_commit.slice(0, 7)}</span>
                            ) : '—'}
                          </td>
                          <td className="px-4 py-3">
                            {item.status === 'updated' && <RollbackButton item={item} />}
                            {item.github_pr_url && (
                              <a href={item.github_pr_url} target="_blank" rel="noreferrer"
                                className="text-xs text-blue-600 dark:text-blue-400 hover:underline ml-2">
                                PR
                              </a>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          ) : (
            <div className="text-center py-24 text-gray-400">
              <div className="text-4xl mb-4">📊</div>
              <div className="text-sm">Select a run to see results</div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
