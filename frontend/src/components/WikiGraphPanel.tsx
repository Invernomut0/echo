import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import ForceGraph3DLib from '3d-force-graph'
import type { ForceGraph3DInstance } from '3d-force-graph'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  fetchWikiGraph,
  fetchWikiPage,
  fetchWikiLog,
  ingestWikiSource,
  ingestWikiFiles,
  queryWiki,
} from '../api'
import type { WikiNode, WikiLink, WikiGraphData } from '../api'

// ── Category colours ────────────────────────────────────────────────────────
const CAT_COLOR: Record<string, string> = {
  entities:   '#06b6d4',   // cyan
  concepts:   '#a78bfa',   // purple
  sources:    '#f59e0b',   // amber
  syntheses:  '#10b981',   // green
}
const CAT_LABEL: Record<string, string> = {
  entities:   'Entità',
  concepts:   'Concetti',
  sources:    'Sorgenti',
  syntheses:  'Sintesi',
}
const CAT_EMOJI: Record<string, string> = {
  entities:   '👤',
  concepts:   '💡',
  sources:    '📄',
  syntheses:  '🔬',
}

function nodeColor(n: WikiNode, selected: WikiNode | null): string {
  if (selected?.id === n.id) return '#ffffff'
  const base = CAT_COLOR[n.category] ?? '#64748b'
  const alpha = Math.round((0.45 + Math.min(n.degree / 10, 1) * 0.55) * 255)
    .toString(16).padStart(2, '0')
  return `${base}${alpha}`
}

function isWebGLAvailable(): boolean {
  try {
    const c = document.createElement('canvas')
    return !!(c.getContext('webgl2') || c.getContext('webgl'))
  } catch { return false }
}

// ── Sub-panel components ─────────────────────────────────────────────────────

function NodeDetail({
  node,
  onClose,
}: {
  node: WikiNode
  onClose: () => void
}) {
  const [body, setBody] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    setLoading(true)
    fetchWikiPage(node.path)
      .then(setBody)
      .catch(() => setBody('*Impossibile caricare la pagina.*'))
      .finally(() => setLoading(false))
  }, [node.path])

  return (
    <div style={panelStyle}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
        <span style={{ color: CAT_COLOR[node.category] ?? '#64748b', fontWeight: 700, fontSize: 13 }}>
          {CAT_EMOJI[node.category]} {CAT_LABEL[node.category] ?? node.category}
        </span>
        <button onClick={onClose} style={closeBtnStyle}>✕</button>
      </div>
      <div style={{ color: '#e2e8f0', fontWeight: 600, fontSize: 14, marginBottom: 6 }}>{node.title}</div>
      {node.tags.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 8 }}>
          {node.tags.map(t => (
            <span key={t} style={tagStyle}>{t}</span>
          ))}
        </div>
      )}
      <div style={{ color: '#64748b', fontSize: 11, marginBottom: 10 }}>
        Grado: <span style={{ color: '#94a3b8' }}>{node.degree}</span>
        &nbsp;·&nbsp;{node.path}
      </div>
      <div style={{ borderTop: '1px solid #1e293b', paddingTop: 10 }}>
        {loading ? (
          <span style={{ color: '#475569', fontSize: 12 }}>Caricamento…</span>
        ) : (
          <div style={{ color: '#cbd5e1', fontSize: 12, lineHeight: 1.6, maxHeight: 320, overflowY: 'auto' }}>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{body ?? ''}</ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  )
}

function IngestPanel({ onDone }: { onDone: () => void }) {
  const [tab, setTab] = useState<'file' | 'text'>('file')
  const [title, setTitle] = useState('')
  const [text, setText] = useState('')
  const [type, setType] = useState('document')
  const [loading, setLoading] = useState(false)
  const [results, setResults] = useState<string[]>([])
  const [dragOver, setDragOver] = useState(false)
  const [pendingFiles, setPendingFiles] = useState<File[]>([])
  const fileInputRef = useRef<HTMLInputElement>(null)

  const ACCEPTED = '.txt,.md,.pdf'

  function addFiles(newFiles: FileList | File[]) {
    const arr = Array.from(newFiles).filter(f => /\.(txt|md|pdf)$/i.test(f.name))
    if (!arr.length) return
    setPendingFiles(prev => {
      const names = new Set(prev.map(f => f.name))
      return [...prev, ...arr.filter(f => !names.has(f.name))]
    })
  }

  function removeFile(name: string) {
    setPendingFiles(prev => prev.filter(f => f.name !== name))
  }

  async function handleFileIngest() {
    if (!pendingFiles.length) return
    setLoading(true)
    setResults([])
    try {
      const res = await ingestWikiFiles(pendingFiles, type)
      const msgs = res.map(r => `✓ ${r.title}: ${r.entities} entità, ${r.concepts} concetti, ${r.pages_written.length} pagine`)
      setResults(msgs)
      setPendingFiles([])
      setTimeout(onDone, 1600)
    } catch (e) {
      setResults([`✗ Errore: ${String(e)}`])
    } finally {
      setLoading(false)
    }
  }

  async function handleTextIngest() {
    if (!title.trim() || !text.trim()) return
    setLoading(true)
    setResults([])
    try {
      const r = await ingestWikiSource(title.trim(), text.trim(), type)
      setResults([`✓ ${r.title}: ${r.entities} entità, ${r.concepts} concetti, ${r.pages_written.length} pagine.`])
      setTimeout(onDone, 1200)
    } catch (e) {
      setResults([`✗ Errore: ${String(e)}`])
    } finally {
      setLoading(false)
    }
  }

  const tabBtnStyle = (active: boolean): React.CSSProperties => ({
    flex: 1, padding: '5px 0', fontSize: 12, cursor: 'pointer', border: 'none',
    borderRadius: 4, background: active ? '#1e293b' : 'transparent',
    color: active ? '#e2e8f0' : '#64748b', fontWeight: active ? 600 : 400,
  })

  const dropZoneStyle: React.CSSProperties = {
    border: `2px dashed ${dragOver ? '#f59e0b' : '#334155'}`,
    borderRadius: 6, padding: '18px 12px', textAlign: 'center',
    cursor: 'pointer', marginTop: 8,
    background: dragOver ? '#f59e0b08' : 'transparent',
    color: '#64748b', fontSize: 12, transition: 'all .15s',
  }

  return (
    <div style={panelStyle}>
      <div style={{ color: '#e2e8f0', fontWeight: 600, marginBottom: 10 }}>📥 Ingesta nella Wiki</div>

      {/* Tipo sorgente */}
      <select value={type} onChange={e => setType(e.target.value)} style={{ ...inputStyle, marginBottom: 8 }}>
        <option value="document">Documento</option>
        <option value="article">Articolo</option>
        <option value="paper">Paper</option>
        <option value="book">Libro</option>
        <option value="note">Nota</option>
        <option value="text">Testo generico</option>
      </select>

      {/* Tab switcher */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 8 }}>
        <button style={tabBtnStyle(tab === 'file')} onClick={() => setTab('file')}>📎 File</button>
        <button style={tabBtnStyle(tab === 'text')} onClick={() => setTab('text')}>✏️ Testo</button>
      </div>

      {tab === 'file' ? (
        <>
          {/* Drop zone */}
          <div
            style={dropZoneStyle}
            onDragOver={e => { e.preventDefault(); setDragOver(true) }}
            onDragLeave={() => setDragOver(false)}
            onDrop={e => { e.preventDefault(); setDragOver(false); addFiles(e.dataTransfer.files) }}
            onClick={() => fileInputRef.current?.click()}
          >
            Trascina qui i file o clicca<br />
            <span style={{ color: '#475569' }}>.txt · .md · .pdf — più file contemporaneamente</span>
          </div>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept={ACCEPTED}
            style={{ display: 'none' }}
            onChange={e => { if (e.target.files) addFiles(e.target.files); e.target.value = '' }}
          />

          {/* File list */}
          {pendingFiles.length > 0 && (
            <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 4 }}>
              {pendingFiles.map(f => (
                <div key={f.name} style={{ display: 'flex', alignItems: 'center', gap: 6, background: '#0f172a', borderRadius: 4, padding: '4px 8px' }}>
                  <span style={{ fontSize: 11, color: '#cbd5e1', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {f.name} <span style={{ color: '#475569' }}>({(f.size / 1024).toFixed(0)} KB)</span>
                  </span>
                  <button onClick={() => removeFile(f.name)} style={{ border: 'none', background: 'none', color: '#f43f5e', cursor: 'pointer', fontSize: 13, lineHeight: 1 }}>✕</button>
                </div>
              ))}
            </div>
          )}

          <button
            onClick={handleFileIngest}
            disabled={loading || !pendingFiles.length}
            style={{ ...btnStyle, marginTop: 10 }}
          >
            {loading ? `Elaborazione ${pendingFiles.length} file…` : `Ingesta ${pendingFiles.length || ''} file`}
          </button>
        </>
      ) : (
        <>
          <input
            value={title}
            onChange={e => setTitle(e.target.value)}
            placeholder="Titolo…"
            style={inputStyle}
          />
          <textarea
            value={text}
            onChange={e => setText(e.target.value)}
            placeholder="Contenuto della sorgente…"
            rows={6}
            style={{ ...inputStyle, marginTop: 6, resize: 'vertical', fontFamily: 'inherit' }}
          />
          <button
            onClick={handleTextIngest}
            disabled={loading || !title.trim() || !text.trim()}
            style={btnStyle}
          >
            {loading ? 'Elaborazione…' : 'Ingesta testo'}
          </button>
        </>
      )}

      {results.length > 0 && (
        <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 3 }}>
          {results.map((r, i) => (
            <div key={i} style={{ fontSize: 11, color: r.startsWith('✓') ? '#10b981' : '#f43f5e' }}>{r}</div>
          ))}
        </div>
      )}
    </div>
  )
}

function QueryPanel() {
  const [question, setQuestion] = useState('')
  const [loading, setLoading] = useState(false)
  const [answer, setAnswer] = useState<{ answer: string; pages: string[]; synthesis: string | null } | null>(null)

  async function handleQuery() {
    if (!question.trim()) return
    setLoading(true)
    setAnswer(null)
    try {
      const r = await queryWiki(question.trim())
      setAnswer({ answer: r.answer, pages: r.pages_consulted, synthesis: r.synthesis_page })
    } catch (e) {
      setAnswer({ answer: `Errore: ${String(e)}`, pages: [], synthesis: null })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={panelStyle}>
      <div style={{ color: '#e2e8f0', fontWeight: 600, marginBottom: 10 }}>🔍 Query wiki</div>
      <div style={{ display: 'flex', gap: 6 }}>
        <input
          value={question}
          onChange={e => setQuestion(e.target.value)}
          placeholder="Fai una domanda…"
          onKeyDown={e => e.key === 'Enter' && handleQuery()}
          style={{ ...inputStyle, flex: 1 }}
        />
        <button onClick={handleQuery} disabled={loading || !question.trim()} style={{ ...btnStyle, width: 'auto', paddingInline: 12 }}>
          {loading ? '…' : '→'}
        </button>
      </div>
      {answer && (
        <div style={{ marginTop: 10 }}>
          <div style={{ color: '#94a3b8', fontSize: 11, marginBottom: 4 }}>
            Pagine consultate: {answer.pages.join(', ') || '—'}
            {answer.synthesis && <span style={{ marginLeft: 6, color: '#10b981' }}>· archiviata come sintesi</span>}
          </div>
          <div style={{ color: '#cbd5e1', fontSize: 12, lineHeight: 1.6, maxHeight: 260, overflowY: 'auto' }}>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{answer.answer}</ReactMarkdown>
          </div>
        </div>
      )}
    </div>
  )
}

function LogPanel() {
  const [log, setLog] = useState<string | null>(null)

  useEffect(() => {
    fetchWikiLog(30).then(setLog).catch(() => setLog('*Log non disponibile*'))
  }, [])

  return (
    <div style={{ ...panelStyle, maxHeight: 400, overflowY: 'auto' }}>
      <div style={{ color: '#e2e8f0', fontWeight: 600, marginBottom: 8 }}>📋 Log wiki</div>
      <div style={{ color: '#94a3b8', fontSize: 11, lineHeight: 1.7 }}>
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{log ?? 'Caricamento…'}</ReactMarkdown>
      </div>
    </div>
  )
}

// ── Shared micro-styles ───────────────────────────────────────────────────────
const panelStyle: React.CSSProperties = {
  background: '#0d1117',
  border: '1px solid #1e293b',
  borderRadius: 10,
  padding: '14px 16px',
  marginBottom: 10,
}
const inputStyle: React.CSSProperties = {
  width: '100%',
  background: '#0a0f1a',
  border: '1px solid #1e293b',
  borderRadius: 6,
  color: '#e2e8f0',
  fontSize: 12,
  padding: '6px 10px',
  outline: 'none',
  boxSizing: 'border-box',
}
const btnStyle: React.CSSProperties = {
  marginTop: 8,
  width: '100%',
  background: '#06b6d4',
  border: 'none',
  borderRadius: 6,
  color: '#000',
  fontWeight: 700,
  fontSize: 12,
  padding: '7px 0',
  cursor: 'pointer',
}
const closeBtnStyle: React.CSSProperties = {
  background: 'none',
  border: 'none',
  color: '#475569',
  cursor: 'pointer',
  fontSize: 14,
  padding: 2,
}
const tagStyle: React.CSSProperties = {
  background: '#1e293b',
  color: '#94a3b8',
  borderRadius: 4,
  fontSize: 10,
  padding: '2px 6px',
}

// ── Main panel ────────────────────────────────────────────────────────────────

interface Props {
  active: boolean
}

type SideMode = 'detail' | 'ingest' | 'query' | 'log' | null

export default function WikiGraphPanel({ active }: Props) {
  const mountRef = useRef<HTMLDivElement>(null)
  const graphRef = useRef<ForceGraph3DInstance | null>(null)
  const selectedNodeRef = useRef<WikiNode | null>(null)

  const [data, setData] = useState<WikiGraphData>({ nodes: [], links: [], stats: { total_pages: 0, total_links: 0, by_category: {} } })
  const [loading, setLoading] = useState(false)
  const [selectedNode, setSelectedNode] = useState<WikiNode | null>(null)
  const [hiddenCats, setHiddenCats] = useState<Set<string>>(new Set())
  const [search, setSearch] = useState('')
  const [sideMode, setSideMode] = useState<SideMode>(null)
  const [webgl] = useState(isWebGLAvailable)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const g = await fetchWikiGraph()
      setData(g)
    } catch {
      // silently ignore — wiki may be empty
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (active) load()
  }, [active, load])

  const toggleCat = useCallback((cat: string) => {
    setHiddenCats(prev => {
      const next = new Set(prev)
      next.has(cat) ? next.delete(cat) : next.add(cat)
      return next
    })
  }, [])

  // Search-highlighted node IDs
  const highlighted = useMemo<Set<string>>(() => {
    if (!search.trim()) return new Set()
    const q = search.toLowerCase()
    return new Set(
      data.nodes
        .filter(n => n.title.toLowerCase().includes(q) || n.tags.some(t => t.toLowerCase().includes(q)) || n.summary.toLowerCase().includes(q))
        .map(n => n.id)
    )
  }, [search, data.nodes])

  const graphData = useMemo(() => ({
    nodes: data.nodes
      .filter(n => !hiddenCats.has(n.category))
      .map(n => ({ ...n })),
    links: data.links
      .filter(l => {
        const srcNode = data.nodes.find(n => n.id === l.source)
        const tgtNode = data.nodes.find(n => n.id === l.target)
        return srcNode && !hiddenCats.has(srcNode.category)
          && tgtNode && !hiddenCats.has(tgtNode.category)
      })
      .map(l => ({ ...l })),
  }), [data, hiddenCats])

  // ── Init 3D graph ──────────────────────────────────────────────────────────
  useEffect(() => {
    if (!mountRef.current || !webgl || !active) return
    const el = mountRef.current
    const { clientWidth: w, clientHeight: h } = el

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const graph = (ForceGraph3DLib as any)({ controlType: 'orbit' })(el)
      .backgroundColor('#070a12')
      .showNavInfo(false)
      .width(w || 900)
      .height(h || 600)
      .nodeLabel((n: object) => {
        const node = n as WikiNode
        const cat = CAT_LABEL[node.category] ?? node.category
        return `<span style="font-size:11px;color:#e2e8f0"><b>${node.title}</b><br/><small style="color:${CAT_COLOR[node.category] ?? '#64748b'}">${cat}</small><br/><small style="color:#64748b">${node.summary.slice(0, 80)}${node.summary.length > 80 ? '…' : ''}</small></span>`
      })
      .nodeVal((n: object) => {
        const node = n as WikiNode
        // Size = base + degree (connected = bigger sphere)
        return 3 + Math.min(node.degree * 1.5, 12)
      })
      .nodeColor((n: object) => {
        const node = n as WikiNode
        if (highlighted.size > 0 && !highlighted.has(node.id)) {
          return '#1e293b44'
        }
        return nodeColor(node, selectedNodeRef.current)
      })
      .nodeOpacity(0.9)
      .linkColor(() => '#334155')
      .linkWidth(1.2)
      .linkLabel((l: object) => {
        const link = l as WikiLink
        return `${link.label}`
      })
      .linkOpacity(0.5)
      .linkDirectionalArrowLength(4)
      .linkDirectionalArrowRelPos(1)
      .linkDirectionalParticles(1)
      .linkDirectionalParticleWidth(1.5)
      .enableNodeDrag(true)
      .onNodeClick((node: object) => {
        const n = node as WikiNode
        setSelectedNode(prev => {
          const next = prev?.id === n.id ? null : ({ ...n } as WikiNode)
          selectedNodeRef.current = next
          setSideMode(next ? 'detail' : null)
          return next
        })
      })

    graphRef.current = graph

    const ro = new ResizeObserver(entries => {
      for (const e of entries) {
        const { width, height } = e.contentRect
        if (width > 0 && height > 0 && graphRef.current) {
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          ;(graphRef.current as any).width(width).height(height)
        }
      }
    })
    ro.observe(el)

    return () => {
      ro.disconnect()
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const g = graphRef.current as any
      if (g) {
        g.pauseAnimation?.()
        try { g.renderer?.().dispose?.() } catch (_) { /* ignore */ }
        g._destructor?.()
        el.innerHTML = ''
      }
      graphRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, webgl])

  // Update data preserving positions
  useEffect(() => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const g = graphRef.current as any
    if (!g) return
    const current = g.graphData() as { nodes: Array<{ id: string; x?: number; y?: number; z?: number }> }
    const posMap = new Map(current.nodes.map(n => [n.id, { x: n.x, y: n.y, z: n.z }]))
    const stableNodes = graphData.nodes.map(n => {
      const p = posMap.get(n.id)
      return p?.x !== undefined ? { ...n, ...p } : n
    })
    g.graphData({ nodes: stableNodes, links: graphData.links })
  }, [graphData])

  // Recolour on search/selection change
  useEffect(() => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ;(graphRef.current as any)?.nodeColor((n: object) => {
      const node = n as WikiNode
      if (highlighted.size > 0 && !highlighted.has(node.id)) return '#1e293b44'
      return nodeColor(node, selectedNode)
    })
  }, [highlighted, selectedNode])

  if (!webgl) {
    return (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#070a12', color: '#475569', fontSize: 13 }}>
        ⬡ WebGL non disponibile in questo ambiente
      </div>
    )
  }

  const cats = ['entities', 'concepts', 'sources', 'syntheses']

  return (
    <div style={{ flex: 1, display: 'flex', height: '100%', background: '#070a12', position: 'relative', overflow: 'hidden' }}>

      {/* 3D Canvas */}
      <div ref={mountRef} style={{ flex: 1, height: '100%' }} />

      {/* Top-left overlay — stats + filters */}
      <div style={{
        position: 'absolute', top: 14, left: 14,
        display: 'flex', flexDirection: 'column', gap: 8,
        pointerEvents: 'none',
      }}>
        {/* Stats badge */}
        <div style={{
          background: '#0d111799', backdropFilter: 'blur(8px)',
          borderRadius: 8, padding: '8px 12px',
          display: 'flex', gap: 16, fontSize: 11, color: '#94a3b8',
          pointerEvents: 'none',
        }}>
          <span>⬡ <b style={{ color: '#e2e8f0' }}>{data.stats.total_pages}</b> pagine</span>
          <span>⟶ <b style={{ color: '#e2e8f0' }}>{data.stats.total_links}</b> link</span>
          {loading && <span style={{ color: '#06b6d4' }}>⟳</span>}
        </div>

        {/* Category filters */}
        <div style={{
          background: '#0d111799', backdropFilter: 'blur(8px)',
          borderRadius: 8, padding: '8px 12px',
          display: 'flex', gap: 8, fontSize: 11,
          pointerEvents: 'all',
        }}>
          {cats.map(cat => (
            <button
              key={cat}
              onClick={() => toggleCat(cat)}
              style={{
                background: 'none', border: 'none', cursor: 'pointer', padding: '2px 6px',
                borderRadius: 4,
                color: hiddenCats.has(cat) ? '#334155' : (CAT_COLOR[cat] ?? '#64748b'),
                fontSize: 11, fontWeight: hiddenCats.has(cat) ? 400 : 600,
                textDecoration: hiddenCats.has(cat) ? 'line-through' : 'none',
              }}
            >
              {CAT_EMOJI[cat]} {CAT_LABEL[cat]}
              <span style={{ color: '#475569', marginLeft: 4 }}>
                {data.stats.by_category[cat] ?? 0}
              </span>
            </button>
          ))}
        </div>
      </div>

      {/* Top-right overlay — search + action buttons */}
      <div style={{
        position: 'absolute', top: 14, right: sideMode ? 340 : 14,
        display: 'flex', gap: 6, alignItems: 'center',
        pointerEvents: 'all',
        transition: 'right .2s',
      }}>
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Cerca nodo…"
          style={{
            background: '#0d1117cc', backdropFilter: 'blur(8px)',
            border: '1px solid #1e293b', borderRadius: 6,
            color: '#e2e8f0', fontSize: 12, padding: '6px 10px', outline: 'none', width: 160,
          }}
        />
        <button onClick={load} style={topBtnStyle} title="Ricarica">↺</button>
        <button onClick={() => setSideMode(m => m === 'ingest' ? null : 'ingest')} style={{ ...topBtnStyle, background: sideMode === 'ingest' ? '#f59e0b22' : undefined, color: '#f59e0b' }} title="Ingesta">📥</button>
        <button onClick={() => setSideMode(m => m === 'query' ? null : 'query')} style={{ ...topBtnStyle, background: sideMode === 'query' ? '#06b6d422' : undefined }} title="Query">🔍</button>
        <button onClick={() => setSideMode(m => m === 'log' ? null : 'log')} style={{ ...topBtnStyle, background: sideMode === 'log' ? '#a78bfa22' : undefined, color: '#a78bfa' }} title="Log">📋</button>
      </div>

      {/* Right sidebar panel */}
      {sideMode && (
        <div style={{
          position: 'absolute', top: 0, right: 0, bottom: 0, width: 320,
          background: '#090e18ee', backdropFilter: 'blur(12px)',
          borderLeft: '1px solid #1e293b',
          overflowY: 'auto', padding: 14,
          display: 'flex', flexDirection: 'column', gap: 0,
        }}>
          {sideMode === 'detail' && selectedNode && (
            <NodeDetail node={selectedNode} onClose={() => { setSideMode(null); setSelectedNode(null); selectedNodeRef.current = null }} />
          )}
          {sideMode === 'ingest' && (
            <>
              <button onClick={() => setSideMode(null)} style={{ ...closeBtnStyle, alignSelf: 'flex-end', marginBottom: 6 }}>✕</button>
              <IngestPanel onDone={() => { setSideMode(null); load() }} />
            </>
          )}
          {sideMode === 'query' && (
            <>
              <button onClick={() => setSideMode(null)} style={{ ...closeBtnStyle, alignSelf: 'flex-end', marginBottom: 6 }}>✕</button>
              <QueryPanel />
            </>
          )}
          {sideMode === 'log' && (
            <>
              <button onClick={() => setSideMode(null)} style={{ ...closeBtnStyle, alignSelf: 'flex-end', marginBottom: 6 }}>✕</button>
              <LogPanel />
            </>
          )}
        </div>
      )}

      {/* Empty state */}
      {!loading && data.nodes.length === 0 && (
        <div style={{
          position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)',
          textAlign: 'center', color: '#334155', pointerEvents: 'none',
        }}>
          <div style={{ fontSize: 36, marginBottom: 12 }}>⬡</div>
          <div style={{ fontSize: 14, color: '#475569' }}>La wiki è vuota.</div>
          <div style={{ fontSize: 12, marginTop: 6 }}>Ingesta una sorgente per popolare il grafo.</div>
        </div>
      )}
    </div>
  )
}

const topBtnStyle: React.CSSProperties = {
  background: '#0d1117cc',
  backdropFilter: 'blur(8px)',
  border: '1px solid #1e293b',
  borderRadius: 6,
  color: '#94a3b8',
  fontSize: 14,
  padding: '5px 9px',
  cursor: 'pointer',
}
