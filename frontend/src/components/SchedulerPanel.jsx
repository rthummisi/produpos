import { useState, useEffect } from 'react'
import { api } from '../api.js'

export default function SchedulerPanel() {
  const [schedules, setSchedules] = useState([])
  const [creating, setCreating] = useState(false)
  const [form, setForm] = useState({
    name: '', schedule_type: 'interval', schedule_value: '24', mode: 'auto', dry_run: true
  })

  const load = () => api.schedules().then(setSchedules).catch(() => {})
  useEffect(() => { load() }, [])

  const create = async () => {
    setCreating(true)
    try {
      await api.createSchedule(form)
      await load()
      setForm({ name: '', schedule_type: 'interval', schedule_value: '24', mode: 'auto', dry_run: true })
    } finally { setCreating(false) }
  }

  const toggle = async (id) => {
    await api.toggleSchedule(id)
    load()
  }

  const remove = async (id) => {
    if (!confirm('Delete this schedule?')) return
    await api.deleteSchedule(id)
    load()
  }

  return (
    <div className="p-8 max-w-3xl">
      <div className="mb-6">
        <h2 className="text-xl font-semibold text-gray-900 dark:text-white">Scheduler</h2>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
          Automate ProdupOS runs on a schedule
        </p>
      </div>

      {/* Create form */}
      <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-100 dark:border-gray-800 p-6 mb-6">
        <div className="text-sm font-medium text-gray-900 dark:text-white mb-4">New Schedule</div>
        <div className="grid grid-cols-2 gap-4">
          <div className="col-span-2">
            <label className="text-xs text-gray-500 mb-1 block">Name</label>
            <input
              value={form.name}
              onChange={e => setForm({...form, name: e.target.value})}
              placeholder="Weekly auto-update"
              className="w-full text-sm px-3 py-2 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white placeholder-gray-400 focus:outline-none focus:border-blue-400"
            />
          </div>
          <div>
            <label className="text-xs text-gray-500 mb-1 block">Schedule type</label>
            <select
              value={form.schedule_type}
              onChange={e => setForm({...form, schedule_type: e.target.value})}
              className="w-full text-sm px-3 py-2 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none"
            >
              <option value="interval">Interval (hours)</option>
              <option value="daily">Daily (HH:MM)</option>
              <option value="weekly">Weekly</option>
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-500 mb-1 block">
              {form.schedule_type === 'interval' ? 'Every N hours' : form.schedule_type === 'daily' ? 'Time (HH:MM)' : 'Interval'}
            </label>
            <input
              value={form.schedule_value}
              onChange={e => setForm({...form, schedule_value: e.target.value})}
              placeholder={form.schedule_type === 'interval' ? '24' : '09:00'}
              className="w-full text-sm px-3 py-2 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white placeholder-gray-400 focus:outline-none focus:border-blue-400"
            />
          </div>
          <div>
            <label className="text-xs text-gray-500 mb-1 block">Mode</label>
            <select
              value={form.mode}
              onChange={e => setForm({...form, mode: e.target.value})}
              className="w-full text-sm px-3 py-2 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none"
            >
              <option value="auto">Auto</option>
              <option value="manual">Manual</option>
            </select>
          </div>
          <div className="flex items-end">
            <label className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400 cursor-pointer pb-2">
              <input
                type="checkbox"
                checked={form.dry_run}
                onChange={e => setForm({...form, dry_run: e.target.checked})}
                className="rounded"
              />
              Dry run (no writes)
            </label>
          </div>
        </div>
        <button
          onClick={create}
          disabled={creating || !form.name}
          className="mt-4 px-4 py-2 text-sm bg-gray-900 text-white dark:bg-white dark:text-gray-900 rounded-xl hover:opacity-90 disabled:opacity-50 transition-opacity"
        >
          {creating ? 'Creating...' : 'Create schedule'}
        </button>
      </div>

      {/* Schedule list */}
      <div className="space-y-3">
        {schedules.length === 0 && (
          <div className="text-center py-12 text-gray-400 text-sm">No schedules configured.</div>
        )}
        {schedules.map(s => (
          <div key={s.id} className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-100 dark:border-gray-800 px-5 py-4">
            <div className="flex items-center justify-between">
              <div>
                <div className="font-medium text-sm text-gray-900 dark:text-white">{s.name}</div>
                <div className="text-xs text-gray-400 mt-0.5">
                  {s.schedule_type} · {s.schedule_value} ·
                  {s.dry_run ? ' dry run' : ' live run'} ·
                  {s.mode} mode
                </div>
                <div className="text-xs text-gray-400 mt-0.5">
                  Next run: {s.next_run ? new Date(s.next_run).toLocaleString() : '—'}
                  {s.last_run && ` · Last: ${new Date(s.last_run).toLocaleDateString()}`}
                </div>
              </div>
              <div className="flex items-center gap-3">
                <span className={`text-xs px-2 py-0.5 rounded-full ${
                  s.enabled
                    ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-400'
                    : 'bg-gray-100 text-gray-400 dark:bg-gray-800'
                }`}>
                  {s.enabled ? 'Active' : 'Paused'}
                </span>
                <button onClick={() => toggle(s.id)} className="text-xs text-gray-500 hover:underline">
                  {s.enabled ? 'Pause' : 'Resume'}
                </button>
                <button onClick={() => remove(s.id)} className="text-xs text-red-500 hover:underline">
                  Delete
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
