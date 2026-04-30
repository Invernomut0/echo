import { useState } from 'react'
import { useMemories, useVectorStatus, useSemanticMemories, useChunks } from '../hooks'
import type { MemoryItem, ChunkItem, MemoryWithChunks } from '../api'

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
        <span style={{ marginLeft: 'auto', fontSize: 10, color: '#4b5563', flexShrink: 0 }}>
          {new Date(m.created_at).toLocaleString('en-GB', {
            day: '2-digit', month: 'short', year: 'numeric',
            hour: '2-digit', minute: '2-digit',
          })}
        </span>
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

/**
 * Shows the avg-chunks-per-memory ratio as a horizontal bar capped at a
 * "reasonable max" of 10 chunks/memory, plus a text label.
 *
 * Background: each memory is split into N ChromaDB chunks (chunked text).
 * The bar fills proportionally to that average (≤ 10 chunks = full bar).
 * We cap visually so the bar never overflows at high ratios.
 */
function AvgChunksBar({ vectors, memories }: { vectors: number; memories: number }) {
  const avg = memories > 0 ? vectors / memories : 0
  const MAX_AVG = 10          // bar fills 100% at 10 chunks/memory
  const fillPct = Math.min((avg / MAX_AVG) * 100, 100)
  // colour ramp: few chunks = amber (could be too sparse), many = green
  const color = avg >= 2 ? '#818cf8' : avg >= 1 ? '#f59e0b' : '#ef4444'
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
            width: `${fillPct}%`,
            background: color,
            transition: 'width 0.5s ease',
          }}
        />
      </div>
      <span style={{ fontSize: 12, color, minWidth: 56, textAlign: 'right' }}>
        ~{avg.toFixed(1)} each
      </span>
    </div>
  )
}

// ── Main component ─────────────────────────────────────────────────────────────

type PanelTab = 'episodic' | 'semantic' | 'dormant' | 'chunks'

// ── Chunk viewer components ────────────────────────────────────────────────────

/** Mini heat-map bar showing the first N embedding dimensions. */
function EmbeddingPreview({ values }: { values: number[] }) {
  if (values.length === 0) return null
  const min = Math.min(...values)
  const max = Math.max(...values)
  const range = max - min || 1
  return (
    <div style={{ display: 'flex', gap: 2, alignItems: 'flex-end', marginTop: 8 }}>
      {values.map((v, i) => {
        const norm = (v - min) / range
        // cool → warm gradient (blue-purple → orange)
        const r = Math.round(30 + norm * 200)
        const g = Math.round(80 + norm * 40)
        const b = Math.round(220 - norm * 180)
        return (
          <div
            key={i}
            title={`dim ${i}: ${v.toFixed(4)}`}
            style={{
              width: 14,
              height: Math.round(8 + norm * 20),
              borderRadius: 2,
              background: `rgb(${r},${g},${b})`,
              opacity: 0.85,
              flexShrink: 0,
            }}
          />
        )
      })}
      <span style={{ fontSize: 10, color: '#6b7280', marginLeft: 4, alignSelf: 'center' }}>
        dims 0–{values.length - 1}
      </span>
    </div>
  )
}

function ChunkCard({ chunk }: { chunk: ChunkItem }) {
  return (
    <div
      style={{
        background: '#0f0f1a',
        borderRadius: 6,
        padding: '8px 12px',
        marginBottom: 6,
        borderLeft: '3px solid #4f46e5',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
        <span style={{ fontSize: 11, color: '#818cf8', fontWeight: 700 }}>
          chunk {chunk.chunk_index}
        </span>
        <span style={{ fontSize: 10, color: '#6b7280' }}>
          {chunk.char_count.toLocaleString()} chars · {chunk.embedding_dim}d
        </span>
      </div>
      <p
        style={{
          fontSize: 12,
          color: '#d1d5db',
          margin: 0,
          lineHeight: 1.55,
          wordBreak: 'break-word',
        }}
      >
        {chunk.text.length > 300 ? chunk.text.slice(0, 300) + '…' : chunk.text}
      </p>
      <EmbeddingPreview values={chunk.embedding_preview} />
    </div>
  )
}

function MemoryChunksCard({ mem }: { mem: MemoryWithChunks }) {
  const [expanded, setExpanded] = useState(false)
  return (
    <div
      style={{
        background: '#1a1a2e',
        borderRadius: 8,
        padding: '10px 14px',
        marginBottom: 10,
        border: '1px solid #2a2a40',
      }}
    >
      {/* Clickable header */}
      <div
        style={{ cursor: 'pointer', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}
        onClick={() => setExpanded(e => !e)}
      >
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 5 }}>
          <code style={{ fontSize: 11, color: '#6366f1', fontFamily: 'monospace' }}>
            {mem.memory_id.slice(0, 8)}
          </code>
          <span
            style={{
              fontSize: 11,
              background: '#2a2a40',
              color: '#9ca3af',
              borderRadius: 10,
              padding: '1px 7px',
            }}
          >
            {mem.chunk_count} chunk{mem.chunk_count !== 1 ? 's' : ''}
          </span>
          <span
            style={{
              fontSize: 11,
              background: '#312e81',
              color: '#a5b4fc',
              borderRadius: 10,
              padding: '1px 7px',
            }}
          >
            sal {mem.salience.toFixed(2)}
          </span>
          {mem.tags.slice(0, 3).map(t => (
            <span
              key={t}
              style={{
                fontSize: 10,
                background: '#1e1e40',
                color: '#818cf8',
                borderRadius: 10,
                padding: '1px 6px',
              }}
            >
              {t}
            </span>
          ))}
        </div>
        <span style={{ color: '#6b7280', fontSize: 14, marginLeft: 8, flexShrink: 0 }}>
          {expanded ? '▲' : '▼'}
        </span>
      </div>

      {/* Content preview */}
      <p style={{ fontSize: 12, color: '#9ca3af', margin: '6px 0 0', lineHeight: 1.45 }}>
        {mem.content.length > 160 ? mem.content.slice(0, 160) + '…' : mem.content}
      </p>

      {/* Expanded: individual chunks */}
      {expanded && (
        <div style={{ marginTop: 10 }}>
          {mem.chunks.length === 0 ? (
            <p style={{ color: '#6b7280', fontSize: 12 }}>No ChromaDB chunks found for this memory.</p>
          ) : (
            mem.chunks.map(c => <ChunkCard key={c.chunk_id} chunk={c} />)
          )}
        </div>
      )}
    </div>
  )
}

export default function VectorMemoriesPanel() {
  const [tab, setTab] = useState<PanelTab>('episodic')

  const vectorStatus = useVectorStatus()
  const { memories: episodic } = useMemories(100)
  const semanticData = useSemanticMemories(100)
  const dormant = episodic.filter(m => m.is_dormant)
  const active = episodic.filter(m => !m.is_dormant)

  const isChunksTab = tab === 'chunks'
  const { data: chunksData, loading: chunksLoading } = useChunks(isChunksTab)

  const tabs: { id: PanelTab; label: string; count: number }[] = [
    { id: 'episodic', label: 'Episodic', count: active.length },
    { id: 'semantic', label: 'Semantic', count: semanticData?.total ?? 0 },
    { id: 'dormant', label: 'Dormant', count: dormant.length },
    { id: 'chunks', label: 'Chunks', count: chunksData?.total_chunks ?? 0 },
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
            <div style={{ fontSize: 15, color: '#e5e7eb', marginBottom: 2 }}>
              {vectorStatus.episodic_vector_count}
              <span style={{ fontSize: 11, color: '#6b7280', marginLeft: 4 }}>
                chunks
              </span>
              <span style={{ fontSize: 11, color: '#4b5563', margin: '0 4px' }}>·</span>
              <span style={{ fontSize: 13, color: '#9ca3af' }}>
                {vectorStatus.episodic_sqlite_count}
              </span>
              <span style={{ fontSize: 11, color: '#6b7280', marginLeft: 4 }}>
                memories
              </span>
            </div>
            <AvgChunksBar
              vectors={vectorStatus.episodic_vector_count}
              memories={vectorStatus.episodic_sqlite_count}
            />
          </div>
          <div>
            <div
              style={{ fontSize: 11, color: '#6b7280', marginBottom: 4, letterSpacing: '0.06em' }}
            >
              SEMANTIC VECTORS
            </div>
            <div style={{ fontSize: 15, color: '#e5e7eb', marginBottom: 2 }}>
              {vectorStatus.semantic_vector_count}
              <span style={{ fontSize: 11, color: '#6b7280', marginLeft: 4 }}>
                chunks
              </span>
              <span style={{ fontSize: 11, color: '#4b5563', margin: '0 4px' }}>·</span>
              <span style={{ fontSize: 13, color: '#9ca3af' }}>
                {vectorStatus.semantic_sqlite_count}
              </span>
              <span style={{ fontSize: 11, color: '#6b7280', marginLeft: 4 }}>
                memories
              </span>
            </div>
            <AvgChunksBar
              vectors={vectorStatus.semantic_vector_count}
              memories={vectorStatus.semantic_sqlite_count}
            />
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

        {tab === 'chunks' && (
          chunksLoading
            ? <p style={{ color: '#6b7280', textAlign: 'center', paddingTop: 20 }}>Loading chunks…</p>
            : !chunksData || chunksData.memories.length === 0
              ? <p style={{ color: '#6b7280', textAlign: 'center', paddingTop: 20 }}>No semantic memories with chunks yet.</p>
              : (
                <>
                  <div style={{ fontSize: 11, color: '#6b7280', marginBottom: 10 }}>
                    {chunksData.total_memories} memories · {chunksData.total_chunks} total chunks in ChromaDB
                  </div>
                  {chunksData.memories.map(m => (
                    <MemoryChunksCard key={m.memory_id} mem={m} />
                  ))}
                </>
              )
        )}
      </div>
    </div>
  )
}
