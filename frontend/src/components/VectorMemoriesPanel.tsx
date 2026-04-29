import { useState } from 'react'
import { useMemories, useVectorStatus, useSemanticMemories } from '../hooks'
import type { MemoryItem } from '../api'

// ── Helpers ──────────────────────────────────────────────────────────────────

function Badge({ label, color }: { label: string; color: string }) {
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '1px 6px',
        borderRadius: 4,
        fontSize: 11,
        fontWeight: 700,
        letterSpacing: '0.04em',
        background: color,
        color: '#fff',
        marginLeft: 4,
      }}
    >
      {label}
    </span>
  )
}

function StrengthBar({ value, color }: { value: number; color: string }) {
  return (
    <div
      style={{
        height: 4,
        borderRadius: 2,
        background: '#2a2a3a',
        overflow: 'hidden',
        marginTop: 2,
        width: '100%',
      }}
    >
      <div
        style={{
          height: '100%',
          width: `${Math.min(Math.max(value * 100, 0), 100)}%`,
          background: color,
          transition: 'width 0.4s ease',
        }}
      />
    </div>
  )
}

function salienceColor(s: number): string {
  if (s >= 0.75) return '#22c55e'  // green
  if (s >= 0.45) return '#f59e0b'  // amber
  return '#ef4444'                  // red
}

function MemoryCard({ m }: { m: MemoryItem }) {
  return (
    <div
      style={{
        background: m.is_dormant ? '#1a1a2a' : '#1e1e30',
        border: `1px solid ${m.is_dormant ? '#3a2a1a' : '#2a2a40'}`,
        borderRadius: 8,
        padding: '10px 12px',
        marginBottom: 8,
        opacity: m.is_dormant ? 0.65 : 1,
      }}
    >
      {/* Header row */}
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 4 }}>
        <span
          style={{
            fontSize: 11,
            color: '#888',
            fontFamily: 'monospace',
            marginRight: 6,
          }}
        >
          {m.id.slice(0, 8)}
        </span>
        {m.has_vector ? (
          <Badge label="VECTOR" color="#16a34a" />
        ) : (
          <Badge label="NO VECTOR" color="#475569" />
        )}
        {m.is_dormant && <Badge label="DORMANT" color="#b45309" />}
        {m.tags.slice(0, 3).map(t => (
          <Badge key={t} label={t} color="#312e81" />
        ))}
      </div>

      {/* Content */}
      <p style={{ margin: 0, fontSize: 13, color: '#d1d5db', lineHeight: 1.5 }}>
        {m.content}
      </p>

      {/* Bars */}
      <div style={{ marginTop: 6, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
        <div>
          <span style={{ fontSize: 10, color: '#6b7280' }}>
            SALIENCE {m.salience.toFixed(2)}
          </span>
          <StrengthBar value={m.salience} color={salienceColor(m.salience)} />
        </div>
        <div>
          <span style={{ fontSize: 10, color: '#6b7280' }}>
            STRENGTH {m.current_strength.toFixed(2)}
          </span>
          <StrengthBar value={m.current_strength} color="#6366f1" />
        </div>
      </div>
    </div>
  )
}

// ── Stats header ──────────────────────────────────────────────────────────────

function CoverageBar({ pct }: { pct: number }) {
  const color = pct >= 80 ? '#22c55e' : pct >= 40 ? '#f59e0b' : '#ef4444'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div
        style={{
          flex: 1,
          height: 6,
          borderRadius: 3,
          background: '#2a2a3a',
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            height: '100%',
            width: `${pct}%`,
            background: color,
            transition: 'width 0.5s ease',
          }}
        />
      </div>
      <span style={{ fontSize: 12, color, minWidth: 38, textAlign: 'right' }}>
        {pct}%
      </span>
    </div>
  )
}

// ── Main component ─────────────────────────────────────────────────────────────

type PanelTab = 'episodic' | 'semantic' | 'dormant'

export default function VectorMemoriesPanel() {
  const [tab, setTab] = useState<PanelTab>('episodic')

  const vectorStatus = useVectorStatus()
  const { memories: episodic } = useMemories(100)
  const semanticData = useSemanticMemories(100)
  const dormant = episodic.filter(m => m.is_dormant)
  const active = episodic.filter(m => !m.is_dormant)

  const tabs: { id: PanelTab; label: string; count: number }[] = [
    { id: 'episodic', label: 'Episodic', count: active.length },
    { id: 'semantic', label: 'Semantic', count: semanticData?.total ?? 0 },
    { id: 'dormant', label: 'Dormant', count: dormant.length },
  ]

  return (
    <div style={{ padding: 16 }}>
      {/* ── Stats header ── */}
      {vectorStatus && (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gap: 12,
            marginBottom: 16,
            background: '#12121e',
            border: '1px solid #2a2a40',
            borderRadius: 10,
            padding: 14,
          }}
        >
          <div>
            <div
              style={{ fontSize: 11, color: '#6b7280', marginBottom: 4, letterSpacing: '0.06em' }}
            >
              EPISODIC VECTORS
            </div>
            <div style={{ fontSize: 15, color: '#e5e7eb', marginBottom: 4 }}>
              {vectorStatus.episodic_vector_count} / {vectorStatus.episodic_sqlite_count}
            </div>
            <CoverageBar pct={vectorStatus.episodic_coverage_pct} />
          </div>
          <div>
            <div
              style={{ fontSize: 11, color: '#6b7280', marginBottom: 4, letterSpacing: '0.06em' }}
            >
              SEMANTIC VECTORS
            </div>
            <div style={{ fontSize: 15, color: '#e5e7eb', marginBottom: 4 }}>
              {vectorStatus.semantic_vector_count} / {vectorStatus.semantic_sqlite_count}
            </div>
            <CoverageBar pct={vectorStatus.semantic_coverage_pct} />
          </div>
        </div>
      )}

      {/* ── Tab bar ── */}
      <div
        style={{
          display: 'flex',
          gap: 4,
          marginBottom: 14,
          borderBottom: '1px solid #2a2a40',
          paddingBottom: 8,
        }}
      >
        {tabs.map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            style={{
              padding: '5px 14px',
              borderRadius: 6,
              border: 'none',
              cursor: 'pointer',
              fontSize: 13,
              fontWeight: tab === t.id ? 700 : 400,
              background: tab === t.id ? '#4f46e5' : '#1e1e30',
              color: tab === t.id ? '#fff' : '#9ca3af',
              transition: 'background 0.15s',
            }}
          >
            {t.label}
            <span
              style={{
                marginLeft: 6,
                background: tab === t.id ? '#6366f1' : '#2a2a40',
                color: tab === t.id ? '#fff' : '#6b7280',
                borderRadius: 10,
                padding: '1px 7px',
                fontSize: 11,
              }}
            >
              {t.count}
            </span>
          </button>
        ))}
      </div>

      {/* ── Memory list ── */}
      <div style={{ maxHeight: '62vh', overflowY: 'auto', paddingRight: 4 }}>
        {tab === 'episodic' &&
          (active.length === 0 ? (
            <p style={{ color: '#6b7280', textAlign: 'center' }}>No active episodic memories.</p>
          ) : (
            active.map(m => <MemoryCard key={m.id} m={m} />)
          ))}

        {tab === 'semantic' &&
          (!semanticData || semanticData.items.length === 0 ? (
            <p style={{ color: '#6b7280', textAlign: 'center' }}>No semantic memories yet.</p>
          ) : (
            semanticData.items.map(m => <MemoryCard key={m.id} m={m} />)
          ))}

        {tab === 'dormant' &&
          (dormant.length === 0 ? (
            <p style={{ color: '#6b7280', textAlign: 'center' }}>No dormant memories.</p>
          ) : (
            dormant.map(m => <MemoryCard key={m.id} m={m} />)
          ))}
      </div>
    </div>
  )
}
