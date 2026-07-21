/**
 * PlasticityPanel — visualise how ECHO's agent routing weights evolve over time,
 * plus the thermodynamic metrics (free energy, temperature, entropy) introduced
 * by the Boltzmann plasticity framework.
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  ReferenceLine,
} from 'recharts'

// ── Types ────────────────────────────────────────────────────────────────────

interface AgentWeights { [agent: string]: number }

interface HistoryPoint {
  timestamp: string
  agent_weights: AgentWeights
  free_energy?: number
  temperature?: number
  internal_energy?: number
  entropy?: number
}

interface StateResponse {
  meta_state: {
    agent_weights: AgentWeights
    arousal: number
    drives: { stability: number; coherence: number; curiosity: number; competence: number; compression: number }
    emotional_valence: number
  }
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
                <div className="plast-bar-label-top">
                  <span
                    className="plast-bar-dot"
                    style={{ background: AGENT_COLORS[agent] ?? '#888' }}
                  />
                  <span className="plast-bar-name">{AGENT_LABELS[agent] ?? agent}</span>
                </div>
                <div className="plast-bar-desc">{AGENT_DESC[agent] ?? ''}</div>
                <div className="plast-bar-track">
                  <div className="plast-bar-neutral-line" />
                  <div
                    className="plast-bar-fill"
                    style={{ width: `${pct(w)}%`, background: barColor(w) }}
                  />
                </div>
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

      {/* ── Thermodynamic metrics ───────────────────────────────────────────── */}
      {history.some(h => h.free_energy !== undefined) && (() => {
        const thermoData = history.map(h => ({
          t:  formatTime(h.timestamp),
          F:  h.free_energy   !== undefined ? +h.free_energy.toFixed(4)   : null,
          T:  h.temperature   !== undefined ? +h.temperature.toFixed(3)   : null,
          U:  h.internal_energy !== undefined ? +h.internal_energy.toFixed(4) : null,
          S:  h.entropy       !== undefined ? +h.entropy.toFixed(3)       : null,
        }))
        const latest = history[history.length - 1]
        return (
          <div className="plast-section plast-thermo">
            <div className="plast-section-title">Thermodynamic state</div>

            {/* Scalar badges */}
            <div className="plast-thermo-badges">
              <div className="plast-thermo-badge">
                <span className="plast-thermo-label">Free energy F</span>
                <span className="plast-thermo-value" style={{ color: '#f43f5e' }}>
                  {latest?.free_energy?.toFixed(4) ?? '—'}
                </span>
                <span className="plast-thermo-unit">F = U − T·S</span>
              </div>
              <div className="plast-thermo-badge">
                <span className="plast-thermo-label">Temperature T</span>
                <span className="plast-thermo-value" style={{ color: '#f59e0b' }}>
                  {latest?.temperature?.toFixed(3) ?? '—'}
                </span>
                <span className="plast-thermo-unit">arousal · (in)stability</span>
              </div>
              <div className="plast-thermo-badge">
                <span className="plast-thermo-label">Internal energy U</span>
                <span className="plast-thermo-value" style={{ color: '#ef4444' }}>
                  {latest?.internal_energy?.toFixed(4) ?? '—'}
                </span>
                <span className="plast-thermo-unit">drive dissonance</span>
              </div>
              <div className="plast-thermo-badge">
                <span className="plast-thermo-label">Entropy S</span>
                <span className="plast-thermo-value" style={{ color: '#10b981' }}>
                  {latest?.entropy?.toFixed(3) ?? '—'}
                </span>
                <span className="plast-thermo-unit">weight diversity</span>
              </div>
            </div>

            {/* Free energy + temperature history */}
            <div className="plast-thermo-chart-label">F, T, U, S history</div>
            <div className="plast-chart-wrap">
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={thermoData} margin={{ top: 4, right: 12, bottom: 0, left: -10 }}>
                  <XAxis dataKey="t" tick={{ fill: 'rgba(196,181,253,0.4)', fontSize: 10 }} interval="preserveStartEnd" />
                  <YAxis tick={{ fill: 'rgba(196,181,253,0.4)', fontSize: 10 }} tickCount={5} />
                  <Tooltip
                    contentStyle={{ background: 'rgba(15,10,30,0.92)', border: '1px solid rgba(139,92,246,0.35)', borderRadius: 8, fontSize: 12 }}
                    labelStyle={{ color: 'rgba(196,181,253,0.5)' }}
                  />
                  <ReferenceLine y={0} stroke="rgba(255,255,255,0.12)" strokeDasharray="4 3" />
                  <Line type="monotone" dataKey="F" stroke="#f43f5e" strokeWidth={2} dot={false} name="F (free energy)" isAnimationActive={false} connectNulls />
                  <Line type="monotone" dataKey="T" stroke="#f59e0b" strokeWidth={1.5} dot={false} name="T (temperature)" isAnimationActive={false} connectNulls />
                  <Line type="monotone" dataKey="U" stroke="#ef4444" strokeWidth={1} dot={false} strokeDasharray="3 2" name="U (energy)" isAnimationActive={false} connectNulls />
                  <Line type="monotone" dataKey="S" stroke="#10b981" strokeWidth={1} dot={false} strokeDasharray="3 2" name="S (entropy)" isAnimationActive={false} connectNulls />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        )
      })()}

      {/* ── How plasticity works ────────────────────────────────────────────── */}
      <details className="plast-explainer">
        <summary className="plast-explainer-summary">How plasticity works — Boltzmann edition</summary>
        <div className="plast-explainer-body">
          <p>
            ECHO now uses a <strong>thermodynamic framework</strong> inspired by Boltzmann autoregressive
            generators and the Free Energy Principle (Friston):
          </p>
          <ul>
            <li>
              <strong>Cognitive free energy</strong> F = U − T·S, where U = drive dissonance (MSE from
              homeostatic setpoints), S = Shannon entropy of agent weights, T = arousal × instability.
              <em>Minimising F simultaneously reduces cognitive disorder and preserves diversity.</em>
            </li>
            <li>
              <strong>Metropolis–Hastings plasticity</strong> — each weight change δ is accepted
              unconditionally if ΔF ≤ 0; otherwise with probability exp(−ΔF/T).
              At high T (aroused, unstable) the system accepts surprises freely.
              At low T (calm, stable) it crystallises into its ground state.
            </li>
            <li>
              <strong>Boltzmann dream selection</strong> — during consolidation, weight candidates
              are sampled proportionally to exp(−energy/T) instead of pure greedy selection.
              High T → diverse dreaming. Low T → convergence.
            </li>
            <li>
              <strong>Thermodynamic consolidation</strong> — memory consolidation is a "cooling"
              process: at high T diverse memories are accepted; as T falls only the most coherent
              representations survive (free-energy minima = stable self-model).
            </li>
          </ul>
          <p>Neutral weight = <strong>1.0</strong> · Min = 0.1 · Max = 2.0</p>
        </div>
      </details>
    </div>
  )
}
