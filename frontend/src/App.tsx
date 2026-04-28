import { useState, useCallback } from 'react'
import './index.css'
import './styles.css'
import ChatPanel from './components/ChatPanel'
import MemoryPanel from './components/MemoryPanel'
import IdentityGraph from './components/IdentityGraph'
import DriveChart from './components/DriveChart'
import DriveHistory from './components/DriveHistory'
import ConsolidationPanel from './components/ConsolidationPanel'
import { useEchoState, useHistory, useGraph, useMemories } from './hooks'
import type { MetaState } from './api'

type Tab = 'chat' | 'memory' | 'graph' | 'consolidation'

const DRIVE_COLORS: Record<string, string> = {
  coherence:   '#06b6d4',
  curiosity:   '#a78bfa',
  stability:   '#10b981',
  competence:  '#f59e0b',
  compression: '#f43f5e',
}

export default function App() {
  const [tab, setTab] = useState<Tab>('chat')
  const { state, error } = useEchoState()
  const history = useHistory()
  const { graph } = useGraph()
  const { memories, total } = useMemories()

  const handleMetaUpdate = useCallback((_ms: MetaState) => {
    // Live update from SSE response — state polling will sync shortly
  }, [])

  const drives = state?.meta_state.drives
  const agentWeights = state?.meta_state.agent_weights ?? {}

  return (
    <div className="app">
      {/* Header */}
      <header className="header">
        <span className="header-logo">◈ ECHO</span>
        <span className="header-subtitle">Persistent Self-Modifying Cognitive Architecture</span>
        <div className="header-status">
          <div className={`status-dot ${error ? 'offline' : ''}`} />
          {error ? 'Backend offline' : 'Connected'}
          {state && (
            <span style={{ marginLeft: 12, color: '#06b6d4' }}>
              {state.interaction_count} interactions
            </span>
          )}
        </div>
      </header>

      {/* Main panel */}
      <main className="main-panel">
        <div className="tab-bar">
          {(['chat', 'memory', 'graph', 'consolidation'] as Tab[]).map((t) => (
            <button key={t} className={`tab ${tab === t ? 'active' : ''}`} onClick={() => setTab(t)}>
              {t}
            </button>
          ))}
        </div>

        {tab === 'chat' && <ChatPanel onMetaStateUpdate={handleMetaUpdate} />}
        {tab === 'memory' && <MemoryPanel memories={memories} total={total} />}
        {tab === 'graph' && (
          <div className="graph-container" style={{ flex: 1 }}>
            <IdentityGraph nodes={graph.nodes} edges={graph.edges} />
            <div style={{
              position: 'absolute', bottom: 12, left: 12,
              background: 'rgba(10,10,15,0.8)',
              border: '1px solid #1e293b',
              borderRadius: 6,
              padding: '6px 10px',
              fontSize: 11,
              color: '#94a3b8',
            }}>
              Coherence: {(graph.coherence_score * 100).toFixed(0)}%
              &nbsp;·&nbsp;{graph.nodes.length} beliefs
            </div>
          </div>
        )}
        {tab === 'consolidation' && <ConsolidationPanel />}
      </main>

      {/* Right sidebar */}
      <aside className="sidebar">
        {/* Stats */}
        <div className="sidebar-section">
          <div className="sidebar-title">System State</div>
          <div className="stat-grid">
            <div className="stat-card">
              <div className="stat-label">Beliefs</div>
              <div className="stat-value">{state?.identity_beliefs ?? '—'}</div>
            </div>
            <div className="stat-card">
              <div className="stat-label">Memories</div>
              <div className="stat-value">{state?.episodic_memories ?? '—'}</div>
            </div>
            <div className="stat-card">
              <div className="stat-label">Workspace</div>
              <div className="stat-value">{state?.workspace_items ?? '—'}</div>
            </div>
            <div className="stat-card">
              <div className="stat-label">Valence</div>
              <div className="stat-value" style={{ fontSize: 14, paddingTop: 4 }}>
                {state ? (state.meta_state.emotional_valence >= 0 ? '+' : '') + state.meta_state.emotional_valence.toFixed(2) : '—'}
              </div>
            </div>
          </div>

          {/* Valence bar */}
          {state && (
            <div className="valence-bar-container" style={{ marginTop: 10 }}>
              <span className="valence-label">−1</span>
              <div className="valence-track">
                <div
                  className="valence-thumb"
                  style={{ left: `${((state.meta_state.emotional_valence + 1) / 2) * 100}%` }}
                />
              </div>
              <span className="valence-label" style={{ textAlign: 'left' }}>+1</span>
            </div>
          )}
        </div>

        {/* Drive gauges */}
        {drives && (
          <div className="sidebar-section">
            <div className="sidebar-title">Drive Competition</div>
            <DriveChart drives={drives} />
          </div>
        )}

        {/* Drive history */}
        <div className="sidebar-section">
          <div className="sidebar-title">Drive History</div>
          <DriveHistory history={history} />
        </div>

        {/* Agent weights */}
        {Object.keys(agentWeights).length > 0 && (
          <div className="sidebar-section">
            <div className="sidebar-title">Agent Routing Weights</div>
            {Object.entries(agentWeights).map(([agent, w]) => (
              <div key={agent} className="agent-weight-row">
                <span className="drive-name" style={{ width: 90 }}>{agent}</span>
                <div className="drive-bar-bg">
                  <div
                    className="drive-bar-fill"
                    style={{
                      width: `${Math.min(100, (w / 2) * 100)}%`,
                      background: '#7c3aed',
                    }}
                  />
                </div>
                <span className="drive-value">{w.toFixed(2)}</span>
              </div>
            ))}
          </div>
        )}
      </aside>
    </div>
  )
}
