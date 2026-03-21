import { useState, useEffect } from 'react'

const fmt = (n) => `฿${(n || 0).toLocaleString('th-TH', { minimumFractionDigits: 2 })}`

function daysUntil(dateStr) {
  if (!dateStr) return null
  const diff = new Date(dateStr) - new Date()
  return Math.ceil(diff / (1000 * 60 * 60 * 24))
}

const s = {
  grid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
    gap: 16, marginBottom: 24,
  },
  card: {
    background: '#1a1d27', borderRadius: 12,
    padding: 20, border: '1px solid #2d3748',
    display: 'flex', flexDirection: 'column', gap: 8,
  },
  name:   { fontSize: 16, fontWeight: 700, color: '#e2e8f0' },
  amount: { fontSize: 22, fontWeight: 700, color: '#7c6af7' },
  meta:   { fontSize: 12, color: '#64748b' },
  renewalBadge: (days) => ({
    display: 'inline-block', padding: '3px 10px', borderRadius: 6,
    fontSize: 11, fontWeight: 600,
    background: days <= 3 ? '#7c2d12' : days <= 7 ? '#451a03' : '#1e2535',
    color: days <= 3 ? '#fca5a5' : days <= 7 ? '#fed7aa' : '#94a3b8',
  }),
  summary: {
    background: '#161b2e', borderRadius: 12,
    padding: '20px 24px', border: '1px solid #2d3748',
    display: 'flex', gap: 40, marginBottom: 24,
  },
  sumLabel: { fontSize: 12, color: '#64748b', textTransform: 'uppercase', letterSpacing: 1 },
  sumValue: { fontSize: 28, fontWeight: 700, color: '#e2e8f0', marginTop: 4 },
  empty:    { color: '#64748b', textAlign: 'center', padding: 60 },
}

export default function Subscriptions({ refreshKey }) {
  const [subs, setSubs]     = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    fetch('/api/subscriptions')
      .then(r => r.json())
      .then(d => { setSubs(d); setLoading(false) })
      .catch(() => setLoading(false))
  }, [refreshKey])

  const monthlyTotal = subs
    .filter(s => s.billing_cycle === 'monthly')
    .reduce((acc, s) => acc + (s.amount || 0), 0)
  const yearlyTotal  = monthlyTotal * 12

  if (loading) return <p style={s.empty}>Loading…</p>

  return (
    <div>
      <h2 style={{ fontSize: 20, fontWeight: 700, marginBottom: 20 }}>Subscriptions</h2>

      {subs.length > 0 && (
        <div style={s.summary}>
          <div>
            <div style={s.sumLabel}>Monthly Total</div>
            <div style={s.sumValue}>{fmt(monthlyTotal)}</div>
          </div>
          <div>
            <div style={s.sumLabel}>Year-to-date</div>
            <div style={s.sumValue}>{fmt(yearlyTotal)}</div>
          </div>
          <div>
            <div style={s.sumLabel}>Active</div>
            <div style={s.sumValue}>{subs.length}</div>
          </div>
        </div>
      )}

      {subs.length === 0 ? (
        <p style={s.empty}>No subscriptions tracked yet.<br />They appear automatically when charge emails are received.</p>
      ) : (
        <div style={s.grid}>
          {subs.map(sub => {
            const days = daysUntil(sub.next_renewal)
            return (
              <div key={sub.id} style={s.card}>
                <div style={s.name}>📱 {sub.service_name}</div>
                <div style={s.amount}>{fmt(sub.amount)}<span style={{ fontSize: 13, color: '#64748b', fontWeight: 400 }}> / {sub.billing_cycle}</span></div>
                <div style={s.meta}>Last charged: {sub.last_charged || '—'}</div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <div style={s.meta}>Renews: {sub.next_renewal || '—'}</div>
                  {days != null && (
                    <span style={s.renewalBadge(days)}>
                      {days <= 0 ? 'Today!' : `in ${days}d`}
                    </span>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Renewal calendar — upcoming 30 days */}
      {subs.length > 0 && (
        <div style={{ background: '#1a1d27', borderRadius: 12, padding: 20, border: '1px solid #2d3748' }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: '#cbd5e1', marginBottom: 16 }}>
            Upcoming Renewals
          </div>
          {subs
            .filter(s => {
              const d = daysUntil(s.next_renewal)
              return d != null && d <= 30 && d >= 0
            })
            .sort((a, b) => new Date(a.next_renewal) - new Date(b.next_renewal))
            .map(sub => {
              const days = daysUntil(sub.next_renewal)
              return (
                <div key={sub.id} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '8px 0', borderBottom: '1px solid #1e2535' }}>
                  <span style={s.renewalBadge(days)}>{days === 0 ? 'Today' : `${days}d`}</span>
                  <span style={{ fontSize: 14, color: '#e2e8f0' }}>{sub.service_name}</span>
                  <span style={{ marginLeft: 'auto', fontSize: 14, fontWeight: 600, color: '#7c6af7' }}>{fmt(sub.amount)}</span>
                </div>
              )
            })}
        </div>
      )}
    </div>
  )
}
