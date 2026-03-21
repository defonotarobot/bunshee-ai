import { useState, useEffect } from 'react'
import {
  Chart as ChartJS,
  CategoryScale, LinearScale, BarElement, PointElement,
  LineElement, ArcElement, Title, Tooltip, Legend, Filler,
} from 'chart.js'
import { Bar, Line, Doughnut } from 'react-chartjs-2'

ChartJS.register(
  CategoryScale, LinearScale, BarElement, PointElement,
  LineElement, ArcElement, Title, Tooltip, Legend, Filler,
)

const COLORS = [
  '#7c6af7','#06b6d4','#22c55e','#f59e0b','#ef4444',
  '#8b5cf6','#ec4899','#14b8a6','#f97316',
]

const fmt = (n) => `฿${(n || 0).toLocaleString('th-TH', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`

const s = {
  grid: {
    display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
    gap: 16, marginBottom: 24,
  },
  card: {
    background: '#1a1d27', borderRadius: 12,
    padding: '20px 24px', border: '1px solid #2d3748',
  },
  cardLabel: { fontSize: 12, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: 1 },
  cardValue: { fontSize: 28, fontWeight: 700, marginTop: 6, color: '#e2e8f0' },
  cardSub:   { fontSize: 12, color: '#64748b', marginTop: 4 },
  charts:    { display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 16, marginBottom: 24 },
  chartBox: {
    background: '#1a1d27', borderRadius: 12,
    padding: 20, border: '1px solid #2d3748',
  },
  chartTitle: { fontSize: 14, fontWeight: 600, marginBottom: 16, color: '#cbd5e1' },
  budgetRow:  { display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 },
  budgetLabel:{ fontSize: 13, color: '#94a3b8', width: 110 },
  barOuter:   { flex: 1, background: '#2d3748', borderRadius: 4, height: 8 },
  barInner: (pct, warn) => ({
    width: `${Math.min(pct, 100)}%`, height: '100%', borderRadius: 4,
    background: pct >= 100 ? '#ef4444' : warn ? '#f59e0b' : '#7c6af7',
    transition: 'width .4s',
  }),
  budgetPct: { fontSize: 12, color: '#64748b', width: 36, textAlign: 'right' },
}

const chartOpts = (title) => ({
  responsive: true,
  plugins: { legend: { display: false }, title: { display: false } },
  scales: {
    x: { grid: { color: '#2d3748' }, ticks: { color: '#64748b', font: { size: 11 } } },
    y: { grid: { color: '#2d3748' }, ticks: { color: '#64748b', font: { size: 11 }, callback: v => `฿${(v/1000).toFixed(0)}k` } },
  },
})

export default function Dashboard({ refreshKey }) {
  const [data, setData]     = useState(null)
  const [month, setMonth]   = useState(() => new Date().toISOString().slice(0, 7))
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    fetch(`/api/summary?month=${month}`)
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false) })
      .catch(() => setLoading(false))
  }, [month, refreshKey])

  if (loading) return <p style={{ color: '#64748b', padding: 40 }}>Loading…</p>
  if (!data)   return <p style={{ color: '#ef4444' }}>Failed to load data.</p>

  const txCount    = data.count || 0
  const total      = data.total || 0
  const budgetLeft = (data.budget_total || 0) - total
  const days       = new Date().getDate()
  const avgDay     = days > 0 ? total / days : 0

  // Daily line chart
  const dailyLabels = (data.daily || []).map(d => d.date.slice(5))
  const dailyValues = (data.daily || []).map(d => d.total)
  const lineData = {
    labels: dailyLabels,
    datasets: [{
      data: dailyValues,
      borderColor: '#7c6af7',
      backgroundColor: 'rgba(124,106,247,0.12)',
      fill: true, tension: 0.4, pointRadius: 3,
    }],
  }

  // Category doughnut
  const cats    = Object.entries(data.categories || {})
  const doughData = {
    labels: cats.map(([k]) => k),
    datasets: [{
      data: cats.map(([, v]) => v),
      backgroundColor: COLORS,
      borderWidth: 0,
    }],
  }

  // Budget bars
  const perCat  = data.budget_per_category || {}
  const catBars = Object.entries(perCat).map(([cat, limit]) => ({
    cat, limit, spent: (data.categories || {})[cat] || 0,
  }))

  return (
    <div>
      {/* Month picker */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <h2 style={{ fontSize: 20, fontWeight: 700 }}>Overview</h2>
        <input
          type="month" value={month}
          onChange={e => setMonth(e.target.value)}
          style={{ background: '#1a1d27', border: '1px solid #2d3748', color: '#e2e8f0', padding: '6px 12px', borderRadius: 8, fontSize: 14 }}
        />
      </div>

      {/* Metric cards */}
      <div style={s.grid}>
        <div style={s.card}>
          <div style={s.cardLabel}>Total Spent</div>
          <div style={s.cardValue}>{fmt(total)}</div>
          <div style={s.cardSub}>{month}</div>
        </div>
        <div style={s.card}>
          <div style={s.cardLabel}>Transactions</div>
          <div style={s.cardValue}>{txCount}</div>
          <div style={s.cardSub}>this month</div>
        </div>
        <div style={s.card}>
          <div style={s.cardLabel}>Avg / Day</div>
          <div style={s.cardValue}>{fmt(avgDay)}</div>
          <div style={s.cardSub}>day {days} of month</div>
        </div>
        <div style={{ ...s.card, borderColor: budgetLeft < 0 ? '#ef4444' : '#2d3748' }}>
          <div style={s.cardLabel}>Budget Left</div>
          <div style={{ ...s.cardValue, color: budgetLeft < 0 ? '#ef4444' : '#22c55e' }}>
            {fmt(Math.abs(budgetLeft))}
            {budgetLeft < 0 && ' over'}
          </div>
          <div style={s.cardSub}>of {fmt(data.budget_total)}</div>
        </div>
      </div>

      {/* Charts row */}
      <div style={s.charts}>
        <div style={s.chartBox}>
          <div style={s.chartTitle}>Daily Spending</div>
          {dailyLabels.length > 0
            ? <Line data={lineData} options={chartOpts()} />
            : <p style={{ color: '#64748b' }}>No data yet.</p>
          }
        </div>

        <div style={s.chartBox}>
          <div style={s.chartTitle}>By Category</div>
          {cats.length > 0
            ? <>
                <Doughnut data={doughData} options={{
                  responsive: true, cutout: '65%',
                  plugins: {
                    legend: { position: 'bottom', labels: { color: '#94a3b8', font: { size: 11 }, boxWidth: 12 } },
                  },
                }} />
              </>
            : <p style={{ color: '#64748b' }}>No data yet.</p>
          }
        </div>
      </div>

      {/* Budget progress */}
      {catBars.length > 0 && (
        <div style={s.chartBox}>
          <div style={s.chartTitle}>Budget Status</div>
          {catBars.map(({ cat, limit, spent }) => {
            const pct = limit ? (spent / limit) * 100 : 0
            return (
              <div key={cat} style={s.budgetRow}>
                <div style={s.budgetLabel}>{cat}</div>
                <div style={s.barOuter}>
                  <div style={s.barInner(pct, pct >= 85)} />
                </div>
                <div style={s.budgetPct}>{pct.toFixed(0)}%</div>
                <div style={{ fontSize: 12, color: '#64748b', width: 130, textAlign: 'right' }}>
                  {fmt(spent)} / {fmt(limit)}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
