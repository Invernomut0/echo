import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import type { DriveScores } from '../api'

interface Props {
  drives: DriveScores
}

const DRIVE_COLORS: Record<string, string> = {
  coherence:   '#06b6d4',
  curiosity:   '#a78bfa',
  stability:   '#10b981',
  competence:  '#f59e0b',
  compression: '#f43f5e',
}

const DRIVE_LABELS: Record<string, string> = {
  coherence:   'Coherence',
  curiosity:   'Curiosity',
  stability:   'Stability',
  competence:  'Competence',
  compression: 'Compression',
}

export default function DriveChart({ drives }: Props) {
  const data = Object.entries(DRIVE_LABELS).map(([key, label]) => ({
    name: label.slice(0, 4),
    value: Math.round((drives[key as keyof DriveScores] as number) * 100),
    color: DRIVE_COLORS[key],
  }))

  return (
    <ResponsiveContainer width="100%" height={110}>
      <BarChart data={data} barCategoryGap="20%">
        <XAxis
          dataKey="name"
          tick={{ fill: '#475569', fontSize: 9 }}
          axisLine={false}
          tickLine={false}
        />
        <YAxis domain={[0, 100]} hide />
        <Tooltip
          cursor={{ fill: 'rgba(255,255,255,0.03)' }}
          contentStyle={{
            background: '#161b27',
            border: '1px solid #1e293b',
            borderRadius: 6,
            fontSize: 11,
            color: '#e2e8f0',
          }}
          formatter={(v: number) => [`${v}%`, 'Drive']}
        />
        <Bar dataKey="value" radius={[3, 3, 0, 0]}>
          {data.map((entry, i) => (
            <Cell key={i} fill={entry.color} fillOpacity={0.8} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
