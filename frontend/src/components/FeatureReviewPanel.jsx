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
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    timeZoneName: 'short',
  })
}

function formatFeatureBuilt(value, title) {
  if (!title || !value) return 'No successful feature build yet'
  return `${title} · ${formatLastUpdated(value)}`
}

function DiffViewer({ diffs }) {
  if (!diffs || diffs.length === 0)
    return <div className="text-xs text-gray-400 py-2">No diff preview yet — run a dry run first.</div>
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
                <span key={j} className={
                  line.startsWith('+') && !line.startsWith('+++') ? 'block bg-emerald-50 text-emerald-800 dark:bg-emerald-900/20 dark:text-emerald-300' :
                  line.startsWith('-') && !line.startsWith('---') ? 'block bg-red-50 text-red-800 dark:bg-red-900/20 dark:text-red-300' :
                  'block text-gray-500 dark:text-gray-500'
                }>
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
  useEffect(() => { api.getBacklog(productId).then(setItems).catch(() => {}) }, [productId])
  return (
    <div className="fixed inset-0 bg-black/20 dark:bg-black/50 z-50 flex justify-end">
      <div className="w-96 bg-white dark:bg-gray-900 shadow-2xl flex flex-col">
        <div className="px-5 py-4 border-b border-gray-100 dark:border-gray-800 flex items-center justify-between">
          <span className="font-medium text-gray-900 dark:text-white text-sm">Feature Backlog</span>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200">✕</button>
        </div>
        <div className="flex-1 overflow-auto divide-y divide-gray-50 dark:divide-gray-800">
          {items.length === 0 && (
            <div className="py-12 text-center text-gray-400 text-sm">No backlog items yet.</div>
          )}
          {items.map(item => (
            <div key={item.id} className="px-5 py-4 flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="text-sm font-medium text-gray-900 dark:text-white mb-1">{item.feature_title}</div>
                <div className="text-xs text-gray-500 dark:text-gray-400">{item.customer_problem}</div>
                <div className="flex gap-2 mt-1.5">
                  <span className={`text-xs px-1.5 py-0.5 rounded ${
                    item.risk_level === 'low' ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-400' :
                    item.risk_level === 'medium' ? 'bg-amber-50 text-amber-700' : 'bg-red-50 text-red-700'
                  }`}>{item.risk_level} risk</span>
                  <span className="text-xs text-gray-400">{item.estimated_scope}</span>
                </div>
              </div>
              <button
                onClick={() => { onSelect(item); onClose() }}
                className="shrink-0 text-xs px-2 py-1 bg-gray-900 text-white dark:bg-white dark:text-gray-900 rounded-lg"
              >
                Use this
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function ProductCard({ product, onRefresh }) {
  const nav = useNavigate()
  const [manualFeature, setManualFeature] = useState(product.manual_feature || '')
  const [proposing, setProposing] = useState(false)
  const [proposalStatus, setProposalStatus] = useState('')
  const [savingManual, setSavingManual] = useState(false)
  const [dragActive, setDragActive] = useState(false)
  const [showDiff, setShowDiff] = useState(false)
  const [diffs, setDiffs] = useState([])
  const [showBacklog, setShowBacklog] = useState(false)
  const [generatingBacklog, setGeneratingBacklog] = useState(false)
  const [running, setRunning] = useState(false)
  const [exclusions, setExclusions] = useState(product.per_product_exclusions || '')
  const [selected, setSelected] = useState(product.selected !== false)

  let proposal = null
  try { if (product.proposed_feature_json) proposal = JSON.parse(product.proposed_feature_json) }
  catch {}
  const builtFeatureIsCurrentProposal =
    !!proposal &&
    !!product.last_built_feature_title &&
    proposal.feature_title === product.last_built_feature_title

  const saveManual = async (value = manualFeature) => {
    setSavingManual(true)
    try {
      const result = await api.setManualFeature(product.id, value)
      setManualFeature(result.manual_feature || '')
      setProposalStatus(result.manual_feature ? 'Manual update brief saved.' : 'Manual update brief cleared.')
      onRefresh()
    } finally {
      setSavingManual(false)
    }
  }

  const handleManualFile = async (file) => {
    if (!file) return
    setSavingManual(true)
    try {
      const result = await api.uploadManualFeatureFile(product.id, file)
      setManualFeature(result.manual_feature || '')
      setProposalStatus(`Loaded manual update brief from ${result.source_file}.`)
      onRefresh()
    } finally {
      setSavingManual(false)
      setDragActive(false)
    }
  }

  const propose = async () => {
    setProposing(true)
    try {
      const result = await api.proposeFeature(product.id)
      if (result?.fallback_used) {
        setProposalStatus('AI providers were unavailable. Showing fallback proposal.')
      } else if (manualFeature.trim() && result?.source) {
        setProposalStatus(`Generated via ${result.source} using your manual update brief.`)
      } else if (result?.source) {
        setProposalStatus(`Generated via ${result.source}.`)
      } else {
        setProposalStatus('Proposal refreshed.')
      }
      onRefresh()
    }
    finally { setProposing(false) }
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

  const toggleSelected = async (val) => {
    setSelected(val)
    await api.setSelected(product.id, val)
  }

  const runSingle = async () => {
    setRunning(true)
    try {
      await api.runSingle(product.id)
      onRefresh()
      setTimeout(() => nav('/console'), 600)
    }
    finally { setRunning(false) }
  }

  return (
    <div className={`bg-white dark:bg-gray-900 rounded-2xl border transition-all ${
      selected
        ? 'border-gray-200 dark:border-gray-700'
        : 'border-gray-100 dark:border-gray-800 opacity-50'
    }`}>
      {/* Card header */}
      <div className="px-5 py-4 border-b border-gray-50 dark:border-gray-800 flex items-center gap-3">
        {/* Select checkbox */}
        <input
          type="checkbox"
          checked={selected}
          onChange={e => toggleSelected(e.target.checked)}
          className="rounded border-gray-300 dark:border-gray-600 cursor-pointer"
          title="Include in next run"
        />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-medium text-gray-900 dark:text-white">{product.name}</span>
            <span className="text-xs text-gray-400">{product.detected_stack}</span>
            {product.current_version && (
              <span className="text-xs bg-gray-100 dark:bg-gray-800 text-gray-500 px-1.5 py-0.5 rounded font-mono">
                v{product.current_version}
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {product.health_score > 0 && (
            <span className={`text-xs px-2 py-0.5 rounded-full ${
              product.health_score > 0.7 ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-400' :
              product.health_score > 0.4 ? 'bg-amber-50 text-amber-700 dark:bg-amber-900/20 dark:text-amber-400' :
              'bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-400'
            }`}>
              {Math.round(product.health_score * 100)}% health
            </span>
          )}
          <span className="text-xs text-gray-400">
            {product.last_update_at ? `Updated ${formatLastUpdated(product.last_update_at)}` : 'Not updated yet'}
          </span>
          <span className="text-xs text-gray-400">{product.git_status}</span>
        </div>
      </div>

      <div className="px-5 py-4 space-y-4">
        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-medium text-gray-500 uppercase tracking-wider">Manual Update Brief</span>
            <div className="flex items-center gap-3">
              <label className="text-xs text-blue-600 dark:text-blue-400 hover:underline cursor-pointer">
                Attach file
                <input
                  type="file"
                  accept=".txt,.md,.pdf,.docx"
                  className="hidden"
                  onChange={e => handleManualFile(e.target.files?.[0])}
                />
              </label>
              <button
                onClick={() => saveManual('')}
                disabled={savingManual || !manualFeature}
                className="text-xs text-gray-400 hover:underline disabled:opacity-50"
              >
                Clear
              </button>
            </div>
          </div>
          <div
            onDragOver={e => { e.preventDefault(); setDragActive(true) }}
            onDragLeave={() => setDragActive(false)}
            onDrop={e => {
              e.preventDefault()
              handleManualFile(e.dataTransfer.files?.[0])
            }}
            className={`rounded-xl border transition-colors ${
              dragActive
                ? 'border-blue-400 bg-blue-50/50 dark:bg-blue-900/10'
                : 'border-gray-200 dark:border-gray-700'
            }`}
          >
            <textarea
              value={manualFeature}
              onChange={e => setManualFeature(e.target.value)}
              placeholder='Type a specific feature/update request here, or drop a .md, .txt, .pdf, or .docx file.'
              className="w-full min-h-28 text-sm px-3 py-3 rounded-xl bg-white dark:bg-gray-800 text-gray-900 dark:text-white placeholder-gray-400 focus:outline-none"
            />
          </div>
          <div className="mt-2 flex items-center justify-between gap-3">
            <div className="text-xs text-gray-400">
              Saved brief is always used first when proposing or running updates for this product.
            </div>
            <button
              onClick={() => saveManual()}
              disabled={savingManual}
              className="px-3 py-2 text-xs bg-gray-900 text-white dark:bg-white dark:text-gray-900 rounded-xl hover:opacity-90 disabled:opacity-50"
            >
              {savingManual ? 'Saving...' : 'Save brief'}
            </button>
          </div>
        </div>

        {builtFeatureIsCurrentProposal ? (
          <div className="flex items-start gap-2">
            <span className="text-xs text-gray-400 w-24 pt-0.5">Last built</span>
            <span className="text-xs text-gray-500 dark:text-gray-400">{formatFeatureBuilt(product.last_built_feature_at, product.last_built_feature_title)}</span>
          </div>
        ) : (
          <>
            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-400 w-24">Last update</span>
              <span className="text-xs text-gray-500 dark:text-gray-400">{formatLastUpdated(product.last_update_at)}</span>
            </div>

            <div className="flex items-start gap-2">
              <span className="text-xs text-gray-400 w-24 pt-0.5">Last built</span>
              <span className="text-xs text-gray-500 dark:text-gray-400">{formatFeatureBuilt(product.last_built_feature_at, product.last_built_feature_title)}</span>
            </div>
          </>
        )}

        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-medium text-gray-500 uppercase tracking-wider">
              {builtFeatureIsCurrentProposal ? 'Next Feature Proposal' : 'Proposed Feature'}
            </span>
            <div className="flex gap-3">
              <button onClick={propose} disabled={proposing}
                className="text-xs text-blue-600 dark:text-blue-400 hover:underline disabled:opacity-50">
                {proposing ? 'Proposing...' : builtFeatureIsCurrentProposal ? 'Propose next' : 'Re-propose'}
              </button>
              <button onClick={() => setShowBacklog(true)} className="text-xs text-gray-400 hover:underline">
                Backlog
              </button>
              <button onClick={generateBacklog} disabled={generatingBacklog}
                className="text-xs text-gray-400 hover:underline disabled:opacity-50">
                {generatingBacklog ? 'Generating...' : 'Gen backlog'}
              </button>
            </div>
          </div>
          {proposalStatus && (
            <div className="mb-2 text-xs text-gray-400">{proposalStatus}</div>
          )}
          {builtFeatureIsCurrentProposal ? (
            <div className="rounded-xl bg-emerald-50 dark:bg-emerald-900/10 border border-emerald-100 dark:border-emerald-900/20 p-4 text-xs text-gray-600 dark:text-gray-300">
              This feature is already built. Use `Propose next` to generate the next update idea.
            </div>
          ) : proposal ? (
            <div className="rounded-xl bg-gray-50 dark:bg-gray-800 p-4 space-y-2">
              <div className="font-medium text-sm text-gray-900 dark:text-white">{proposal.feature_title}</div>
              <div className="text-xs text-gray-500 dark:text-gray-400">{proposal.customer_problem}</div>
              <div className="flex flex-wrap gap-1.5 pt-0.5">
                <span className={`text-xs px-1.5 py-0.5 rounded ${
                  proposal.risk_level === 'low' ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-400' :
                  proposal.risk_level === 'medium' ? 'bg-amber-50 text-amber-700' : 'bg-red-50 text-red-700'
                }`}>{proposal.risk_level} risk</span>
                <span className="text-xs text-gray-400">{proposal.estimated_scope}</span>
                {proposal.files_likely_to_change?.length > 0 && (
                  <span className="text-xs text-gray-400">· {proposal.files_likely_to_change.join(', ')}</span>
                )}
              </div>
            </div>
          ) : (
            <div className="rounded-xl bg-gray-50 dark:bg-gray-800 p-4 text-xs text-gray-400">
              No proposal yet. Click "Re-propose" to generate.
            </div>
          )}
        </div>

        {/* Diff preview & per-product exclusions row */}
        <div className="flex items-center gap-4 flex-wrap">
          <button onClick={() => setShowDiff(!showDiff)}
            className="text-xs text-gray-400 hover:text-gray-600 dark:hover:text-gray-300">
            {showDiff ? '▲ Hide diff' : '▼ Diff preview'}
          </button>
          <div className="flex items-center gap-1.5">
            <span className="text-xs text-gray-400">Exclude:</span>
            <input
              value={exclusions}
              onChange={e => setExclusions(e.target.value)}
              onBlur={() => api.setExclusions(product.id, exclusions)}
              placeholder="config.py, settings.js..."
              className="text-xs px-2 py-1 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 placeholder-gray-400 w-40 focus:outline-none"
            />
          </div>
          <button onClick={() => api.setSkipPersistent(product.id, true).then(onRefresh)}
            className="text-xs text-gray-400 hover:text-red-500 dark:hover:text-red-400 ml-auto">
            Skip always
          </button>
        </div>

        {showDiff && <DiffViewer diffs={diffs} />}

        {/* Run this one */}
        <div className="pt-1">
          <button
            onClick={runSingle}
            disabled={running}
            className="px-4 py-1.5 text-xs font-medium bg-gray-900 text-white dark:bg-white dark:text-gray-900 rounded-xl hover:opacity-90 disabled:opacity-50 transition-opacity"
          >
            {running ? 'Running...' : `Run ${product.name} only`}
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
  const [runStarted, setRunStarted] = useState(false)
  const [dryRun, setDryRun] = useState(false)
  const nav = useNavigate()

  const refresh = () => api.products().then(setProducts).catch(() => {})
  useEffect(() => { refresh() }, [])

  const updatable = products.filter(p => p.updatable && !p.skip_persistent)
  const selected = updatable.filter(p => p.selected !== false)

  const selectAll = async (val) => {
    await Promise.all(updatable.map(p => api.setSelected(p.id, val)))
    refresh()
  }

  const runAll = async () => {
    setRunning(true)
    setRunStarted(false)
    try {
      const ids = selected.map(p => p.id)
      await api.startRun(ids.length === updatable.length ? null : ids, dryRun)
      setRunStarted(true)
      setTimeout(() => nav('/console'), 600)
    } catch (e) {
      alert('Failed to start: ' + e.message)
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="p-8">
      {/* Header */}
      <div className="mb-5">
        <h2 className="text-xl font-semibold text-gray-900 dark:text-white">Feature Review</h2>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
          Approve features, review last update times, and run updates
        </p>
      </div>

      {/* Bulk controls + Run bar */}
      {updatable.length > 0 && (
        <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-100 dark:border-gray-800 px-5 py-4 mb-5">
          <div className="flex items-center gap-3 flex-wrap">
            {/* Select all / none */}
            <div className="flex items-center gap-1.5">
              <span className="text-xs text-gray-400 mr-1">Select:</span>
              <button
                onClick={() => selectAll(true)}
                className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
              >
                All
              </button>
              <span className="text-gray-300 dark:text-gray-600">·</span>
              <button
                onClick={() => selectAll(false)}
                className="text-xs text-gray-400 hover:underline"
              >
                None
              </button>
            </div>

            {/* Spacer */}
            <div className="flex-1" />

            {/* Run summary + button */}
            <div className="flex items-center gap-3">
              <div className="text-xs text-gray-500 dark:text-gray-400 text-right">
                {selected.length} of {updatable.length} selected
              </div>
              <label className="flex items-center gap-1.5 text-xs text-gray-500 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={dryRun}
                  onChange={e => setDryRun(e.target.checked)}
                  className="rounded border-gray-300 dark:border-gray-600"
                />
                Dry run
              </label>
              <button
                onClick={runAll}
                disabled={running || runStarted || selected.length === 0}
                className="px-5 py-2 text-sm font-medium bg-gray-900 text-white dark:bg-white dark:text-gray-900 rounded-xl hover:opacity-90 disabled:opacity-50 transition-opacity"
              >
                {runStarted ? 'Started ✓' :
                 running ? 'Starting...' :
                 selected.length === 0 ? 'None selected' :
                 `Update ${selected.length} product${selected.length !== 1 ? 's' : ''}`}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Product cards */}
      {updatable.length === 0 ? (
        <div className="text-center py-20 text-gray-400">
          <div className="text-4xl mb-4">✅</div>
          <div className="text-sm">No updatable products. Scan first from the Dashboard.</div>
        </div>
      ) : (
        <div className="space-y-4">
          {updatable.map(p => (
            <ProductCard key={p.id} product={p} onRefresh={refresh} />
          ))}
        </div>
      )}

      {/* Skipped section */}
      {products.filter(p => !p.updatable || p.skip_persistent).length > 0 && (
        <div className="mt-8">
          <div className="text-xs font-medium text-gray-400 uppercase tracking-wider mb-3">Skipped</div>
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
