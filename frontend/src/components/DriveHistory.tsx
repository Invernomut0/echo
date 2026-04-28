import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend
} from 'recharts'
import type { HistoryPoint } from '../api'

interface Props {
  history: HistoryPoint[]
}

const COLORS: Record<string, string> = {
  coherence:   '#06b6d4',
  curiosity:   '#a78bfa',
  stability:   '#10b981',
  competence:  '#f59e0b',
  compression: '#f43f5e',
}

export default function DriveHistory({ history }: Props) {
  if (history.length === 0) {
    return (
      <div style={{ color: '#475569', fontSize: 11, textAlign: 'center', padding: 16 }}>
        No history yet
      </div>
    )
  }

  const data = history.map((h) => ({
    t: new Date(h.timestamp).toLocaleTimeString(),
    ...Object.fromEntries(
      Object.entries(h.drives).map(([k, v]) => [k, Math.round(v * 100)])
    ),
  }))

  return (
    <ResponsiveContainer width="100%" height={140}>
      <LineChart data={data}>
        <XAxis dataKey="t" hide />
        <YAxis domain={[0, 100]} hide />
        <Tooltip
          contentStyle={{
            background: '#161b27',
            border: '1px solid #1e293b',
            borderRadius: 6,
            fontSize: 10,
            color: '#e2e8f0',
          }}
          formatter={(v: number) => [`${v}%`]}
        />
        {Object.entries(COLORS).map(([key, color]) => (
          <Line
            key={key}
            type="monotone"
            dataKey={key}
            stroke={color}
            dot={false}
            strokeWidth={1.5}
            strokeOpacity={0.8}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  )
}
