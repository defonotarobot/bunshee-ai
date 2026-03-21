import { useState, useEffect } from 'react'

const CATEGORIES = [
  'All','Food & Drink','Transport','Shopping','Groceries',
  'Coffee','Entertainment','Subscriptions','Transfer','Other',
]
const SOURCES = ['All','KTC','KBank','Subscription']

const fmt = (n) => `฿${(n || 0).toLocaleString('th-TH', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

const EMOJI = {
  'Food & Drink':'🍜','Transport':'🚗','Shopping':'🛍','Groceries':'🛒',
  'Coffee':'☕','Entertainment':'🎬','Subscriptions':'📱','Transfer':'💸','Other':'📦',
}

const s = {
  toolbar: {
    display: 'flex', gap: 10, marginBottom: 16, flexWrap: 'wrap', alignItems: 'center',
  },
  select: {
    background: '#1a1d27', border: '1px solid #2d3748', color: '#e2e8f0',
    padding: '7px 12px', borderRadius: 8, fontSize: 13,
  },
  input: {
    background: '#1a1d27', border: '1px solid #2d3748', color: '#e2e8f0',
    padding: '7px 12px', borderRadius: 8, fontSize: 13,
  },
  syncBtn: {
    marginLeft: 'auto', background: '#7c6af7', color: '#fff',
    border: 'none', borderRadius: 8, padding: '8px 16px',
    cursor: 'pointer', fontSize: 13, fontWeight: 600,
  },
  table: { width: '100%', borderCollapse: 'collapse' },
  th: {
    background: '#161b2e', padding: '10px 14px', textAlign: 'left',
    fontSize: 12, color: '#64748b', fontWeight: 600,
    textTransform: 'uppercase', letterSpacing: 0.5,
    borderBottom: '1px solid #2d3748',
  },
  tr: (alt) => ({
    background: alt ? '#161b2e' : '#1a1d27',
    borderBottom: '1px solid #1e2535',
  }),
  td: { padding: '10px 14px', fontSize: 13 },
  badge: (src) => ({
    display: 'inline-block', padding: '2px 8px', borderRadius: 4, fontSize: 11,
    fontWeight: 600,
    background: src === 'KTC' ? '#312e81' : src === 'KBank' ? '#064e3b' : '#1e1b4b',
    color: src === 'KTC' ? '#a5b4fc' : src === 'KBank' ? '#6ee7b7' : '#c4b5fd',
  }),
  catChip: {
    display: 'inline-block', padding: '2px 8px', borderRadius: 12,
    fontSize: 11, background: '#2d3748', color: '#94a3b8',
  },
  clarify: {
    display: 'inline-block', padding: '2px 8px', borderRadius: 4,
    fontSize: 10, background: '#7c2d12', color: '#fca5a5', marginLeft: 6,
  },
  empty: { textAlign: 'center', color: '#64748b', padding: 40 },
}

export default function Transactions({ refreshKey }) {
  const [txs, setTxs]           = useState([])
  const [loading, setLoading]   = useState(true)
  const [syncing, setSyncing]   = useState(false)
  const [category, setCategory] = useState('All')
  const [source, setSource]     = useState('All')
  const [month, setMonth]       = useState(() => new Date().toISOString().slice(0, 7))
  const [search, setSearch]     = useState('')

  const load = () => {
    setLoading(true)
    const params = new URLSearchParams({ limit: 500, month })
    if (category !== 'All') params.set('category', category)
    if (source !== 'All')   params.set('source', source)
    fetch(`/api/transactions?${params}`)
      .then(r => r.json())
      .then(d => { setTxs(d); setLoading(false) })
      .catch(() => setLoading(false))
  }

  useEffect(load, [category, source, month, refreshKey])

  const sync = async () => {
    setSyncing(true)
    await fetch('/api/sync', { method: 'POST' })
    setTimeout(() => { setSyncing(false); load() }, 3000)
  }

  const filtered = txs.filter(t =>
    !search || t.merchant?.toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <h2 style={{ fontSize: 20, fontWeight: 700 }}>Transactions</h2>
        <span style={{ color: '#64748b', fontSize: 13 }}>{filtered.length} records</span>
      </div>

      <div style={s.toolbar}>
        <input
          type="month" value={month} onChange={e => setMonth(e.target.value)}
          style={s.input}
        />
        <select value={source} onChange={e => setSource(e.target.value)} style={s.select}>
          {SOURCES.map(s => <option key={s}>{s}</option>)}
        </select>
        <select value={category} onChange={e => setCategory(e.target.value)} style={s.select}>
          {CATEGORIES.map(c => <option key={c}>{c}</option>)}
        </select>
        <input
          placeholder="Search merchant…" value={search}
          onChange={e => setSearch(e.target.value)}
          style={{ ...s.input, minWidth: 160 }}
        />
        <button style={s.syncBtn} onClick={sync} disabled={syncing}>
          {syncing ? '⟳ Syncing…' : '⟳ Sync Inbox'}
        </button>
      </div>

      {loading ? (
        <p style={s.empty}>Loading…</p>
      ) : filtered.length === 0 ? (
        <p style={s.empty}>No transactions found.</p>
      ) : (
        <div style={{ background: '#1a1d27', borderRadius: 12, border: '1px solid #2d3748', overflow: 'hidden' }}>
          <table style={s.table}>
            <thead>
              <tr>
                {['Date', 'Source', 'Merchant', 'Category', 'Amount', 'Confidence'].map(h => (
                  <th key={h} style={s.th}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((t, i) => (
                <tr key={t.id} style={s.tr(i % 2)}>
                  <td style={{ ...s.td, color: '#64748b', whiteSpace: 'nowrap' }}>
                    {t.timestamp?.slice(0, 16).replace('T', ' ')}
                  </td>
                  <td style={s.td}><span style={s.badge(t.source)}>{t.source}</span></td>
                  <td style={s.td}>
                    <span style={{ color: '#e2e8f0' }}>{t.merchant}</span>
                    {t.clarification_needed ? <span style={s.clarify}>pending</span> : null}
                    {t.notes && <div style={{ fontSize: 11, color: '#64748b', marginTop: 2 }}>{t.notes}</div>}
                  </td>
                  <td style={s.td}>
                    <span style={s.catChip}>{EMOJI[t.category] || '📦'} {t.category}</span>
                  </td>
                  <td style={{ ...s.td, fontWeight: 600, color: '#22c55e', textAlign: 'right' }}>
                    {fmt(t.amount)}
                  </td>
                  <td style={{ ...s.td, color: t.confidence >= 0.8 ? '#22c55e' : t.confidence >= 0.6 ? '#f59e0b' : '#ef4444' }}>
                    {t.confidence != null ? `${(t.confidence * 100).toFixed(0)}%` : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
