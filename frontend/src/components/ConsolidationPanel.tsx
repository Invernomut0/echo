import { useState } from 'react'
import { triggerConsolidation, triggerREM, type ConsolidationReport } from '../api'
import { useDreams, useHeartbeat } from '../hooks'

// ── Helpers ──────────────────────────────────────────────────────────────────

function fmtTime(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function fmtDate(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  const today = new Date()
  if (d.toDateString() === today.toDateString()) return `Today ${fmtTime(iso)}`
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' }) + ' ' + fmtTime(iso)
}

function fmtInterval(secs: number): string {
  if (secs < 3600) return `${secs / 60} min`
  return `${secs / 3600} h`
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function ConsolidationPanel() {
  const [running, setRunning] = useState(false)
  const [remRunning, setRemRunning] = useState(false)
  const [report, setReport] = useState<ConsolidationReport | null>(null)
  const [error, setError] = useState<string | null>(null)

  const heartbeat = useHeartbeat(true)
  const { dreams, loading: dreamsLoading, refresh: refreshDreams } = useDreams(true)

  const trigger = async () => {
    setRunning(true)
    setError(null)
    try {
      const r = await triggerConsolidation()
      setReport(r.report)
    } catch (e) {
      setError(String(e))
    } finally {
      setRunning(false)
    }
  }

  const triggerDream = async () => {
    setRemRunning(true)
    setError(null)
    try {
      await triggerREM()
      refreshDreams()
    } catch (e) {
      setError(String(e))
    } finally {
      setRemRunning(false)
    }
  }

  return (
    <div className="consolidation-panel">

      {/* ── Heartbeat Status ─────────────────────────────────────────────── */}
      <div className="report-card" style={{ marginBottom: 16 }}>
        <div style={{ fontWeight: 600, color: '#e2e8f0', marginBottom: 10, fontSize: 12, letterSpacing: '0.06em' }}>
          Heartbeat Status
        </div>

        {heartbeat ? (
          <>
            {/* Light */}
            <div style={{ marginBottom: 10 }}>
              <div style={{ fontSize: 10, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 4 }}>
                Light ({fmtInterval(heartbeat.light_interval_seconds)})
              </div>
              <div className="report-row">
                <span className="report-key">Last</span>
                <span className="report-val" style={{ color: '#94a3b8' }}>{fmtDate(heartbeat.last_light_at)}</span>
              </div>
              <div className="report-row">
                <span className="report-key">Next</span>
                <span className="report-val" style={{ color: '#38bdf8' }}>{fmtDate(heartbeat.next_light_at)}</span>
              </div>
            </div>

            {/* Deep / REM */}
            <div>
              <div style={{ fontSize: 10, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 4 }}>
                Deep / REM ({fmtInterval(heartbeat.deep_interval_seconds)})
              </div>
              <div className="report-row">
                <span className="report-key">Last</span>
                <span className="report-val" style={{ color: '#94a3b8' }}>{fmtDate(heartbeat.last_deep_at)}</span>
              </div>
              <div className="report-row">
                <span className="report-key">Next</span>
                <span className="report-val" style={{ color: '#a78bfa' }}>{fmtDate(heartbeat.next_deep_at)}</span>
              </div>
              <div className="report-row" style={{ marginTop: 4 }}>
                <span className="report-key">Running</span>
                <span className="report-val" style={{ color: heartbeat.running ? '#4ade80' : '#f43f5e' }}>
                  {heartbeat.running ? '● active' : '○ stopped'}
                </span>
              </div>
            </div>
          </>
        ) : (
          <div style={{ color: '#475569', fontSize: 12 }}>Loading…</div>
        )}
      </div>

      {/* ── Dream Log ────────────────────────────────────────────────────── */}
      <div className="report-card" style={{ marginBottom: 16 }}>
        <div style={{ fontWeight: 600, color: '#e2e8f0', marginBottom: 10, fontSize: 12, letterSpacing: '0.06em' }}>
          Dream Log
        </div>

        {dreamsLoading ? (
          <div style={{ color: '#475569', fontSize: 12 }}>Loading dreams…</div>
        ) : dreams.length === 0 ? (
          <div style={{ color: '#475569', fontSize: 12, fontStyle: 'italic' }}>
            No dreams yet — REM phase hasn't run.
          </div>
        ) : (
          <div style={{ maxHeight: 260, overflowY: 'auto', paddingRight: 4 }}>
            {dreams.map(d => (
              <div key={d.id} style={{
                borderBottom: '1px solid #1e293b',
                padding: '8px 0',
                display: 'flex',
                gap: 10,
                alignItems: 'flex-start',
              }}>
                {/* Badge */}
                <div style={{
                  flexShrink: 0,
                  fontSize: 10,
                  color: '#a78bfa',
                  background: 'rgba(167,139,250,0.08)',
                  border: '1px solid rgba(167,139,250,0.2)',
                  borderRadius: 4,
                  padding: '2px 6px',
                  whiteSpace: 'nowrap',
                  marginTop: 2,
                }}>
                  {fmtTime(d.created_at)}
                </div>

                {/* Dream text */}
                <div style={{ fontSize: 11, color: '#cbd5e1', lineHeight: 1.55 }}>
                  {d.dream}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── Controls ─────────────────────────────────────────────────────── */}
      <div style={{ color: '#94a3b8', fontSize: 11, lineHeight: 1.6, marginBottom: 12 }}>
        Consolidation promotes high-salience episodic memories to semantic and
        autobiographical stores, applies exponential decay, and extracts patterns.
        REM phase additionally generates a dream narrative from recent memories.
      </div>

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
        <button className="trigger-btn" onClick={trigger} disabled={running || remRunning}>
          {running ? 'Running…' : 'Trigger Consolidation'}
        </button>

        <button
          className="trigger-btn"
          onClick={triggerDream}
          disabled={running || remRunning}
          style={{ background: 'rgba(167,139,250,0.12)', borderColor: 'rgba(167,139,250,0.3)', color: '#a78bfa' }}
        >
          {remRunning ? 'Dreaming…' : '✦ Trigger REM Now'}
        </button>
      </div>

      {error && (
        <div style={{ color: '#f43f5e', fontSize: 12, marginBottom: 8 }}>{error}</div>
      )}

      {report && (
        <div className="report-card">
          <div style={{ fontWeight: 600, color: '#e2e8f0', marginBottom: 12, fontSize: 12, letterSpacing: '0.06em' }}>
            Last Report
            {report.finished_at && (
              <span style={{ fontWeight: 400, color: '#475569', marginLeft: 8 }}>
                {fmtDate(report.finished_at)}
              </span>
            )}
          </div>

          {/* ── Memory Processing ── */}
          <div style={{ fontSize: 10, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 6 }}>
            Memory Processing
          </div>
          <div className="report-row">
            <span className="report-key">Processed</span>
            <span className="report-val">{report.memories_processed}</span>
          </div>
          <div className="report-row">
            <span className="report-key">Active</span>
            <span className="report-val">{report.total_active > 0 ? report.total_active : report.memories_processed}</span>
          </div>
          <div className="report-row">
            <span className="report-key">Dormant</span>
            <span className="report-val" style={{ color: report.dormant_count > 0 ? '#94a3b8' : '#475569' }}>
              {report.dormant_count}
            </span>
          </div>
          <div className="report-row">
            <span className="report-key">Avg Salience</span>
            <span className="report-val" style={{ color: '#38bdf8' }}>
              {report.avg_salience > 0 ? report.avg_salience.toFixed(3) : '—'}
            </span>
          </div>

          {/* ── Synaptic Pruning ── */}
          <div style={{ fontSize: 10, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.08em', marginTop: 12, marginBottom: 6 }}>
            Synaptic Pruning (dedup)
          </div>
          <div className="report-row">
            <span className="report-key">Episodic deduped</span>
            <span className="report-val" style={{ color: report.episodic_deduped > 0 ? '#f59e0b' : '#475569' }}>
              {report.episodic_deduped}
            </span>
          </div>
          <div className="report-row">
            <span className="report-key">Semantic deduped</span>
            <span className="report-val" style={{ color: report.semantic_deduped > 0 ? '#f59e0b' : '#475569' }}>
              {report.semantic_deduped}
            </span>
          </div>
          <div className="report-row">
            <span className="report-key">Re-embedded</span>
            <span className="report-val" style={{ color: report.re_embedded > 0 ? '#a78bfa' : '#475569' }}>
              {report.re_embedded}
            </span>
          </div>
          <div className="report-row">
            <span className="report-key">Weak pruned</span>
            <span className="report-val" style={{ color: report.memories_pruned > 0 ? '#f43f5e' : '#475569' }}>
              {report.memories_pruned}
            </span>
          </div>

          {/* ── Knowledge Growth ── */}
          <div style={{ fontSize: 10, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.08em', marginTop: 12, marginBottom: 6 }}>
            Knowledge Growth
          </div>
          <div className="report-row">
            <span className="report-key">Promoted → semantic</span>
            <span className="report-val" style={{ color: report.memories_promoted > 0 ? '#4ade80' : '#475569' }}>
              {report.memories_promoted}
            </span>
          </div>
          <div className="report-row">
            <span className="report-key">Patterns extracted</span>
            <span className="report-val" style={{ color: report.patterns_found.length > 0 ? '#4ade80' : '#475569' }}>
              {report.patterns_found.length}
            </span>
          </div>

          {report.patterns_found.length > 0 && (
            <div style={{ marginTop: 10 }}>
              <div style={{ fontSize: 10, color: '#475569', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                Extracted Patterns
              </div>
              {report.patterns_found.map((p, i) => (
                <div key={i} style={{
                  fontSize: 11,
                  color: '#94a3b8',
                  padding: '4px 0',
                  borderBottom: '1px solid #1e293b',
                  display: 'flex',
                  gap: 6,
                  alignItems: 'flex-start',
                }}>
                  <span style={{ color: '#4ade80', flexShrink: 0 }}>◈</span>
                  <span>{p}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

