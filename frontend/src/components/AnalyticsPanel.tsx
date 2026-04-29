/**
 * AnalyticsPanel — sezione grafici di dettaglio degli stati interni di ECHO.
 *
 * Sezioni:
 *  1. Badge di riepilogo (valori live)
 *  2. Drive Cognitivi   — 5 linee 0–100% nel tempo
 *  3. Umore Emotivo     — valenza normalizzata + arousal
 *  4. Autocoscienza     — motivazione totale M = Σ wᵢ·dᵢ
 *  5. Plasticità        — pesi learnable dei drive (0–1)
 *  6. Routing Agenti    — pesi orchestratore per agente (0.1–2.0)
 */

import { useMemo } from 'react'
import {
  LineChart,
  Line,
  AreaChart,
  Area,
  ComposedChart,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Legend,
  ReferenceLine,
  CartesianGrid,
} from 'recharts'
import type { HistoryPoint } from '../api'

// ── palette ──────────────────────────────────────────────────────────────────

const DRIVE_COLORS: Record<string, string> = {
  coherence:   '#06b6d4',
  curiosity:   '#a78bfa',
  stability:   '#10b981',
  competence:  '#f59e0b',
  compression: '#f43f5e',
}

const DRIVE_LABELS: Record<string, string> = {
  coherence:   'Coerenza',
  curiosity:   'Curiosità',
  stability:   'Stabilità',
  competence:  'Competenza',
  compression: 'Compressione',
}

const AGENT_COLORS: Record<string, string> = {
  analyst:      '#06b6d4',
  explorer:     '#a78bfa',
  skeptic:      '#f43f5e',
  archivist:    '#10b981',
  social_self:  '#f59e0b',
  planner:      '#8b5cf6',
  orchestrator: '#94a3b8',
}

const AGENT_LABELS: Record<string, string> = {
  analyst:      'Analyst',
  explorer:     'Explorer',
  skeptic:      'Skeptic',
  archivist:    'Archivist',
  social_self:  'Social Self',
  planner:      'Planner',
  orchestrator: 'Orchestrator',
}

// ── helpers ───────────────────────────────────────────────────────────────────

function fmt(ts: string): string {
  return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

const TIP: React.CSSProperties = {
  background: '#0d1117',
  border: '1px solid #1e2a3a',
  borderRadius: 8,
  fontSize: 11,
  color: '#e2e8f0',
  padding: '6px 10px',
}

function Grid() {
  return (
    <CartesianGrid
      strokeDasharray="2 5"
      stroke="#1e2a3a"
      strokeOpacity={0.45}
    />
  )
}

// ── sub-components ─────────────────────────────────────────────────────────────

interface CardProps {
  title: string
  sub: string
  full?: boolean
  height?: number
  children: React.ReactNode
}

function Card({ title, sub, full, height = 190, children }: CardProps) {
  return (
    <div className={`an-card${full ? ' an-card--full' : ''}`}>
      <div className="an-card-head">
        <span className="an-card-title">{title}</span>
        <span className="an-card-sub">{sub}</span>
      </div>
      <div style={{ height }}>{children}</div>
    </div>
  )
}

interface BadgeProps {
  label: string
  value: string | number
  color: string
}

function Badge({ label, value, color }: BadgeProps) {
  return (
    <div className="an-badge">
      <span className="an-badge-label">{label}</span>
      <span className="an-badge-value" style={{ color }}>{value}</span>
    </div>
  )
}

// ── main component ─────────────────────────────────────────────────────────────

interface Props {
  history: HistoryPoint[]
}

export default function AnalyticsPanel({ history }: Props) {
  const last = history.length > 0 ? history[history.length - 1] : null

  // Drive data: valori 0-100 + motivazione totale
  const driveData = useMemo(() =>
    history.map(h => ({
      t: fmt(h.timestamp),
      ...Object.fromEntries(
        Object.keys(DRIVE_COLORS).map(k => [k, Math.round((h.drives[k] ?? 0) * 100)])
      ),
      motivation: Math.round((h.total_motivation ?? 0.5) * 100),
    })),
    [history]
  )

  // Mood: valenza normalizzata 0-100 (neutro=50) + arousal 0-100
  const moodData = useMemo(() =>
    history.map(h => ({
      t: fmt(h.timestamp),
      valenza: Math.round(((h.emotional_valence + 1) / 2) * 100),
      arousal: Math.round((h.arousal ?? 0.5) * 100),
      _rawValence: h.emotional_valence,
    })),
    [history]
  )

  // Plasticità: pesi learnable dei drive (0-1)
  const plasticityData = useMemo(() =>
    history.map(h => {
      const w = h.drive_weights ?? {}
      return {
        t: fmt(h.timestamp),
        ...Object.fromEntries(
          Object.keys(DRIVE_COLORS).map(k => [`w_${k}`, +(w[k] ?? 0.2).toFixed(3)])
        ),
      }
    }),
    [history]
  )

  // Agent weights: pesi routing orchestratore
  const agentData = useMemo(() =>
    history.map(h => {
      const aw = h.agent_weights ?? {}
      return {
        t: fmt(h.timestamp),
        ...Object.fromEntries(
          Object.keys(AGENT_COLORS).map(k => [k, +(aw[k] ?? 1.0).toFixed(3)])
        ),
      }
    }),
    [history]
  )

  // ── empty state ─────────────────────────────────────────────────────────────
  if (history.length === 0) {
    return (
      <div className="an-empty">
        <div className="an-empty-icon">◈</div>
        <div className="an-empty-title">Nessuna storia disponibile</div>
        <div className="an-empty-sub">I grafici appariranno dopo la prima interazione</div>
      </div>
    )
  }

  // ── render ──────────────────────────────────────────────────────────────────
  return (
    <div className="an-panel">

      {/* ── Badge riepilogo ── */}
      {last && (
        <div className="an-summary">
          <Badge
            label="Motivazione"
            value={(last.total_motivation ?? 0.5).toFixed(2)}
            color="#a78bfa"
          />
          <Badge
            label="Valenza"
            value={
              last.emotional_valence >= 0
                ? `+${last.emotional_valence.toFixed(2)}`
                : last.emotional_valence.toFixed(2)
            }
            color={last.emotional_valence >= 0 ? '#10b981' : '#f43f5e'}
          />
          <Badge
            label="Arousal"
            value={`${Math.round((last.arousal ?? 0.5) * 100)}%`}
            color="#f59e0b"
          />
          <Badge
            label="Coerenza"
            value={`${Math.round(last.drives.coherence * 100)}%`}
            color="#06b6d4"
          />
          <Badge
            label="Curiosità"
            value={`${Math.round(last.drives.curiosity * 100)}%`}
            color="#a78bfa"
          />
          <Badge
            label="Stabilità"
            value={`${Math.round(last.drives.stability * 100)}%`}
            color="#10b981"
          />
          <Badge
            label="Competenza"
            value={`${Math.round(last.drives.competence * 100)}%`}
            color="#f59e0b"
          />
          <Badge
            label="Compressione"
            value={`${Math.round(last.drives.compression * 100)}%`}
            color="#f43f5e"
          />
        </div>
      )}

      <div className="an-grid">

        {/* ── 1. Drive Cognitivi (full width) ── */}
        <Card title="Drive Cognitivi" sub="Evoluzione nel tempo (0 – 100%)" full>
          <ResponsiveContainer width="100%" height={190}>
            <LineChart data={driveData} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
              <Grid />
              <XAxis
                dataKey="t"
                tick={{ fill: '#475569', fontSize: 9 }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                domain={[0, 100]}
                width={28}
                tick={{ fill: '#475569', fontSize: 9 }}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip
                contentStyle={TIP}
                formatter={(v: number, name: string) => [`${v}%`, DRIVE_LABELS[name] ?? name]}
              />
              <Legend
                iconSize={10}
                wrapperStyle={{ fontSize: 10, paddingTop: 6 }}
                formatter={(v: string) => DRIVE_LABELS[v] ?? v}
              />
              {Object.entries(DRIVE_COLORS).map(([k, c]) => (
                <Line
                  key={k}
                  type="monotone"
                  dataKey={k}
                  stroke={c}
                  dot={false}
                  strokeWidth={1.8}
                  name={k}
                  activeDot={{ r: 3 }}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </Card>

        {/* ── 2. Umore Emotivo ── */}
        <Card title="Umore Emotivo" sub="Valenza (norm. 0-100, neutro=50) · Arousal (0-100%)">
          <ResponsiveContainer width="100%" height={190}>
            <ComposedChart data={moodData} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id="aroGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#f59e0b" stopOpacity={0.25} />
                  <stop offset="95%" stopColor="#f59e0b" stopOpacity={0.0}  />
                </linearGradient>
                <linearGradient id="valGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#10b981" stopOpacity={0.2} />
                  <stop offset="95%" stopColor="#10b981" stopOpacity={0.0} />
                </linearGradient>
              </defs>
              <Grid />
              <XAxis
                dataKey="t"
                tick={{ fill: '#475569', fontSize: 9 }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                domain={[0, 100]}
                width={28}
                tick={{ fill: '#475569', fontSize: 9 }}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip
                contentStyle={TIP}
                formatter={(v: number, name: string) => {
                  if (name === 'valenza') {
                    const raw = ((v / 50) - 1).toFixed(2)
                    return [raw, 'Valenza']
                  }
                  return [`${v}%`, name === 'arousal' ? 'Arousal' : name]
                }}
              />
              <ReferenceLine
                y={50}
                stroke="#334155"
                strokeDasharray="4 4"
                label={{ value: 'neutro', fill: '#334155', fontSize: 9, position: 'insideTopRight' }}
              />
              <Area
                type="monotone"
                dataKey="arousal"
                stroke="#f59e0b"
                fill="url(#aroGrad)"
                strokeWidth={1.5}
                name="arousal"
                dot={false}
              />
              <Line
                type="monotone"
                dataKey="valenza"
                stroke="#10b981"
                dot={false}
                strokeWidth={2.2}
                name="valenza"
                activeDot={{ r: 3 }}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </Card>

        {/* ── 3. Autocoscienza ── */}
        <Card title="Autocoscienza" sub="Motivazione totale M = Σ wᵢ·dᵢ">
          <ResponsiveContainer width="100%" height={190}>
            <AreaChart data={driveData} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id="motGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#a78bfa" stopOpacity={0.35} />
                  <stop offset="95%" stopColor="#a78bfa" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <Grid />
              <XAxis
                dataKey="t"
                tick={{ fill: '#475569', fontSize: 9 }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                domain={[0, 100]}
                width={28}
                tick={{ fill: '#475569', fontSize: 9 }}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip
                contentStyle={TIP}
                formatter={(v: number) => [`${v}%`, 'Motivazione']}
              />
              <ReferenceLine
                y={50}
                stroke="#334155"
                strokeDasharray="4 4"
                label={{ value: 'base', fill: '#334155', fontSize: 9, position: 'insideTopRight' }}
              />
              <Area
                type="monotone"
                dataKey="motivation"
                stroke="#a78bfa"
                fill="url(#motGrad)"
                strokeWidth={2.5}
                dot={false}
                activeDot={{ r: 3, fill: '#a78bfa' }}
              />
            </AreaChart>
          </ResponsiveContainer>
        </Card>

        {/* ── 4. Plasticità — Pesi Drive (full width) ── */}
        <Card title="Plasticità — Pesi Drive" sub="Adattamento pesi learnable (Σ = 1, init = 0.2)" full>
          <ResponsiveContainer width="100%" height={190}>
            <LineChart data={plasticityData} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
              <Grid />
              <XAxis
                dataKey="t"
                tick={{ fill: '#475569', fontSize: 9 }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                domain={[0, 0.65]}
                width={28}
                tick={{ fill: '#475569', fontSize: 9 }}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip
                contentStyle={TIP}
                formatter={(v: number, name: string) => [
                  v.toFixed(3),
                  DRIVE_LABELS[name.replace('w_', '')] ?? name,
                ]}
              />
              <Legend
                iconSize={10}
                wrapperStyle={{ fontSize: 10, paddingTop: 6 }}
                formatter={(v: string) => DRIVE_LABELS[v.replace('w_', '')] ?? v}
              />
              <ReferenceLine
                y={0.2}
                stroke="#334155"
                strokeDasharray="4 4"
                label={{ value: '0.2 init', fill: '#334155', fontSize: 9, position: 'insideTopRight' }}
              />
              {Object.entries(DRIVE_COLORS).map(([k, c]) => (
                <Line
                  key={k}
                  type="monotone"
                  dataKey={`w_${k}`}
                  stroke={c}
                  dot={false}
                  strokeWidth={1.5}
                  strokeDasharray="5 2"
                  strokeOpacity={0.85}
                  name={`w_${k}`}
                  activeDot={{ r: 3 }}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </Card>

        {/* ── 5. Routing Agenti (full width) ── */}
        <Card
          title="Routing Agenti"
          sub="Peso orchestratore per agente (init = 1.0, range 0.1 – 2.0)"
          full
          height={220}
        >
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={agentData} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
              <Grid />
              <XAxis
                dataKey="t"
                tick={{ fill: '#475569', fontSize: 9 }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                domain={[0, 2.1]}
                width={28}
                tick={{ fill: '#475569', fontSize: 9 }}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip
                contentStyle={TIP}
                formatter={(v: number, name: string) => [
                  v.toFixed(3),
                  AGENT_LABELS[name] ?? name,
                ]}
              />
              <Legend
                iconSize={10}
                wrapperStyle={{ fontSize: 10, paddingTop: 6 }}
                formatter={(v: string) => AGENT_LABELS[v] ?? v}
              />
              <ReferenceLine
                y={1}
                stroke="#334155"
                strokeDasharray="4 4"
                label={{ value: '1.0 base', fill: '#334155', fontSize: 9, position: 'insideTopRight' }}
              />
              {Object.entries(AGENT_COLORS).map(([k, c]) => (
                <Line
                  key={k}
                  type="monotone"
                  dataKey={k}
                  stroke={c}
                  dot={false}
                  strokeWidth={1.8}
                  name={k}
                  activeDot={{ r: 3 }}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </Card>

      </div>
    </div>
  )
}
