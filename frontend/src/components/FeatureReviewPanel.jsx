import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api.js'

function DiffViewer({ diffs }) {
  if (!diffs || diffs.length === 0) return <div className="text-xs text-gray-400 py-2">No diff preview available yet.</div>
  return (
    <div className="space-y-3">
      {diffs.map((d, i) => (
        <div key={i} className="rounded-lg overflow-hidden border border-gray-100 dark:border-gray-700">
          <div className="px-3 py-1.5 bg-gray-50 dark:bg-gray-800 text-xs font-mono text-gray-600 dark:text-gray-400">
            {d.action === 'create' ? '+ create' : '~ modify'} {d.path}
          </div>
          {d.diff && (
            <pre className="text-xs p-3 overflow-auto max-h-48 bg-white dark:bg-gray-900 scrollbar-thin">
              {d.diff.split('\n').map((line, j) => (
                <span
                  key={j}
                  className={
                    line.startsWith('+') && !line.startsWith('+++') ? 'block bg-emerald-50 text-emerald-800 dark:bg-emerald-900/20 dark:text-emerald-300' :
                    line.startsWith('-') && !line.startsWith('---') ? 'block bg-red-50 text-red-800 dark:bg-red-900/20 dark:text-red-300' :
                    'block text-gray-500 dark:text-gray-500'
                  }
                >
                  {line || ' '}
                </span>
              ))}
            </pre>
          )}
        </div>
      ))}
    </div>
  )
}

function BacklogDrawer({ productId, onSelect, onClose }) {
  const [items, setItems] = useState([])
  useEffect(() => {
    api.getBacklog(productId).then(setItems).catch(() => {})
  }, [productId])

  return (
    <div className="fixed inset-0 bg-black/20 dark:bg-black/50 z-50 flex justify-end">
      <div className="w-96 bg-white dark:bg-gray-900 shadow-2xl flex flex-col">
        <div className="px-5 py-4 border-b border-gray-100 dark:border-gray-800 flex items-center justify-between">
          <span className="font-medium text-gray-900 dark:text-white text-sm">Feature Backlog</span>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200">✕</button>
        </div>
        <div className="flex-1 overflow-auto divide-y divide-gray-50 dark:divide-gray-800">
          {items.length === 0 && (
            <div className="py-12 text-center text-gray-400 text-sm">No backlog items. Click "Generate Backlog".</div>
          )}
          {items.map(item => (
            <div key={item.id} className="px-5 py-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-sm font-medium text-gray-900 dark:text-white mb-1">{item.feature_title}</div>
                  <div className="text-xs text-gray-500 dark:text-gray-400">{item.customer_problem}</div>
                  <div className="flex items-center gap-2 mt-2">
                    <span className={`text-xs px-1.5 py-0.5 rounded ${
                      item.risk_level === 'low' ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-400' :
                      item.risk_level === 'medium' ? 'bg-amber-50 text-amber-700 dark:bg-amber-900/20 dark:text-amber-400' :
                      'bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-400'
                    }`}>
                      {item.risk_level} risk
                    </span>
                    <span className="text-xs text-gray-400">{item.estimated_scope}</span>
                  </div>
                </div>
                <button
                  onClick={() => { onSelect(item); onClose() }}
                  className="shrink-0 text-xs px-2 py-1 bg-gray-900 text-white dark:bg-white dark:text-gray-900 rounded-lg hover:opacity-90"
                >
                  Select
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function ProductReviewCard({ product, onRefresh }) {
  const [mode, setMode] = useState(product.mode)
  const [manualFeature, setManualFeature] = useState(product.manual_feature || '')
  const [proposing, setProposing] = useState(false)
  const [showDiff, setShowDiff] = useState(false)
  const [diffs, setDiffs] = useState([])
  const [showBacklog, setShowBacklog] = useState(false)
  const [generatingBacklog, setGeneratingBacklog] = useState(false)
  const [running, setRunning] = useState(false)
  const [exclusions, setExclusions] = useState(product.per_product_exclusions || '')

  let proposal = null
  try {
    if (product.proposed_feature_json) proposal = JSON.parse(product.proposed_feature_json)
  } catch {}

  const saveMode = async (m) => {
    setMode(m)
    await api.setMode(product.id, m)
  }

  const saveManual = async () => {
    await api.setManualFeature(product.id, manualFeature)
  }

  const propose = async () => {
    setProposing(true)
    try {
      await api.proposeFeature(product.id)
      onRefresh()
    } finally { setProposing(false) }
  }

  const generateBacklog = async () => {
    setGeneratingBacklog(true)
    try { await api.proposeBacklog(product.id) }
    finally { setGeneratingBacklog(false) }
  }

  const selectFromBacklog = async (item) => {
    await api.selectFromBacklog(product.id, item.id)
    onRefresh()
  }

  const saveExclusions = async () => {
    await api.setExclusions(product.id, exclusions)
  }

  const runSingle = async () => {
    setRunning(true)
    try { await api.runSingle(product.id) }
    finally { setRunning(false) }
  }

  return (
    <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-100 dark:border-gray-800 overflow-hidden">
      {/* Header */}
      <div className="px-6 py-4 border-b border-gray-50 dark:border-gray-800 flex items-center justify-between">
        <div>
          <span className="font-medium text-gray-900 dark:text-white">{product.name}</span>
          <span className="ml-2 text-xs text-gray-400">{product.detected_stack}</span>
          {product.current_version && (
            <span className="ml-2 text-xs bg-gray-100 dark:bg-gray-800 text-gray-500 px-1.5 py-0.5 rounded">
              v{product.current_version}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {product.health_score > 0 && (
            <span className={`text-xs px-2 py-0.5 rounded-full ${
              product.health_score > 0.7 ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-400' :
              product.health_score > 0.4 ? 'bg-amber-50 text-amber-700 dark:bg-amber-900/20 dark:text-amber-400' :
              'bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-400'
            }`}>
              Health {Math.round(product.health_score * 100)}%
            </span>
          )}
          <span className="text-xs text-gray-400">{product.git_status}</span>
        </div>
      </div>

      <div className="px-6 py-5 space-y-5">
        {/* Mode selector */}
        <div>
          <label className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2 block">Mode</label>
          <div className="flex gap-2">
            {['auto', 'manual'].map(m => (
              <button
                key={m}
                onClick={() => saveMode(m)}
                className={`px-3 py-1.5 text-xs rounded-lg capitalize transition-colors ${
                  mode === m
                    ? 'bg-gray-900 text-white dark:bg-white dark:text-gray-900'
                    : 'border border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800'
                }`}
              >
                {m}
              </button>
            ))}
          </div>
        </div>

        {/* Proposed feature */}
        {mode === 'auto' && (
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-xs font-medium text-gray-500 uppercase tracking-wider">Proposed Feature</label>
              <div className="flex gap-2">
                <button
                  onClick={propose}
                  disabled={proposing}
                  className="text-xs text-blue-600 dark:text-blue-400 hover:underline disabled:opacity-50"
                >
                  {proposing ? 'Proposing...' : 'Repropose'}
                </button>
                <button
                  onClick={() => setShowBacklog(true)}
                  className="text-xs text-gray-500 dark:text-gray-400 hover:underline"
                >
                  View backlog
                </button>
                <button
                  onClick={generateBacklog}
                  disabled={generatingBacklog}
                  className="text-xs text-gray-500 dark:text-gray-400 hover:underline disabled:opacity-50"
                >
                  {generatingBacklog ? 'Generating...' : 'Gen backlog'}
                </button>
              </div>
            </div>
            {proposal ? (
              <div className="rounded-xl bg-gray-50 dark:bg-gray-800 p-4 space-y-2">
                <div className="font-medium text-sm text-gray-900 dark:text-white">{proposal.feature_title}</div>
                <div className="text-xs text-gray-500 dark:text-gray-400">{proposal.customer_problem}</div>
                <div className="flex flex-wrap gap-1.5 pt-1">
                  <span className={`text-xs px-1.5 py-0.5 rounded ${
                    proposal.risk_level === 'low' ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-400' :
                    proposal.risk_level === 'medium' ? 'bg-amber-50 text-amber-700' : 'bg-red-50 text-red-700'
                  }`}>
                    {proposal.risk_level} risk
                  </span>
                  <span className="text-xs text-gray-400">{proposal.estimated_scope}</span>
                </div>
                {proposal.files_likely_to_change?.length > 0 && (
                  <div className="text-xs text-gray-400">
                    Files: {proposal.files_likely_to_change.join(', ')}
                  </div>
                )}
              </div>
            ) : (
              <div className="rounded-xl bg-gray-50 dark:bg-gray-800 p-4 text-xs text-gray-400">
                No proposal yet. Click "Repropose" to generate.
              </div>
            )}
          </div>
        )}

        {/* Manual mode */}
        {mode === 'manual' && (
          <div>
            <label className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2 block">Manual Feature</label>
            <div className="flex gap-2">
              <input
                value={manualFeature}
                onChange={e => setManualFeature(e.target.value)}
                placeholder="Describe the feature to implement..."
                className="flex-1 text-sm px-3 py-2 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white placeholder-gray-400 focus:outline-none focus:border-blue-400"
              />
              <button
                onClick={saveManual}
                className="px-3 py-2 text-xs bg-gray-900 text-white dark:bg-white dark:text-gray-900 rounded-xl hover:opacity-90"
              >
                Save
              </button>
            </div>
          </div>
        )}

        {/* File exclusions */}
        <div>
          <label className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-1.5 block">
            Per-product exclusions
          </label>
          <div className="flex gap-2">
            <input
              value={exclusions}
              onChange={e => setExclusions(e.target.value)}
              placeholder="config.py, settings.js, ..."
              className="flex-1 text-xs px-3 py-1.5 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 placeholder-gray-400 focus:outline-none focus:border-blue-400"
            />
            <button onClick={saveExclusions} className="text-xs text-gray-500 hover:underline">Save</button>
          </div>
        </div>

        {/* Diff preview toggle */}
        <div>
          <button
            onClick={() => setShowDiff(!showDiff)}
            className="text-xs text-gray-500 dark:text-gray-400 hover:underline"
          >
            {showDiff ? 'Hide diff preview' : 'Show diff preview'}
          </button>
          {showDiff && <div className="mt-3"><DiffViewer diffs={diffs} /></div>}
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2 pt-1">
          <button
            onClick={runSingle}
            disabled={running}
            className="px-4 py-2 text-xs font-medium bg-gray-900 text-white dark:bg-white dark:text-gray-900 rounded-xl hover:opacity-90 disabled:opacity-50 transition-opacity"
          >
            {running ? 'Running...' : 'Run this product'}
          </button>
          <button
            onClick={() => api.setSkipPersistent(product.id, true).then(onRefresh)}
            className="px-3 py-2 text-xs border border-gray-200 dark:border-gray-700 text-gray-500 rounded-xl hover:bg-gray-50 dark:hover:bg-gray-800"
          >
            Skip always
          </button>
        </div>
      </div>

      {showBacklog && (
        <BacklogDrawer
          productId={product.id}
          onSelect={selectFromBacklog}
          onClose={() => setShowBacklog(false)}
        />
      )}
    </div>
  )
}

export default function FeatureReviewPanel() {
  const [products, setProducts] = useState([])
  const [running, setRunning] = useState(false)
  const [dryRun, setDryRun] = useState(false)
  const nav = useNavigate()

  const refresh = () => api.products().then(setProducts).catch(() => {})
  useEffect(() => { refresh() }, [])

  const updatable = products.filter(p => p.updatable && !p.skip_persistent && p.selected !== false)

  const runAll = async () => {
    setRunning(true)
    try {
      await api.startRun(null, dryRun)
      nav('/console')
    } finally { setRunning(false) }
  }

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white">Feature Review</h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
            Review and approve features before implementation · {updatable.length} products ready
          </p>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-xs text-gray-600 dark:text-gray-400 cursor-pointer">
            <input
              type="checkbox"
              checked={dryRun}
              onChange={e => setDryRun(e.target.checked)}
              className="rounded"
            />
            Dry run
          </label>
          <button
            onClick={runAll}
            disabled={running || updatable.length === 0}
            className="px-4 py-2 text-sm font-medium bg-gray-900 text-white dark:bg-white dark:text-gray-900 rounded-xl hover:opacity-90 disabled:opacity-50 transition-opacity"
          >
            {running ? 'Starting...' : `Run all ${updatable.length} products`}
          </button>
        </div>
      </div>

      {products.filter(p => p.updatable && !p.skip_persistent).length === 0 && (
        <div className="text-center py-20 text-gray-400">
          <div className="text-4xl mb-4">✅</div>
          <div className="text-sm">No updatable products. Scan first.</div>
        </div>
      )}

      <div className="space-y-4">
        {products.filter(p => p.updatable && !p.skip_persistent).map(p => (
          <ProductReviewCard key={p.id} product={p} onRefresh={refresh} />
        ))}
      </div>

      {products.filter(p => !p.updatable || p.skip_persistent).length > 0 && (
        <div className="mt-8">
          <div className="text-xs font-medium text-gray-400 uppercase tracking-wider mb-3">Skipped Products</div>
          <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-100 dark:border-gray-800 divide-y divide-gray-50 dark:divide-gray-800">
            {products.filter(p => !p.updatable || p.skip_persistent).map(p => (
              <div key={p.id} className="px-5 py-3.5 flex items-center justify-between">
                <div>
                  <span className="text-sm text-gray-700 dark:text-gray-300">{p.name}</span>
                  <span className="ml-2 text-xs text-gray-400">
                    {p.skip_persistent ? 'Always skipped by user' : p.skip_reason}
                  </span>
                </div>
                {p.skip_persistent && (
                  <button
                    onClick={() => api.setSkipPersistent(p.id, false).then(refresh)}
                    className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
                  >
                    Unskip
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
