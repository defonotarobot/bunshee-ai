import { useState, useEffect } from 'react'

const s = {
  card: {
    background: '#1a1d27', borderRadius: 12,
    padding: 24, border: '1px solid #2d3748', marginBottom: 16,
  },
  cardTitle: { fontSize: 15, fontWeight: 700, color: '#e2e8f0', marginBottom: 20 },
  row: { display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14 },
  label: { fontSize: 13, color: '#94a3b8', width: 200 },
  input: {
    background: '#0f1117', border: '1px solid #374151', color: '#e2e8f0',
    padding: '7px 12px', borderRadius: 8, fontSize: 13, flex: 1,
  },
  saveBtn: {
    background: '#7c6af7', color: '#fff', border: 'none',
    borderRadius: 8, padding: '8px 20px', cursor: 'pointer',
    fontSize: 13, fontWeight: 600, marginTop: 8,
  },
  section: { fontSize: 11, color: '#64748b', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 16 },
  info: {
    background: '#0f1117', borderRadius: 8, padding: '12px 16px',
    fontSize: 13, color: '#94a3b8', fontFamily: 'monospace',
    border: '1px solid #2d3748', marginBottom: 8,
  },
  tip: { fontSize: 12, color: '#64748b', marginTop: 4 },
}

export default function Settings({ refreshKey }) {
  const [cfg, setCfg]     = useState({})
  const [saved, setSaved] = useState(false)
  const [local, setLocal] = useState({
    alert_threshold: 85,
    report_time: '21:00',
    language: 'en',
  })

  useEffect(() => {
    fetch('/api/config')
      .then(r => r.json())
      .then(d => {
        setCfg(d)
        setLocal({
          alert_threshold: Math.round((d.alert_threshold || 0.85) * 100),
          report_time: d.report_time || '21:00',
          language: d.language || 'en',
        })
      })
  }, [refreshKey])

  const save = async () => {
    await fetch('/api/config', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        alert_threshold: local.alert_threshold / 100,
        report_time:     local.report_time,
        language:        local.language,
      }),
    })
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  return (
    <div>
      <h2 style={{ fontSize: 20, fontWeight: 700, marginBottom: 20 }}>Settings</h2>

      {/* Preferences */}
      <div style={s.card}>
        <div style={s.cardTitle}>Preferences</div>
        <div style={s.row}>
          <div style={s.label}>Budget alert threshold (%)</div>
          <input
            type="number" min={50} max={100}
            value={local.alert_threshold}
            onChange={e => setLocal(p => ({ ...p, alert_threshold: e.target.value }))}
            style={{ ...s.input, maxWidth: 100 }}
          />
          <span style={{ fontSize: 12, color: '#64748b' }}>Warn when a category hits this %</span>
        </div>
        <div style={s.row}>
          <div style={s.label}>Daily report time</div>
          <input
            type="time" value={local.report_time}
            onChange={e => setLocal(p => ({ ...p, report_time: e.target.value }))}
            style={{ ...s.input, maxWidth: 120 }}
          />
        </div>
        <div style={s.row}>
          <div style={s.label}>Report language</div>
          <select
            value={local.language}
            onChange={e => setLocal(p => ({ ...p, language: e.target.value }))}
            style={{ ...s.input, maxWidth: 120 }}
          >
            <option value="en">English</option>
            <option value="th">Thai</option>
          </select>
        </div>
        <button style={s.saveBtn} onClick={save}>{saved ? '✅ Saved' : 'Save'}</button>
      </div>

      {/* IMAP setup instructions */}
      <div style={s.card}>
        <div style={s.cardTitle}>Email (IMAP) Setup</div>
        <div style={s.section}>Gmail App Password</div>
        <ol style={{ paddingLeft: 20, fontSize: 13, color: '#94a3b8', lineHeight: 2 }}>
          <li>Go to <a href="https://myaccount.google.com/security" target="_blank" style={{ color: '#7c6af7' }}>Google Account → Security</a></li>
          <li>Under "How you sign in to Google" → enable 2-Step Verification if not already on</li>
          <li>Search "App Passwords" → create one named "Spending Tracker"</li>
          <li>Copy the 16-character password (no spaces)</li>
          <li>Add to your <code style={{ color: '#7c6af7' }}>.env</code> file as <code style={{ color: '#7c6af7' }}>IMAP_PASSWORD=xxxx xxxx xxxx xxxx</code></li>
        </ol>
        <div style={s.info}>IMAP_EMAIL=thr.leelasithorn@gmail.com{'\n'}IMAP_SERVER=imap.gmail.com</div>
      </div>

      {/* Telegram setup */}
      <div style={s.card}>
        <div style={s.cardTitle}>Telegram Setup</div>
        <div style={s.section}>Get your Chat ID</div>
        <ol style={{ paddingLeft: 20, fontSize: 13, color: '#94a3b8', lineHeight: 2 }}>
          <li>Open Telegram → find your new bot → send <code style={{ color: '#7c6af7' }}>/start</code></li>
          <li>Visit this URL in your browser:</li>
        </ol>
        <div style={s.info}>
          https://api.telegram.org/bot8696828333:AAGqaDW4G78K3vIOCDhEZgFq4lzDplw3pWo/getUpdates
        </div>
        <p style={s.tip}>Look for <code>"chat": {'{'}  "id": 123456789  {'}'}</code> — that number is your TELEGRAM_CHAT_ID.</p>
        <p style={{ ...s.tip, marginTop: 8 }}>Add it to <code style={{ color: '#7c6af7' }}>.env</code> as <code style={{ color: '#7c6af7' }}>TELEGRAM_CHAT_ID=123456789</code></p>
      </div>

      {/* Running the agent */}
      <div style={s.card}>
        <div style={s.cardTitle}>Running the Agent</div>
        <div style={s.info}>
          {'# Install dependencies\n'}
          {'pip install -r requirements.txt\n\n'}
          {'# Run the agent (starts everything)\n'}
          {'python agent.py'}
        </div>
        <div style={{ ...s.info, marginTop: 8 }}>
          {'# Build the dashboard (first time only)\n'}
          {'cd dashboard && npm install && npm run build'}
        </div>
        <div style={{ ...s.info, marginTop: 8 }}>
          {'# Access from iPhone via Tailscale:\n'}
          {'http://<your-mac-tailscale-ip>:3000'}
        </div>
      </div>
    </div>
  )
}
