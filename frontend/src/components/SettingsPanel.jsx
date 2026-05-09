import { useState, useEffect } from 'react'
import { api } from '../api.js'

function SettingRow({ label, description, settingKey, value, type = 'text', onSave }) {
  const [local, setLocal] = useState(String(value ?? ''))
  const [saved, setSaved] = useState(false)

  const save = async () => {
    await onSave(settingKey, local)
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  if (type === 'boolean') {
    return (
      <div className="flex items-center justify-between py-4 border-b border-gray-50 dark:border-gray-800">
        <div>
          <div className="text-sm font-medium text-gray-900 dark:text-white">{label}</div>
          <div className="text-xs text-gray-400 mt-0.5">{description}</div>
        </div>
        <button
          onClick={() => { const next = local === 'true' ? 'false' : 'true'; setLocal(next); onSave(settingKey, next) }}
          className={`relative w-10 h-5 rounded-full transition-colors ${
            local === 'true' ? 'bg-gray-900 dark:bg-white' : 'bg-gray-200 dark:bg-gray-700'
          }`}
        >
          <span className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white dark:bg-gray-900 transition-transform ${
            local === 'true' ? 'translate-x-5' : ''
          }`} />
        </button>
      </div>
    )
  }

  return (
    <div className="flex items-center justify-between gap-6 py-4 border-b border-gray-50 dark:border-gray-800">
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium text-gray-900 dark:text-white">{label}</div>
        <div className="text-xs text-gray-400 mt-0.5">{description}</div>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <input
          value={local}
          onChange={e => setLocal(e.target.value)}
          className="text-sm px-3 py-1.5 w-48 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:border-blue-400"
        />
        <button
          onClick={save}
          className="text-xs px-3 py-1.5 bg-gray-900 text-white dark:bg-white dark:text-gray-900 rounded-xl hover:opacity-90"
        >
          {saved ? '✓' : 'Save'}
        </button>
      </div>
    </div>
  )
}

export default function SettingsPanel() {
  const [settings, setSettings] = useState({})
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.settings().then(s => { setSettings(s); setLoading(false) }).catch(() => setLoading(false))
  }, [])

  const save = async (key, value) => {
    await api.updateSetting(key, value)
    setSettings(prev => ({ ...prev, [key]: value }))
  }

  if (loading) return <div className="p-8 text-gray-400 text-sm">Loading settings...</div>

  const SETTINGS = [
    {
      section: 'Scanning',
      items: [
        { key: 'projects_root', label: 'Projects root path', desc: 'Primary directory to scan for products', type: 'text' },
        { key: 'additional_roots', label: 'Additional scan roots', desc: 'Comma-separated extra paths to scan', type: 'text' },
      ],
    },
    {
      section: 'AI',
      items: [
        { key: 'ai_model', label: 'AI model', desc: 'Claude model to use for feature proposals and implementation', type: 'text' },
        { key: 'ai_enabled', label: 'AI enabled', desc: 'Set ANTHROPIC_API_KEY in environment to enable', type: 'boolean' },
      ],
    },
    {
      section: 'Agents',
      items: [
        { key: 'max_concurrent_agents', label: 'Max concurrent agents', desc: 'How many products to update simultaneously', type: 'text' },
        { key: 'agent_timeout_seconds', label: 'Agent timeout (seconds)', desc: 'Kill agent if it runs longer than this', type: 'text' },
        { key: 'require_approval_before_write', label: 'Require approval before write', desc: 'Block dirty repos unless user overrides', type: 'boolean' },
      ],
    },
    {
      section: 'Git',
      items: [
        { key: 'allow_git_commits', label: 'Allow git commits', desc: 'Let ProdupOS commit changes to git', type: 'boolean' },
        { key: 'allow_git_branch_creation', label: 'Allow branch creation', desc: 'Create a new branch per update', type: 'boolean' },
        { key: 'allow_non_git_updates', label: 'Allow non-git updates', desc: 'Update products that are not git repos', type: 'boolean' },
        { key: 'allow_auto_create_git_repo', label: 'Auto-create git repos', desc: 'Run git init on non-repo products (disabled by default)', type: 'boolean' },
        { key: 'allow_github_pr', label: 'Create GitHub PRs', desc: 'Push branch and open PR (requires GITHUB_TOKEN)', type: 'boolean' },
      ],
    },
    {
      section: 'Safety',
      items: [
        { key: 'dry_run', label: 'Dry run mode', desc: 'Plan and show diffs but never write files', type: 'boolean' },
      ],
    },
  ]

  return (
    <div className="p-8 max-w-3xl">
      <div className="mb-6">
        <h2 className="text-xl font-semibold text-gray-900 dark:text-white">Settings</h2>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">Configure ProdupOS behavior</p>
      </div>

      <div className="space-y-8">
        {SETTINGS.map(({ section, items }) => (
          <div key={section} className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-100 dark:border-gray-800 overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-50 dark:border-gray-800">
              <span className="text-xs font-medium text-gray-400 uppercase tracking-wider">{section}</span>
            </div>
            <div className="px-6">
              {items.map(({ key, label, desc, type }) => (
                <SettingRow
                  key={key}
                  settingKey={key}
                  label={label}
                  description={desc}
                  value={settings[key]}
                  type={type}
                  onSave={save}
                />
              ))}
            </div>
          </div>
        ))}

        {/* Never-touch info */}
        <div className="bg-amber-50 dark:bg-amber-900/10 rounded-2xl border border-amber-100 dark:border-amber-900/20 p-5">
          <div className="text-sm font-medium text-amber-800 dark:text-amber-400 mb-2">Safety — Never touched</div>
          <div className="text-xs text-amber-700 dark:text-amber-500 font-mono">
            .env · .env.local · .env.production · node_modules · .git · venv · __pycache__ · dist · build · *.pem · *.key · secrets.json
          </div>
        </div>
      </div>
    </div>
  )
}
