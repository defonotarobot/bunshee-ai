import { useState, useEffect } from 'react'

const fmt = (n) => `฿${(n || 0).toLocaleString('th-TH', { minimumFractionDigits: 0 })}`

const EMOJI = {
  'Food & Drink':'🍜','Transport':'🚗','Shopping':'🛍','Groceries':'🛒',
  'Coffee':'☕','Entertainment':'🎬','Subscriptions':'📱','Transfer':'💸','Other':'📦',
}

const s = {
  card: {
    background: '#1a1d27', borderRadius: 12,
    padding: 24, border: '1px solid #2d3748', marginBottom: 16,
  },
  row: { display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 },
  catLabel: { fontSize: 15, fontWeight: 600, color: '#e2e8f0', width: 160 },
  barOuter: {
    flex: 1, background: '#2d3748', borderRadius: 6, height: 10, overflow: 'hidden',
  },
  barInner: (pct) => ({
    height: '100%', borderRadius: 6,
    width: `${Math.min(pct, 100)}%`,
    background: pct >= 100 ? '#ef4444' : pct >= 85 ? '#f59e0b' : '#7c6af7',
    transition: 'width .4s',
  }),
  pctLabel: { fontSize: 13, color: '#94a3b8', width: 44, textAlign: 'right' },
  spentLabel: { fontSize: 13, color: '#64748b', width: 180, textAlign: 'right' },
  input: {
    background: '#0f1117', border: '1px solid #374151', color: '#e2e8f0',
    padding: '4px 10px', borderRadius: 6, fontSize: 13, width: 110, textAlign: 'right',
  },
  saveBtn: {
    background: '#7c6af7', color: '#fff', border: 'none',
    borderRadius: 8, padding: '8px 20px', cursor: 'pointer',
    fontSize: 13, fontWeight: 600,
  },
  totalCard: {
    background: '#161b2e', borderRadius: 12,
    padding: '20px 24px', border: '1px solid #2d3748',
    marginBottom: 24, display: 'flex', gap: 40, alignItems: 'center',
  },
  totalLabel: { fontSize: 12, color: '#64748b', textTransform: 'uppercase', letterSpacing: 1 },
  totalValue: { fontSize: 26, fontWeight: 700, color: '#e2e8f0', marginTop: 4 },
}

export default function Budgets({ refreshKey }) {
  const [data, setData]     = useState(null)
  const [limits, setLimits] = useState({})
  const [total, setTotal]   = useState(0)
  const [saved, setSaved]   = useState(false)

  const load = () =>
    fetch('/api/budgets')
      .then(r => r.json())
      .then(d => {
        setData(d)
        const lims = {}
        Object.entries(d.per_category || {}).forEach(([k, v]) => { lims[k] = v.limit })
        setLimits(lims)
        setTotal(d.total_budget || 0)
      })

  useEffect(() => { load() }, [refreshKey])

  const save = async () => {
    const payload = {
      total: Number(total),
      per_category: Object.fromEntries(
        Object.entries(limits).map(([k, v]) => [k, Number(v)])
      ),
    }
    await fetch('/api/budgets', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
    load()
  }

  if (!data) return <p style={{ color: '#64748b', padding: 40 }}>Loading…</p>

  const totalPct = data.total_budget ? (data.total_spent / data.total_budget) * 100 : 0

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <h2 style={{ fontSize: 20, fontWeight: 700 }}>Budgets — {data.month}</h2>
        <button style={s.saveBtn} onClick={save}>
          {saved ? '✅ Saved' : 'Save Changes'}
        </button>
      </div>

      {/* Overall total */}
      <div style={s.totalCard}>
        <div>
          <div style={s.totalLabel}>Total Spent</div>
          <div style={s.totalValue}>{fmt(data.total_spent)}</div>
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ ...s.barOuter, height: 14 }}>
            <div style={s.barInner(totalPct)} />
          </div>
          <div style={{ fontSize: 12, color: '#64748b', marginTop: 4 }}>
            {totalPct.toFixed(0)}% of monthly budget
          </div>
        </div>
        <div>
          <div style={s.totalLabel}>Budget</div>
          <input
            type="number" value={total}
            onChange={e => setTotal(e.target.value)}
            style={{ ...s.input, fontSize: 18, padding: '6px 12px' }}
          />
        </div>
      </div>

      {/* Per-category */}
      <div style={s.card}>
        <div style={{ fontSize: 14, fontWeight: 600, color: '#cbd5e1', marginBottom: 20 }}>
          Per-Category Limits
          <span style={{ fontSize: 12, color: '#64748b', fontWeight: 400, marginLeft: 8 }}>
            (click the amount to edit)
          </span>
        </div>
        {Object.entries(data.per_category || {}).map(([cat, { spent, limit }]) => {
          const pct = limit ? (spent / limit) * 100 : 0
          return (
            <div key={cat} style={s.row}>
              <div style={s.catLabel}>{EMOJI[cat] || '📦'} {cat}</div>
              <div style={s.barOuter}>
                <div style={s.barInner(pct)} />
              </div>
              <div style={s.pctLabel}>{pct.toFixed(0)}%</div>
              <div style={s.spentLabel}>{fmt(spent)} /</div>
              <input
                type="number"
                value={limits[cat] ?? limit}
                onChange={e => setLimits(prev => ({ ...prev, [cat]: e.target.value }))}
                style={s.input}
              />
            </div>
          )
        })}
      </div>
    </div>
  )
}
