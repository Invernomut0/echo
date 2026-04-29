import { useState, useEffect, useCallback, useRef } from 'react'
import {
  fetchCuriosityActivity,
  triggerCuriosityCycle,
  type CycleRecord,
  type CuriosityActivity,
  type CuriosityFinding,
} from '../api'

// ── Constants ─────────────────────────────────────────────────────────────

const SOURCE_META: Record<string, { label: string; color: string; emoji: string }> = {
  arxiv:      { label: 'arXiv',      color: '#38bdf8', emoji: '📄' },
  hn:         { label: 'HN',         color: '#f97316', emoji: '🟠' },
  wikipedia:  { label: 'Wikipedia',  color: '#86efac', emoji: '📖' },
  duckduckgo: { label: 'DDG',        color: '#c084fc', emoji: '🔍' },
  brave:      { label: 'Brave',      color: '#fb923c', emoji: '🦁' },
  fetch:      { label: 'Fetch',      color: '#fbbf24', emoji: '🌐' },
}

const STATUS_META: Record<string, { label: string; color: string; dot: string }> = {
  running:   { label: 'Running',   color: '#22d3ee', dot: '#22d3ee' },
  completed: { label: 'Done',      color: '#4ade80', dot: '#4ade80' },
  skipped:   { label: 'Skipped',   color: '#94a3b8', dot: '#94a3b8' },
  error:     { label: 'Error',     color: '#f43f5e', dot: '#f43f5e' },
}

const POLL_INTERVAL_MS = 8_000

// ── Helpers ───────────────────────────────────────────────────────────────

function fmtTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function fmtDate(iso: string): string {
  const d = new Date(iso)
  const today = new Date()
  if (d.toDateString() === today.toDateString()) return `Today · ${fmtTime(iso)}`
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' }) + ' · ' + fmtTime(iso)
}

function fmtDuration(start: string, end: string | null): string {
  if (!end) return '…'
  const ms = new Date(end).getTime() - new Date(start).getTime()
  if (ms < 1000) return `${ms}ms`
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`
  return `${Math.round(ms / 60_000)}m`
}

function fmtIdle(secs: number | null): string {
  if (secs === null) return '—'
  if (secs < 60) return `${secs.toFixed(0)}s`
  if (secs < 3600) return `${(secs / 60).toFixed(0)}m`
  return `${(secs / 3600).toFixed(1)}h`
}

// ── Sub-components ────────────────────────────────────────────────────────

function TopicPill({ text }: { text: string }) {
  return (
    <span className="curiosity-topic-pill">{text}</span>
  )
}

function SourceBar({ bySource }: { bySource: Record<string, number> }) {
  const total = Object.values(bySource).reduce((a, b) => a + b, 0)
  if (total === 0) return null
  const sources = Object.entries(bySource).filter(([, n]) => n > 0)
  return (
    <div style={{ marginTop: 8 }}>
      <div style={{ fontSize: 10, color: '#475569', letterSpacing: '0.07em', textTransform: 'uppercase', marginBottom: 5 }}>
        Sources · {total} results
      </div>
      {/* Stacked bar */}
      <div className="curiosity-source-bar">
        {sources.map(([src, n]) => {
          const meta = SOURCE_META[src] ?? { color: '#64748b', label: src, emoji: '•' }
          return (
            <div
              key={src}
              className="curiosity-source-segment"
              style={{ width: `${(n / total) * 100}%`, background: meta.color }}
              title={`${meta.label}: ${n}`}
            />
          )
        })}
      </div>
      {/* Legend */}
      <div className="curiosity-source-legend">
        {sources.map(([src, n]) => {
          const meta = SOURCE_META[src] ?? { color: '#64748b', label: src, emoji: '•' }
          return (
            <span key={src} className="curiosity-source-chip" style={{ '--chip-color': meta.color } as React.CSSProperties}>
              <span style={{ color: meta.color, fontSize: 9, marginRight: 3 }}>■</span>
              {meta.label} <span style={{ opacity: 0.6 }}>{n}</span>
            </span>
          )
        })}
      </div>
    </div>
  )
}

function FindingsAccordion({ findings }: { findings: CuriosityFinding[] }) {
  const [open, setOpen] = useState(false)
  if (findings.length === 0) return null
  return (
    <div style={{ marginTop: 8 }}>
      <button
        className="curiosity-findings-toggle"
        onClick={() => setOpen(o => !o)}
      >
        <span>{open ? '▾' : '▸'}</span>
        <span>{findings.length} finding{findings.length !== 1 ? 's' : ''} stored</span>
      </button>
      {open && (
        <div className="curiosity-findings-list">
          {findings.map((f, i) => {
            const meta = SOURCE_META[f.source] ?? { color: '#64748b', label: f.source, emoji: '•' }
            return (
              <div key={i} className="curiosity-finding-row">
                <span style={{ color: meta.color, fontSize: 11, flexShrink: 0 }}>{meta.emoji}</span>
                <div style={{ minWidth: 0 }}>
                  {f.url ? (
                    <a href={f.url} target="_blank" rel="noopener noreferrer" className="curiosity-finding-title">
                      {f.title}
                    </a>
                  ) : (
                    <span className="curiosity-finding-title" style={{ cursor: 'default' }}>{f.title}</span>
                  )}
                  <div style={{ fontSize: 10, color: '#475569', marginTop: 1 }}>
                    <span style={{ color: meta.color }}>{meta.label}</span>
                    {' · '}
                    <span style={{ color: '#a78bfa' }}>{f.topic}</span>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

function CycleCard({ cycle }: { cycle: CycleRecord }) {
  const st = STATUS_META[cycle.status] ?? STATUS_META.error
  const isCompleted = cycle.status === 'completed'
  const isRunning = cycle.status === 'running'

  return (
    <div className={`curiosity-cycle-card ${isRunning ? 'curiosity-cycle-card--running' : ''}`}>
      {/* Header row */}
      <div className="curiosity-cycle-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
          <span
            className="curiosity-status-dot"
            style={{ background: st.dot, boxShadow: isRunning ? `0 0 8px ${st.dot}` : 'none' }}
          />
          <span style={{ fontSize: 12, color: '#e2e8f0', fontWeight: 500 }}>
            {fmtDate(cycle.started_at)}
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
          {cycle.idle_seconds !== null && (
            <span style={{ fontSize: 10, color: '#475569' }}>
              idle {fmtIdle(cycle.idle_seconds)}
            </span>
          )}
          <span className="curiosity-status-badge" style={{ color: st.color, borderColor: st.color + '33' }}>
            {isRunning ? '⟳ ' : ''}{st.label}
          </span>
          <span style={{ fontSize: 10, color: '#334155' }}>
            {fmtDuration(cycle.started_at, cycle.finished_at)}
          </span>
        </div>
      </div>

      {/* Skip reason */}
      {cycle.skip_reason && (
        <div style={{ fontSize: 11, color: '#64748b', marginTop: 6, fontStyle: 'italic' }}>
          ↳ {cycle.skip_reason}
        </div>
      )}

      {/* Topics */}
      {cycle.topics_searched.length > 0 && (
        <div style={{ marginTop: 8 }}>
          <div style={{ fontSize: 10, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 5 }}>
            Topics searched
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
            {cycle.topics_searched.map((t) => <TopicPill key={t} text={t} />)}
          </div>
        </div>
      )}
      {cycle.topics_proposed.length > 0 && cycle.topics_searched.length === 0 && (
        <div style={{ marginTop: 8 }}>
          <div style={{ fontSize: 10, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 5 }}>
            Topics proposed
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
            {cycle.topics_proposed.map((t) => (
              <span key={t} className="curiosity-topic-pill" style={{ opacity: 0.45 }}>{t}</span>
            ))}
          </div>
        </div>
      )}

      {/* Source bar */}
      {isCompleted && <SourceBar bySource={cycle.results_by_source} />}

      {/* Stats row */}
      {isCompleted && (
        <div className="curiosity-stats-row">
          <span className="curiosity-stat">
            <span className="curiosity-stat-n">{cycle.total_found}</span> found
          </span>
          <span className="curiosity-stat-sep">·</span>
          <span className="curiosity-stat">
            <span className="curiosity-stat-n" style={{ color: '#4ade80' }}>{cycle.total_stored}</span> stored
          </span>
          <span className="curiosity-stat-sep">·</span>
          <span className="curiosity-stat">
            <span className="curiosity-stat-n" style={{ color: '#94a3b8' }}>{cycle.total_deduped}</span> deduped
          </span>
        </div>
      )}

      {/* Findings accordion */}
      {isCompleted && <FindingsAccordion findings={cycle.findings} />}
    </div>
  )
}

// ── Stats Header ──────────────────────────────────────────────────────────

function StatsHeader({
  data,
  onTrigger,
  triggering,
}: {
  data: CuriosityActivity
  onTrigger: () => void
  triggering: boolean
}) {
  const { stats, is_running } = data
  return (
    <div className="curiosity-stats-header">
      <div className="curiosity-stat-cards">
        <div className="curiosity-stat-card">
          <div className="curiosity-stat-card-label">Cycles run</div>
          <div className="curiosity-stat-card-value">{stats.total_cycles}</div>
        </div>
        <div className="curiosity-stat-card">
          <div className="curiosity-stat-card-label">Completed</div>
          <div className="curiosity-stat-card-value" style={{ color: '#4ade80' }}>{stats.completed}</div>
        </div>
        <div className="curiosity-stat-card">
          <div className="curiosity-stat-card-label">Skipped</div>
          <div className="curiosity-stat-card-value" style={{ color: '#94a3b8' }}>{stats.skipped}</div>
        </div>
        <div className="curiosity-stat-card">
          <div className="curiosity-stat-card-label">Memories stored</div>
          <div className="curiosity-stat-card-value" style={{ color: '#a78bfa' }}>{stats.total_stored}</div>
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        {/* Status pill */}
        <div className="curiosity-status-pill" data-running={is_running}>
          <span
            className="curiosity-status-dot"
            style={{
              background: is_running ? '#22d3ee' : '#334155',
              boxShadow: is_running ? '0 0 8px #22d3ee' : 'none',
            }}
          />
          <span style={{ fontSize: 11, color: is_running ? '#22d3ee' : '#64748b' }}>
            {is_running ? 'Running…' : 'Idle'}
          </span>
        </div>

        {/* Trigger button */}
        <button
          className="curiosity-trigger-btn"
          onClick={onTrigger}
          disabled={triggering || is_running}
          title="Manually trigger a curiosity cycle"
        >
          {triggering || is_running ? (
            <span className="curiosity-spinner" />
          ) : (
            '⚡'
          )}
          {triggering ? 'Running…' : 'Trigger Cycle'}
        </button>
      </div>
    </div>
  )
}

// ── Recently Searched ─────────────────────────────────────────────────────

function RecentlySearched({ topics }: { topics: string[] }) {
  if (topics.length === 0) return null
  return (
    <div className="curiosity-recently-searched">
      <div style={{ fontSize: 10, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 6 }}>
        Recently searched (cache)
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
        {topics.map((t) => (
          <span key={t} className="curiosity-topic-pill curiosity-topic-pill--recent">{t}</span>
        ))}
      </div>
    </div>
  )
}

// ── Source Legend ─────────────────────────────────────────────────────────

function SourceLegend() {
  return (
    <div className="curiosity-legend-row">
      {Object.entries(SOURCE_META).map(([key, meta]) => (
        <span key={key} className="curiosity-legend-item">
          <span style={{ color: meta.color }}>■</span> {meta.label}
        </span>
      ))}
    </div>
  )
}

// ── Main Panel ────────────────────────────────────────────────────────────

export default function CuriosityPanel() {
  const [data, setData] = useState<CuriosityActivity | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [triggering, setTriggering] = useState(false)
  const [triggerMsg, setTriggerMsg] = useState<string | null>(null)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const load = useCallback(async () => {
    try {
      const result = await fetchCuriosityActivity(60)
      setData(result)
      setError(null)
    } catch (e) {
      setError(String(e))
    }
  }, [])

  useEffect(() => {
    load()
    intervalRef.current = setInterval(load, POLL_INTERVAL_MS)
    return () => { if (intervalRef.current) clearInterval(intervalRef.current) }
  }, [load])

  const handleTrigger = async () => {
    setTriggering(true)
    setTriggerMsg(null)
    try {
      const r = await triggerCuriosityCycle()
      setTriggerMsg(r.stored > 0 ? `✓ Stored ${r.stored} new memories` : '↷ Cycle complete (0 new)')
      await load()
    } catch (e) {
      setTriggerMsg(`✗ ${e}`)
    } finally {
      setTriggering(false)
    }
  }

  return (
    <div className="curiosity-panel">
      {/* Title bar */}
      <div className="curiosity-title-bar">
        <span className="curiosity-title">
          <span style={{ color: '#22d3ee' }}>◈</span> Curiosity Engine
        </span>
        <span className="curiosity-subtitle">
          Autonomous idle-time knowledge acquisition
        </span>
        <SourceLegend />
      </div>

      {error && (
        <div className="curiosity-error">{error}</div>
      )}

      {triggerMsg && (
        <div className="curiosity-trigger-msg" data-ok={!triggerMsg.startsWith('✗')}>
          {triggerMsg}
        </div>
      )}

      {data ? (
        <>
          <StatsHeader data={data} onTrigger={handleTrigger} triggering={triggering} />
          <RecentlySearched topics={data.recently_searched} />

          {/* Cycle timeline */}
          <div className="curiosity-timeline-label">
            Activity Timeline
            <span style={{ marginLeft: 8, color: '#334155', fontWeight: 400 }}>
              ({data.cycles.length} record{data.cycles.length !== 1 ? 's' : ''})
            </span>
          </div>

          {data.cycles.length === 0 ? (
            <div className="curiosity-empty">
              No curiosity cycles recorded yet.<br />
              Cycles run automatically when ECHO is idle, or trigger one manually above.
            </div>
          ) : (
            <div className="curiosity-feed">
              {data.cycles.map((cycle) => (
                <CycleCard key={cycle.id} cycle={cycle} />
              ))}
            </div>
          )}
        </>
      ) : (
        <div className="curiosity-loading">
          <span className="curiosity-spinner" /> Loading curiosity data…
        </div>
      )}
    </div>
  )
}
