import { useState, useEffect, useCallback } from 'react'
import Dashboard    from './components/Dashboard.jsx'
import Transactions from './components/Transactions.jsx'
import Subscriptions from './components/Subscriptions.jsx'
import Budgets      from './components/Budgets.jsx'
import Settings     from './components/Settings.jsx'

const TABS = [
  { id: 'dashboard',     label: '📊 Dashboard' },
  { id: 'transactions',  label: '💳 Transactions' },
  { id: 'subscriptions', label: '🔄 Subscriptions' },
  { id: 'budgets',       label: '💰 Budgets' },
  { id: 'settings',      label: '⚙️ Settings' },
]

const s = {
  shell: {
    display: 'flex', flexDirection: 'column', minHeight: '100vh',
  },
  header: {
    background: '#161b2e',
    borderBottom: '1px solid #2d3748',
    padding: '0 24px',
    display: 'flex', alignItems: 'center', gap: 32,
    position: 'sticky', top: 0, zIndex: 100,
  },
  logo: {
    fontSize: 18, fontWeight: 700, color: '#7c6af7',
    padding: '16px 0', whiteSpace: 'nowrap',
  },
  nav: { display: 'flex', gap: 4, overflowX: 'auto' },
  tab: (active) => ({
    padding: '18px 14px',
    border: 'none', background: 'none', cursor: 'pointer',
    fontSize: 14, fontWeight: active ? 600 : 400,
    color: active ? '#7c6af7' : '#94a3b8',
    borderBottom: active ? '2px solid #7c6af7' : '2px solid transparent',
    whiteSpace: 'nowrap', transition: 'color .15s',
  }),
  badge: {
    display: 'inline-block', background: '#22c55e',
    borderRadius: '50%', width: 8, height: 8, marginLeft: 6,
  },
  content: { flex: 1, padding: '24px', maxWidth: 1200, margin: '0 auto', width: '100%' },
}

export default function App() {
  const [tab, setTab]           = useState('dashboard')
  const [wsConnected, setWs]    = useState(false)
  const [refreshKey, setRefresh] = useState(0)

  const refresh = useCallback(() => setRefresh(k => k + 1), [])

  // WebSocket — live updates when new transactions arrive
  useEffect(() => {
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const ws    = new WebSocket(`${proto}://${window.location.host}/ws`)

    ws.onopen    = () => setWs(true)
    ws.onclose   = () => setWs(false)
    ws.onerror   = () => setWs(false)
    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data)
        if (msg.event === 'new_transaction') refresh()
      } catch {}
    }

    return () => ws.close()
  }, [refresh])

  const tabProps = { refreshKey, onRefresh: refresh }

  return (
    <div style={s.shell}>
      <header style={s.header}>
        <div style={s.logo}>💸 Bunshee</div>
        <nav style={s.nav}>
          {TABS.map(t => (
            <button key={t.id} style={s.tab(tab === t.id)} onClick={() => setTab(t.id)}>
              {t.label}
            </button>
          ))}
        </nav>
        {wsConnected && <span style={s.badge} title="Live updates connected" />}
      </header>

      <main style={s.content}>
        {tab === 'dashboard'     && <Dashboard    {...tabProps} />}
        {tab === 'transactions'  && <Transactions {...tabProps} />}
        {tab === 'subscriptions' && <Subscriptions {...tabProps} />}
        {tab === 'budgets'       && <Budgets      {...tabProps} />}
        {tab === 'settings'      && <Settings     {...tabProps} />}
      </main>
    </div>
  )
}
