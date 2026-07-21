/**
 * PlasticityPanel — visualise how ECHO's agent routing weights evolve over time.
 *
 * Two views:
 *  1. Current weights — horizontal bar chart, one bar per agent.
 *     Neutral = 1.0 (grey baseline), above = green, below = amber.
 *  2. Weight history — line chart showing each agent's weight trajectory.
 *
 * Data source: GET /api/state and GET /api/state/history
 * Both are already available with no new backend code.
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  ReferenceLine, Legend,
} from 'recharts'

// ── Types ────────────────────────────────────────────────────────────────────

interface AgentWeights { [agent: string]: number }

interface HistoryPoint {
  timestamp: string
  agent_weights: AgentWeights
}

interface StateResponse {
  meta_state: { agent_weights: AgentWeights }
}

// ── Constants ────────────────────────────────────────────────────────────────

const AGENT_COLORS: Record<string, string> = {
  analyst:      '#06b6d4',
  explorer:     '#a78bfa',
  skeptic:      '#f43f5e',
  archivist:    '#10b981',
  social_self:  '#f59e0b',
  planner:      '#3b82f6',
  orchestrator: '#e879f9',
}

const AGENT_LABELS: Record<string, string> = {
  analyst:      'Analyst',
  explorer:     'Explorer',
  skeptic:      'Skeptic',
  archivist:    'Archivist',
  social_self:  'Social',
  planner:      'Planner',
  orchestrator: 'Orchestrator',
}

const AGENT_DESC: Record<string, string> = {
  analyst:      'Logical analysis and pattern recognition',
  explorer:     'Curiosity-driven exploration of new ideas',
  skeptic:      'Critical thinking and coherence checking',
  archivist:    'Memory retrieval and knowledge preservation',
  social_self:  'Interpersonal awareness and empathy',
  planner:      'Goal-oriented planning and action sequencing',
  orchestrator: 'Meta-coordination of all agents',
}

const NEUTRAL = 1.0
const WEIGHT_MIN = 0.1
const WEIGHT_MAX = 2.0

// ── Helpers ──────────────────────────────────────────────────────────────────

function barColor(w: number): string {
  if (w > NEUTRAL + 0.15) return '#10b981'   // boosted → green
  if (w < NEUTRAL - 0.15) return '#f59e0b'   // reduced → amber
  return '#6b7280'                            // neutral → grey
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  } catch {
    return iso
  }
}

function pct(w: number): number {
  // Map [WEIGHT_MIN, WEIGHT_MAX] → [0, 100] for bar width
  return Math.round(((w - WEIGHT_MIN) / (WEIGHT_MAX - WEIGHT_MIN)) * 100)
}

// ── Custom tooltip for line chart ────────────────────────────────────────────

function WeightTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  return (
    <div className="plast-tooltip">
      <div className="plast-tooltip-time">{label}</div>
      {payload.map((p: any) => (
        <div key={p.dataKey} className="plast-tooltip-row">
          <span className="plast-tooltip-dot" style={{ background: p.color }} />
          <span className="plast-tooltip-name">{AGENT_LABELS[p.dataKey] ?? p.dataKey}</span>
          <span className="plast-tooltip-val">{Number(p.value).toFixed(3)}</span>
        </div>
      ))}
    </div>
  )
}

// ── Main Component ───────────────────────────────────────────────────────────

export default function PlasticityPanel() {
  const [weights, setWeights] = useState<AgentWeights>({})
  const [history, setHistory] = useState<HistoryPoint[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdated, setLastUpdated] = useState<string | null>(null)
  const [historyLimit, setHistoryLimit] = useState(60)
  const [hiddenAgents, setHiddenAgents] = useState<Set<string>>(new Set())
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const load = useCallback(async (limit = historyLimit) => {
    setLoading(true)
    setError(null)
    try {
      const [stateRes, histRes] = await Promise.all([
        fetch('/api/state'),
        fetch(`/api/state/history?limit=${limit}`),
      ])
      if (!stateRes.ok) throw new Error(`state: HTTP ${stateRes.status}`)
      if (!histRes.ok) throw new Error(`history: HTTP ${histRes.status}`)

      const state: StateResponse = await stateRes.json()
      const hist: HistoryPoint[] = await histRes.json()

      setWeights(state.meta_state?.agent_weights ?? {})
      setHistory(hist)
      setLastUpdated(new Date().toLocaleTimeString())
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }, [historyLimit])

  useEffect(() => {
    load()
    intervalRef.current = setInterval(() => load(), 15_000)
    return () => { if (intervalRef.current) clearInterval(intervalRef.current) }
  }, [load])

  const toggleAgent = (agent: string) => {
    setHiddenAgents(prev => {
      const next = new Set(prev)
      next.has(agent) ? next.delete(agent) : next.add(agent)
      return next
    })
  }

  // Sort agents by current weight descending for bar chart
  const sortedAgents = Object.entries(weights).sort((a, b) => b[1] - a[1])

  // Prepare line chart data: each point has timestamp + one key per agent
  const lineData = history.map(h => ({
    t: formatTime(h.timestamp),
    ...Object.fromEntries(
      Object.entries(h.agent_weights ?? {}).map(([k, v]) => [k, +v.toFixed(4)])
    ),
  }))

  // All agents seen across history
  const allAgents = Array.from(
    new Set([
      ...Object.keys(weights),
      ...history.flatMap(h => Object.keys(h.agent_weights ?? {})),
    ])
  )

  return (
    <div className="plast-panel">
      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <div className="plast-header">
        <div>
          <div className="plast-title">Plasticity</div>
          <div className="plast-subtitle">Agent routing weight evolution</div>
        </div>
        <div className="plast-actions">
          {lastUpdated && <span className="plast-ts">updated {lastUpdated}</span>}
          <select
            className="plast-select"
            value={historyLimit}
            onChange={e => setHistoryLimit(Number(e.target.value))}
          >
            <option value={20}>20 pts</option>
            <option value={60}>60 pts</option>
            <option value={120}>120 pts</option>
            <option value={200}>200 pts</option>
          </select>
          <button className="plast-btn" onClick={() => load()} disabled={loading}>
            {loading ? '…' : '↻'}
          </button>
        </div>
      </div>

      {error && <div className="plast-error">{error}</div>}

      {/* ── Current weights bar chart ───────────────────────────────────────── */}
      <div className="plast-section">
        <div className="plast-section-title">Current weights</div>
        <div className="plast-bar-legend">
          <span className="plast-legend-item plast-legend-boosted">▲ boosted (&gt;1.15)</span>
          <span className="plast-legend-item plast-legend-neutral">● neutral (≈1.0)</span>
          <span className="plast-legend-item plast-legend-reduced">▼ reduced (&lt;0.85)</span>
        </div>

        <div className="plast-bars">
          {sortedAgents.map(([agent, w]) => (
            <div key={agent} className="plast-bar-row">
              <div className="plast-bar-label">
                <span
                  className="plast-bar-dot"
                  style={{ background: AGENT_COLORS[agent] ?? '#888' }}
                />
                <span className="plast-bar-name">{AGENT_LABELS[agent] ?? agent}</span>
                <span className="plast-bar-desc">{AGENT_DESC[agent] ?? ''}</span>
              </div>
              <div className="plast-bar-track">
                {/* Neutral reference line at 50% */}
                <div className="plast-bar-neutral-line" />
                <div
                  className="plast-bar-fill"
                  style={{
                    width: `${pct(w)}%`,
                    background: barColor(w),
                  }}
                />
              </div>
              <div className="plast-bar-value" style={{ color: barColor(w) }}>
                {w.toFixed(3)}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Weight history line chart ───────────────────────────────────────── */}
      <div className="plast-section plast-section--chart">
        <div className="plast-section-header">
          <div className="plast-section-title">Weight history</div>
          <div className="plast-agent-toggles">
            {allAgents.map(agent => (
              <button
                key={agent}
                className={`plast-agent-toggle${hiddenAgents.has(agent) ? ' hidden' : ''}`}
                style={{ '--agent-color': AGENT_COLORS[agent] ?? '#888' } as React.CSSProperties}
                onClick={() => toggleAgent(agent)}
                title={AGENT_DESC[agent]}
              >
                {AGENT_LABELS[agent] ?? agent}
              </button>
            ))}
          </div>
        </div>

        {lineData.length === 0 ? (
          <div className="plast-empty">No history available yet.</div>
        ) : (
          <div className="plast-chart-wrap">
            <ResponsiveContainer width="100%" height={280}>
              <LineChart data={lineData} margin={{ top: 8, right: 12, bottom: 0, left: -10 }}>
                <XAxis
                  dataKey="t"
                  tick={{ fill: 'rgba(196,181,253,0.45)', fontSize: 10 }}
                  interval="preserveStartEnd"
                />
                <YAxis
                  domain={[WEIGHT_MIN, WEIGHT_MAX]}
                  tick={{ fill: 'rgba(196,181,253,0.45)', fontSize: 10 }}
                  tickCount={6}
                />
                <Tooltip content={<WeightTooltip />} />
                <ReferenceLine
                  y={NEUTRAL}
                  stroke="rgba(255,255,255,0.12)"
                  strokeDasharray="4 3"
                  label={{ value: 'neutral', fill: 'rgba(255,255,255,0.2)', fontSize: 9, position: 'right' }}
                />
                {allAgents
                  .filter(a => !hiddenAgents.has(a))
                  .map(agent => (
                    <Line
                      key={agent}
                      type="monotone"
                      dataKey={agent}
                      stroke={AGENT_COLORS[agent] ?? '#888'}
                      strokeWidth={1.5}
                      dot={false}
                      isAnimationActive={false}
                    />
                  ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* ── How plasticity works ────────────────────────────────────────────── */}
      <details className="plast-explainer">
        <summary className="plast-explainer-summary">How plasticity works</summary>
        <div className="plast-explainer-body">
          <p>
            ECHO adjusts agent routing weights in two ways:
          </p>
          <ul>
            <li>
              <strong>Reactive (per interaction)</strong> — <code>PlasticityAdapter</code> shifts
              weights immediately based on drive levels: high curiosity boosts Explorer, low coherence
              boosts Skeptic and Analyst, low stability boosts Archivist, low competence boosts Planner.
              Changes are modulated by <em>prediction error</em> — surprises cause larger updates.
            </li>
            <li>
              <strong>Evolutionary (dream phase)</strong> — <code>WeightEvolution</code> generates
              N_CANDIDATES random weight variants during consolidation, scores each by
              <em>F(w) = Σ w[agent] × salience × strength</em> across seed memories,
              and keeps the fittest variant. This models sleep-based synaptic consolidation.
            </li>
            <li>
              <strong>Decay</strong> — all weights are gently pulled toward 1.0 each cycle
              (rate = 0.005) to prevent monotonic drift and preserve cognitive diversity.
            </li>
          </ul>
          <p>Neutral weight = <strong>1.0</strong> · Min = 0.1 · Max = 2.0</p>
        </div>
      </details>
    </div>
  )
}
