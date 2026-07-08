import { useState, useEffect, useCallback } from 'react'

interface HeartbeatEvent {
  id: string
  type: 'light' | 'deep' | 'curiosity' | 'initiative' | 'cron' | 'proactive'
  timestamp: string
  actions: Record<string, unknown>
}

const TYPE_CONFIG: Record<string, { label: string; color: string; bg: string }> = {
  light:      { label: 'LIGHT',      color: '#06b6d4', bg: 'rgba(6,182,212,0.12)' },
  deep:       { label: 'DEEP REM',   color: '#a78bfa', bg: 'rgba(167,139,250,0.12)' },
  curiosity:  { label: 'CURIOSITY',  color: '#f59e0b', bg: 'rgba(245,158,11,0.12)' },
  initiative: { label: 'INITIATIVE', color: '#22c55e', bg: 'rgba(34,197,94,0.12)' },
  cron:       { label: 'CRON',       color: '#38bdf8', bg: 'rgba(56,189,248,0.12)' },
  proactive:  { label: 'PROACTIVE', color: '#ec4899', bg: 'rgba(236,72,153,0.12)' },
}

function relativeTime(iso: string): string {
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (diff < 60)   return `${diff}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return new Date(iso).toLocaleDateString()
}

function ActionPills({ actions }: { actions: Record<string, unknown> }) {
  const pills: { label: string; value: string; nonzero: boolean }[] = []
  for (const [k, v] of Object.entries(actions)) {
    if (k === 'patterns' || k === 'types') continue
    const val = typeof v === 'number' ? v : String(v)
    const nonzero = typeof val === 'number' ? val > 0 : val !== '0'
    pills.push({ label: k.replace(/_/g, ' '), value: String(val), nonzero })
  }
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
      {pills.map(p => (
        <span key={p.label} style={{
          fontSize: 11,
          padding: '2px 8px',
          borderRadius: 4,
          background: p.nonzero ? 'rgba(255,255,255,0.08)' : 'rgba(255,255,255,0.03)',
          color: p.nonzero ? '#cbd5e1' : '#475569',
          border: '1px solid rgba(255,255,255,0.06)',
        }}>
          {p.label}: <b>{p.value}</b>
        </span>
      ))}
    </div>
  )
}

function EventRow({ ev }: { ev: HeartbeatEvent }) {
  const [expanded, setExpanded] = useState(false)
  const cfg = TYPE_CONFIG[ev.type] ?? { label: ev.type.toUpperCase(), color: '#94a3b8', bg: 'rgba(148,163,184,0.1)' }
  const patterns = ev.actions.patterns as string[] | undefined
  const types    = ev.actions.types    as string[] | undefined

  return (
    <div style={{
      borderBottom: '1px solid rgba(255,255,255,0.05)',
      padding: '10px 0',
    }}>
      <div
        style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer' }}
        onClick={() => setExpanded(x => !x)}
      >
        {/* type badge */}
        <span style={{
          fontSize: 10,
          fontWeight: 700,
          padding: '2px 7px',
          borderRadius: 4,
          color: cfg.color,
          background: cfg.bg,
          border: `1px solid ${cfg.color}33`,
          minWidth: 80,
          textAlign: 'center',
          flexShrink: 0,
        }}>
          {cfg.label}
        </span>
        {/* time */}
        <span style={{ fontSize: 11, color: '#64748b', flexShrink: 0, minWidth: 70 }}>
          {relativeTime(ev.timestamp)}
        </span>
        {/* summary pills inline */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <ActionPills actions={ev.actions} />
        </div>
        {/* expand chevron */}
        <span style={{ color: '#475569', fontSize: 12, flexShrink: 0 }}>
          {expanded ? '▲' : '▼'}
        </span>
      </div>

      {expanded && (
        <div style={{
          marginTop: 10,
          paddingLeft: 90,
          fontSize: 11,
          color: '#94a3b8',
          display: 'flex',
          flexDirection: 'column',
          gap: 4,
        }}>
          <div style={{ color: '#64748b', fontFamily: 'monospace' }}>
            {new Date(ev.timestamp).toLocaleString()} · id: {ev.id}
          </div>
          {patterns && patterns.length > 0 && (
            <div>
              <span style={{ color: '#64748b' }}>🔍 patterns: </span>
              {patterns.map((p: string, i: number) => (
                <span key={i} style={{ marginRight: 8, color: '#c084fc' }}>"{p}"</span>
              ))}
            </div>
          )}

          {/* Promoted memories */}
          {(ev.actions.promoted_snippets as string[] | undefined)?.length! > 0 && (
            <div>
              <div style={{ color: '#22c55e', marginBottom: 2 }}>⬆ promoted to semantic:</div>
              {(ev.actions.promoted_snippets as string[]).map((s: string, i: number) => (
                <div key={i} style={{ paddingLeft: 12, color: '#86efac', fontStyle: 'italic' }}>· {s}…</div>
              ))}
            </div>
          )}

          {/* Pruned / dormant memories */}
          {(ev.actions.pruned_snippets as string[] | undefined)?.length! > 0 && (
            <div>
              <div style={{ color: '#f87171', marginBottom: 2 }}>🗑 pruned / dormant:</div>
              {(ev.actions.pruned_snippets as string[]).map((s: string, i: number) => (
                <div key={i} style={{ paddingLeft: 12, color: '#fca5a5', fontStyle: 'italic' }}>· {s}…</div>
              ))}
            </div>
          )}

          {/* Deduped pairs */}
          {(ev.actions.deduped_pairs as Array<{winner:string,loser:string}> | undefined)?.length! > 0 && (
            <div>
              <div style={{ color: '#fb923c', marginBottom: 2 }}>♻ deduped pairs (winner kept):</div>
              {(ev.actions.deduped_pairs as Array<{winner:string,loser:string}>).map((p, i) => (
                <div key={i} style={{ paddingLeft: 12, fontSize: 10 }}>
                  <span style={{ color: '#86efac' }}>✓ {p.winner}…</span>
                  {' → '}
                  <span style={{ color: '#f87171', textDecoration: 'line-through' }}>{p.loser}…</span>
                </div>
              ))}
            </div>
          )}

          {/* Curiosity skip reason */}
          {(ev.actions.skip_reason as string | undefined) && (
            <div style={{ color: '#64748b', fontStyle: 'italic' }}>
              ⏭ skipped: {ev.actions.skip_reason as string}
            </div>
          )}

          {/* Curiosity topics searched */}
          {(ev.actions.topics as string[] | undefined)?.length! > 0 && (
            <div>
              <span style={{ color: '#64748b' }}>🔎 searched: </span>
              {(ev.actions.topics as string[]).map((t: string, i: number) => (
                <span key={i} style={{ marginRight: 8, color: '#fbbf24' }}>"{t}"</span>
              ))}
            </div>
          )}

          {types && types.length > 0 && (
            <div>
              <span style={{ color: '#64748b' }}>initiative types: </span>
              {types.join(', ')}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function HeartbeatPanel({ active }: { active: boolean }) {
  const [events, setEvents]     = useState<HeartbeatEvent[]>([])
  const [loading, setLoading]   = useState(false)
  const [error, setError]       = useState<string | null>(null)
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null)

  const fetch_ = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const r = await fetch('/api/consolidation/heartbeat-log?limit=30')
      if (!r.ok) throw new Error(`${r.status}`)
      const data: HeartbeatEvent[] = await r.json()
      setEvents(data)
      setLastRefresh(new Date())
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!active) return
    fetch_()
    const id = setInterval(fetch_, 30_000)
    return () => clearInterval(id)
  }, [active, fetch_])

  return (
    <div style={{
      flex: 1,
      overflow: 'hidden',
      display: 'flex',
      flexDirection: 'column',
      padding: '20px 24px',
      gap: 16,
    }}>
      {/* header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <div style={{ fontSize: 15, fontWeight: 600, color: '#e2e8f0' }}>Heartbeat Log</div>
          <div style={{ fontSize: 12, color: '#64748b', marginTop: 2 }}>
            Cognitive cycles — consolidation, curiosity, initiative, proactive outreach
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {lastRefresh && (
            <span style={{ fontSize: 11, color: '#475569' }}>
              refreshed {relativeTime(lastRefresh.toISOString())}
            </span>
          )}
          <button
            onClick={fetch_}
            disabled={loading}
            style={{
              padding: '5px 12px',
              borderRadius: 6,
              border: '1px solid rgba(255,255,255,0.1)',
              background: 'rgba(255,255,255,0.05)',
              color: '#94a3b8',
              cursor: loading ? 'default' : 'pointer',
              fontSize: 12,
            }}
          >
            {loading ? '…' : '↻ Refresh'}
          </button>
        </div>
      </div>

      {/* legend */}
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        {Object.entries(TYPE_CONFIG).map(([k, cfg]) => (
          <span key={k} style={{ fontSize: 11, color: cfg.color, display: 'flex', alignItems: 'center', gap: 4 }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: cfg.color, display: 'inline-block' }} />
            {cfg.label}
          </span>
        ))}
      </div>

      {/* content */}
      <div style={{
        flex: 1,
        overflowY: 'auto',
        background: 'rgba(255,255,255,0.02)',
        borderRadius: 8,
        border: '1px solid rgba(255,255,255,0.06)',
        padding: '8px 16px',
      }}>
        {error && (
          <div style={{ color: '#ef4444', fontSize: 12, padding: '20px 0' }}>Error: {error}</div>
        )}
        {!error && events.length === 0 && !loading && (
          <div style={{ color: '#475569', fontSize: 13, padding: '40px 0', textAlign: 'center' }}>
            No heartbeat events yet. Waiting for first cycle (every 5 min while idle)…
          </div>
        )}
        {events.map(ev => <EventRow key={ev.id + ev.timestamp} ev={ev} />)}
      </div>
    </div>
  )
}
