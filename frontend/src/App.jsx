import { useState, useEffect } from 'react'
import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import Dashboard from './components/Dashboard.jsx'
import ProductScanTable from './components/ProductScanTable.jsx'
import FeatureReviewPanel from './components/FeatureReviewPanel.jsx'
import RunConsole from './components/RunConsole.jsx'
import ResultsSummary from './components/ResultsSummary.jsx'
import SettingsPanel from './components/SettingsPanel.jsx'
import SchedulerPanel from './components/SchedulerPanel.jsx'

const NAV = [
  { to: '/', label: 'Dashboard', icon: '⚡' },
  { to: '/scan', label: 'Products', icon: '🔍' },
  { to: '/review', label: 'Review', icon: '✅' },
  { to: '/console', label: 'Console', icon: '🖥' },
  { to: '/results', label: 'Results', icon: '📊' },
  { to: '/schedule', label: 'Schedule', icon: '🕐' },
  { to: '/settings', label: 'Settings', icon: '⚙️' },
]

export default function App() {
  const [dark, setDark] = useState(() => localStorage.getItem('theme') === 'dark')

  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
    localStorage.setItem('theme', dark ? 'dark' : 'light')
  }, [dark])

  return (
    <div className={dark ? 'dark' : ''}>
      <BrowserRouter>
        <div className="min-h-screen bg-gray-50 dark:bg-gray-950 flex">
          {/* Sidebar */}
          <aside className="w-56 shrink-0 bg-white dark:bg-gray-900 border-r border-gray-100 dark:border-gray-800 flex flex-col">
            <div className="px-6 py-6 border-b border-gray-100 dark:border-gray-800">
              <div className="text-lg font-semibold tracking-tight text-gray-900 dark:text-white">ProdupOS</div>
              <div className="text-xs text-gray-400 mt-0.5">v2.1.0 · AI Product OS</div>
            </div>
            <nav className="flex-1 py-4 px-3 space-y-0.5">
              {NAV.map(({ to, label, icon }) => (
                <NavLink
                  key={to}
                  to={to}
                  end={to === '/'}
                  className={({ isActive }) =>
                    `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-all ${
                      isActive
                        ? 'bg-gray-900 text-white dark:bg-white dark:text-gray-900 font-medium'
                        : 'text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800'
                    }`
                  }
                >
                  <span className="text-base">{icon}</span>
                  {label}
                </NavLink>
              ))}
            </nav>
            <div className="px-4 pb-4">
              <button
                onClick={() => setDark(!dark)}
                className="w-full text-left px-3 py-2 text-xs text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800 rounded-lg transition-colors"
              >
                {dark ? '☀️ Light mode' : '🌙 Dark mode'}
              </button>
            </div>
          </aside>

          {/* Main */}
          <main className="flex-1 overflow-auto">
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/scan" element={<ProductScanTable />} />
              <Route path="/review" element={<FeatureReviewPanel />} />
              <Route path="/console" element={<RunConsole />} />
              <Route path="/results" element={<ResultsSummary />} />
              <Route path="/schedule" element={<SchedulerPanel />} />
              <Route path="/settings" element={<SettingsPanel />} />
            </Routes>
          </main>
        </div>
      </BrowserRouter>
    </div>
  )
}
