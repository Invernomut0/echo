import type { MemoryItem } from '../api'

interface Props {
  memories: MemoryItem[]
  total: number
}

export default function MemoryPanel({ memories, total }: Props) {
  return (
    <div style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: 12, overflow: 'hidden', flex: 1 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontSize: 11, color: '#94a3b8' }}>
          Showing {memories.length} of {total} memories
        </span>
      </div>
      <div className="memory-list">
        {memories.length === 0 && (
          <div style={{ color: '#475569', fontSize: 11, textAlign: 'center', paddingTop: 24 }}>
            No memories stored yet
          </div>
        )}
        {memories.map((mem) => (
          <div key={mem.id} className="memory-card">
            <div className="memory-card-header">
              <span className={`memory-type-badge ${mem.memory_type}`}>{mem.memory_type}</span>
              <span className="memory-salience">s={mem.salience.toFixed(2)}</span>
            </div>
            <div className="memory-content">{mem.content}</div>
            <div className="memory-strength-bar">
              <div
                className="memory-strength-fill"
                style={{ width: `${Math.round(mem.current_strength * 100)}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
