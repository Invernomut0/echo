import { useCallback, useMemo, useRef, useState, useEffect } from 'react'
// Use 3d-force-graph directly to avoid the AFRAME crash from react-force-graph's AR/VR bundle
import ForceGraph3DLib from '3d-force-graph'
import type { ForceGraph3DInstance } from '3d-force-graph'
import type { GraphNode, GraphEdge } from '../api'

interface Props {
  nodes: GraphNode[]
  edges: GraphEdge[]
  coherenceScore?: number
}

const RELATION_CFG: Record<string, { color: string; label: string; sym: string }> = {
  SUPPORTS:     { color: '#10b981', label: 'Supporta',    sym: '↑' },
  CONTRADICTS:  { color: '#f43f5e', label: 'Contraddice', sym: '⚡' },
  REFINES:      { color: '#3b82f6', label: 'Raffina',     sym: '↔' },
  DERIVES_FROM: { color: '#94a3b8', label: 'Deriva da',   sym: '↙' },
}

// Semantic link types — coloured but NOT filterable (always visible)
const SEMANTIC_LINK_CFG: Record<string, { color: string; label: string; sym: string }> = {
  INFORMS:          { color: '#a78bfa', label: 'Informa',  sym: '⟶' },
  SEMANTIC_RELATED: { color: '#7c3aed', label: 'Correlato', sym: '≈' },
}

const ALL_LINK_CFG = { ...RELATION_CFG, ...SEMANTIC_LINK_CFG }

function isWebGLAvailable(): boolean {
  try {
    const canvas = document.createElement('canvas')
    return !!(canvas.getContext('webgl2') || canvas.getContext('webgl'))
  } catch {
    return false
  }
}

export default function IdentityGraph({ nodes, edges, coherenceScore = 0 }: Props) {
  const mountRef = useRef<HTMLDivElement>(null)
  const graphRef = useRef<ForceGraph3DInstance | null>(null)
  const selectedNodeRef = useRef<GraphNode | null>(null)
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null)
  const [hidden, setHidden] = useState<Set<string>>(new Set())
  const [webglAvailable] = useState<boolean>(() => isWebGLAvailable())

  const toggleHidden = useCallback((rel: string) => {
    setHidden(prev => {
      const next = new Set(prev)
      next.has(rel) ? next.delete(rel) : next.add(rel)
      return next
    })
  }, [])

  const relCounts = useMemo(() => {
    const m: Record<string, number> = {}
    edges.forEach(e => { m[e.relation] = (m[e.relation] ?? 0) + 1 })
    return m
  }, [edges])

  const nodeConnections = useMemo(() => {
    if (!selectedNode) return []
    return edges.filter(e => e.source === selectedNode.id || e.target === selectedNode.id)
  }, [selectedNode, edges])

  const graphData = useMemo(() => ({
    nodes: nodes.map(n => ({ ...n })),
    links: edges
      .filter(e => !hidden.has(e.relation))
      .map(e => ({ ...e })),
  }), [nodes, edges, hidden])

  // ── Init 3d-force-graph on mount (imperative API) ──────────────────────
  useEffect(() => {
    if (!mountRef.current || !webglAvailable) return
    const el = mountRef.current
    const { clientWidth: w, clientHeight: h } = el

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const graph = (ForceGraph3DLib as any)({ controlType: 'orbit' })(el)
      .backgroundColor('#070a12')
      .showNavInfo(false)
      .width(w || 800)
      .height(h || 600)
      .nodeLabel((n: object) => {
        const node = n as GraphNode
        const isSem = node.node_type === 'semantic'
        const typeLabel = isSem ? 'memoria semantica' : 'credenza'
        const scoreLabel = isSem ? 'salienza' : 'conf'
        return `<span style="font-size:11px;color:#e2e8f0">${node.content}<br/><small style="color:#94a3b8">${typeLabel} · ${scoreLabel}: ${(node.confidence * 100).toFixed(0)}%</small></span>`
      })
      .nodeVal((n: object) => {
        const node = n as GraphNode
        return node.node_type === 'semantic'
          ? 1.5 + (node.confidence ?? 0.5) * 5
          : 2 + (node.confidence ?? 0.5) * 8
      })
      .nodeColor((n: object) => {
        const node = n as GraphNode
        if (selectedNodeRef.current?.id === node.id) return '#ffffff'
        const alpha = Math.round((0.4 + (node.confidence ?? 0.5) * 0.6) * 255).toString(16).padStart(2, '0')
        return node.node_type === 'semantic' ? `#a78bfa${alpha}` : `#06b6d4${alpha}`
      })
      .nodeOpacity(0.9)
      .linkColor((l: object) => {
        const link = l as GraphEdge
        return ALL_LINK_CFG[link.relation]?.color ?? '#475569'
      })
      .linkWidth((l: object) => Math.max(0.8, ((l as GraphEdge).weight ?? 0.5) * 2.5))
      .linkLabel((l: object) => {
        const link = l as GraphEdge
        const cfg = ALL_LINK_CFG[link.relation]
        return `${cfg?.sym ?? '→'} ${link.relation} (${(link.weight ?? 0).toFixed(2)})`
      })
      .linkOpacity(0.7)
      .linkDirectionalArrowLength(4)
      .linkDirectionalArrowRelPos(1)
      .linkDirectionalParticles(1)
      .linkDirectionalParticleWidth(1.5)
      .enableNodeDrag(true)
      .onNodeClick((node: object) => {
        const n = node as GraphNode
        setSelectedNode(prev => {
          const next = prev?.id === n.id ? null : ({ ...n } as GraphNode)
          selectedNodeRef.current = next
          return next
        })
      })

    graphRef.current = graph

    const ro = new ResizeObserver(entries => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect
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
        // Dispose Three.js renderer so the WebGL context is released before
        // React StrictMode (dev) mounts the component a second time.
        try { g.renderer?.().dispose?.() } catch (_) { /* ignore */ }
        g._destructor?.()
        // Remove all child nodes Three.js may have appended to the mount div
        el.innerHTML = ''
      }
      graphRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Update graph data when nodes / edges / hidden filter change.
  // IMPORTANT: preserve existing node positions from the running simulation so
  // the force layout does NOT restart from scratch (which would make nodes jump
  // and shift the camera) on every 5-second poll update.
  useEffect(() => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const g = graphRef.current as any
    if (!g) return
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const current = g.graphData() as { nodes: Array<{ id: string; x?: number; y?: number; z?: number; vx?: number; vy?: number; vz?: number }> }
    const posMap = new Map(
      current.nodes.map((n) => [n.id, { x: n.x, y: n.y, z: n.z, vx: n.vx ?? 0, vy: n.vy ?? 0, vz: n.vz ?? 0 }])
    )
    const stableNodes = graphData.nodes.map((n) => {
      const pos = posMap.get(n.id)
      return pos && pos.x !== undefined ? { ...n, ...pos } : n
    })
    g.graphData({ nodes: stableNodes, links: graphData.links })
  }, [graphData])

  // Re-apply nodeColor when selection changes so the highlight is visible
  useEffect(() => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ;(graphRef.current as any)?.nodeColor((node: object) => {
      const n = node as GraphNode
      if (selectedNode && n.id === selectedNode.id) return '#ffffff'
      const alpha = Math.round((0.4 + (n.confidence ?? 0.5) * 0.6) * 255).toString(16).padStart(2, '0')
      return n.node_type === 'semantic' ? `#a78bfa${alpha}` : `#06b6d4${alpha}`
    })
  }, [selectedNode])

  // ── Overlay UI ───────────────────────────────────────────────────────────
  if (!webglAvailable) {
    return (
      <div style={{ width: '100%', height: '100%', overflow: 'auto', background: '#070a12', padding: '20px', color: '#94a3b8' }}>
        <div style={{ marginBottom: 12, display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ color: '#f59e0b', fontSize: 16 }}>⬡</span>
          <span style={{ fontSize: 13 }}>Grafo 3D non disponibile — WebGL disabilitato in questo ambiente</span>
          <span style={{ marginLeft: 'auto', fontSize: 11, color: '#475569' }}>
            Coerenza: <span style={{ color: '#06b6d4' }}>{(coherenceScore * 100).toFixed(0)}%</span>
          </span>
        </div>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
          <thead>
            <tr style={{ borderBottom: '1px solid #1e293b', color: '#475569', textAlign: 'left' }}>
              <th style={{ padding: '6px 8px' }}>Contenuto</th>
              <th style={{ padding: '6px 8px', width: 90 }}>Tipo</th>
              <th style={{ padding: '6px 8px', width: 60 }}>Conf.</th>
            </tr>
          </thead>
          <tbody>
            {nodes.map(n => (
              <tr key={n.id} style={{ borderBottom: '1px solid #0f172a' }}>
                <td style={{ padding: '6px 8px', color: '#e2e8f0', lineHeight: 1.4 }}>{n.content}</td>
                <td style={{ padding: '6px 8px', color: n.node_type === 'semantic' ? '#a78bfa' : '#06b6d4' }}>
                  {n.node_type === 'semantic' ? 'semantica' : 'credenza'}
                </td>
                <td style={{ padding: '6px 8px', color: '#94a3b8' }}>{(n.confidence * 100).toFixed(0)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
        {nodes.length === 0 && (
          <div style={{ textAlign: 'center', padding: '40px 0', color: '#475569' }}>Nessun nodo disponibile</div>
        )}
      </div>
    )
  }

  return (
    <div
      style={{ position: 'relative', width: '100%', height: '100%', overflow: 'hidden', background: '#070a12' }}
    >
      {/* 3D canvas mount point — 3d-force-graph renders into this div */}
      <div ref={mountRef} style={{ width: '100%', height: '100%' }} />

      {/* Relation filter pills — top left */}
      <div style={{
        position: 'absolute', top: 10, left: 10,
        display: 'flex', gap: 5, flexWrap: 'wrap',
        maxWidth: '480px',
        zIndex: 10,
      }}>
        {Object.entries(RELATION_CFG).map(([rel, cfg]) => {
          const off = hidden.has(rel)
          const cnt = relCounts[rel] ?? 0
          return (
            <button
              key={rel}
              onClick={() => toggleHidden(rel)}
              title={off ? `Mostra ${cfg.label}` : `Nascondi ${cfg.label}`}
              style={{
                display: 'flex', alignItems: 'center', gap: 4,
                background: off ? 'rgba(10,12,16,0.82)' : `${cfg.color}18`,
                border: `1px solid ${off ? '#1e293b' : cfg.color + '55'}`,
                borderRadius: 20, padding: '3px 9px',
                fontSize: 10, color: off ? '#334155' : cfg.color,
                cursor: 'pointer', backdropFilter: 'blur(6px)',
                transition: 'all 0.15s',
              }}
            >
              <span style={{ fontSize: 12 }}>{cfg.sym}</span>
              <span style={{ fontWeight: 600 }}>{cfg.label}</span>
              {cnt > 0 && (
                <span style={{
                  background: off ? '#1a2030' : `${cfg.color}28`,
                  borderRadius: 9, padding: '1px 5px', fontSize: 9,
                }}>{cnt}</span>
              )}
            </button>
          )
        })}
      </div>

      {/* Stats bar — bottom left */}
      <div style={{
        position: 'absolute', bottom: 10, left: 10,
        background: 'rgba(10,10,15,0.82)', border: '1px solid #1e293b',
        borderRadius: 6, padding: '5px 10px',
        fontSize: 11, color: '#94a3b8', backdropFilter: 'blur(6px)',
        display: 'flex', gap: 10, alignItems: 'center', zIndex: 10,
      }}>
        <span>Coerenza&nbsp;
          <span style={{ color: '#06b6d4', fontWeight: 600 }}>
            {(coherenceScore * 100).toFixed(0)}%
          </span>
        </span>
        <span style={{ color: '#1e293b' }}>·</span>
        <span>
          <span style={{ color: '#06b6d4' }}>●</span>
          &nbsp;{nodes.filter(n => n.node_type !== 'semantic').length} credenze
        </span>
        <span style={{ color: '#1e293b' }}>·</span>
        <span>
          <span style={{ color: '#a78bfa' }}>●</span>
          &nbsp;{nodes.filter(n => n.node_type === 'semantic').length} memorie
        </span>
        <span style={{ color: '#1e293b' }}>·</span>
        <span>{edges.length} relazioni</span>
        {(relCounts['CONTRADICTS'] ?? 0) > 0 && (
          <>
            <span style={{ color: '#1e293b' }}>·</span>
            <span style={{ color: '#f43f5e' }}>⚡ {relCounts['CONTRADICTS']} contraddizioni</span>
          </>
        )}
      </div>

      {/* Node detail panel — right side */}
      {selectedNode && (
        <div style={{
          position: 'absolute', top: 0, right: 0, bottom: 0, width: 272,
          background: 'rgba(8,10,15,0.95)', borderLeft: '1px solid #1e293b',
          backdropFilter: 'blur(14px)', display: 'flex', flexDirection: 'column',
          overflowY: 'auto', zIndex: 20,
        }}>
          {/* Header */}
          <div style={{
            padding: '11px 14px 9px', borderBottom: '1px solid #1e293b',
            display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
          }}>
            <div style={{ flex: 1 }}>
              <div style={{
                fontSize: 9, textTransform: 'uppercase',
                letterSpacing: '0.08em', marginBottom: 5,
                color: selectedNode.node_type === 'semantic' ? '#a78bfa' : '#475569',
              }}>
                {selectedNode.node_type === 'semantic' ? 'Memoria Semantica' : 'Credenza selezionata'}
              </div>
              <div style={{ fontSize: 12, color: '#e2e8f0', lineHeight: 1.55 }}>
                {selectedNode.content}
              </div>
            </div>
            <button
              onClick={() => setSelectedNode(null)}
              style={{
                background: 'none', border: 'none', color: '#475569',
                cursor: 'pointer', fontSize: 18, paddingLeft: 8,
                lineHeight: 1, flexShrink: 0,
              }}
            >×</button>
          </div>

          {/* Confidence / salience bar */}
          <div style={{ padding: '9px 14px', borderBottom: '1px solid #1e293b' }}>
            <div style={{
              fontSize: 9, color: '#475569', textTransform: 'uppercase',
              letterSpacing: '0.07em', marginBottom: 5,
            }}>
              {selectedNode.node_type === 'semantic' ? 'Salienza × Forza' : 'Confidenza'}
            </div>
            <div style={{ height: 4, background: '#1e293b', borderRadius: 2, overflow: 'hidden', marginBottom: 3 }}>
              <div style={{
                height: '100%', width: `${selectedNode.confidence * 100}%`,
                background: selectedNode.node_type === 'semantic' ? '#a78bfa' : '#06b6d4',
                borderRadius: 2,
              }} />
            </div>
            <div style={{ fontSize: 11, color: selectedNode.node_type === 'semantic' ? '#a78bfa' : '#06b6d4' }}>
              {(selectedNode.confidence * 100).toFixed(0)}%
            </div>
          </div>

          {/* Tags */}
          {selectedNode.tags.length > 0 && (
            <div style={{
              padding: '8px 14px', borderBottom: '1px solid #1e293b',
              display: 'flex', gap: 5, flexWrap: 'wrap',
            }}>
              {selectedNode.tags.map(tag => (
                <span key={tag} style={{
                  background: selectedNode.node_type === 'semantic' ? '#a78bfa1a' : '#06b6d41a',
                  border: `1px solid ${selectedNode.node_type === 'semantic' ? '#a78bfa' : '#06b6d4'}30`,
                  borderRadius: 10, padding: '2px 7px', fontSize: 10,
                  color: selectedNode.node_type === 'semantic' ? '#a78bfa' : '#06b6d4',
                }}>{tag}</span>
              ))}
            </div>
          )}

          {/* Relations list */}
          <div style={{ padding: '10px 14px', flex: 1 }}>
            <div style={{
              fontSize: 9, color: '#475569', textTransform: 'uppercase',
              letterSpacing: '0.08em', marginBottom: 8,
            }}>
              Relazioni ({nodeConnections.length})
            </div>
            {nodeConnections.length === 0 ? (
              <div style={{ fontSize: 11, color: '#334155', fontStyle: 'italic' }}>
                Nessuna relazione
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {nodeConnections.map((e, i) => {
                  const cfg = ALL_LINK_CFG[e.relation]
                  const isOut = e.source === selectedNode.id
                  const otherId = isOut ? e.target : e.source
                  const other = nodes.find(n => n.id === otherId)
                  return (
                    <div key={i} style={{
                      background: `${cfg?.color ?? '#475569'}0d`,
                      border: `1px solid ${cfg?.color ?? '#475569'}2e`,
                      borderRadius: 8, padding: '7px 10px',
                    }}>
                      <div style={{
                        display: 'flex', alignItems: 'center', gap: 5, marginBottom: 3,
                      }}>
                        <span style={{ color: cfg?.color ?? '#94a3b8', fontSize: 13 }}>
                          {cfg?.sym ?? '→'}
                        </span>
                        <span style={{
                          fontSize: 10, color: cfg?.color ?? '#94a3b8', fontWeight: 600,
                        }}>
                          {isOut ? (cfg?.label ?? e.relation) : `← ${cfg?.label ?? e.relation}`}
                        </span>
                        <span style={{ fontSize: 9, color: '#475569', marginLeft: 'auto' }}>
                          {(e.weight ?? 0).toFixed(2)}
                        </span>
                      </div>
                      <div style={{ fontSize: 11, color: '#94a3b8', lineHeight: 1.4 }}>
                        {other?.content ?? otherId}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
