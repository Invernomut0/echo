import { useState, useCallback, Component } from 'react'
import type { ReactNode } from 'react'
import { Settings } from 'lucide-react'
import './index.css'
import './styles.css'
import ChatPanel from './components/ChatPanel'
import PipelinePanel from './components/PipelinePanel'
import IdentityGraph from './components/IdentityGraph'
import DriveChart from './components/DriveChart'
import DriveHistory from './components/DriveHistory'
import ConsolidationPanel from './components/ConsolidationPanel'
import SetupPanel from './components/SetupPanel'
import AnalyticsPanel from './components/AnalyticsPanel'
import VectorMemoriesPanel from './components/VectorMemoriesPanel'
import CuriosityPanel from './components/CuriosityPanel'
import WikiGraphPanel from './components/WikiGraphPanel'
import GoalsPanel from './components/GoalsPanel'
import { useEchoState, useHistory, useAnalyticsHistory, useGraph } from './hooks'
import type { MetaState } from './api'

type Tab = 'chat' | 'pipeline' | 'graph' | 'consolidation' | 'analytics' | 'vectors' | 'curiosity' | 'wiki' | 'goals' | 'setup'

class GraphErrorBoundary extends Component<{ children: ReactNode }, { hasError: boolean }> {
  state = { hasError: false }
  static getDerivedStateFromError() { return { hasError: true } }
  componentDidCatch(err: Error) { console.warn('[IdentityGraph] caught error:', err.message) }
  render() {
    if (this.state.hasError) {
      return (
        <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#070a12', color: '#475569', fontSize: 13 }}>
          ⬡ Grafo non disponibile in questo ambiente
        </div>
      )
    }
    return this.props.children
  }
}

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
  const analyticsHistory = useAnalyticsHistory()
  const { graph } = useGraph(tab === 'graph')
  const handleMetaUpdate = useCallback((_ms: MetaState) => {
    // intentionally left empty — pipeline trace polls independently
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
          {(['chat', 'pipeline', 'graph', 'consolidation', 'analytics', 'vectors', 'curiosity', 'wiki', 'goals'] as Tab[]).map((t) => (
            <button key={t} className={`tab ${tab === t ? 'active' : ''}`} onClick={() => setTab(t)}>
              {t}
            </button>
          ))}
          <button
            className={`tab tab--icon ${tab === 'setup' ? 'active' : ''}`}
            onClick={() => setTab('setup')}
            title="Setup"
          >
            <Settings size={14} />
          </button>
        </div>

        {/* Always mounted — hidden with CSS so state survives tab switches */}
        <div style={{ display: tab === 'chat' ? 'contents' : 'none' }}>
          <ChatPanel onMetaStateUpdate={handleMetaUpdate} />
        </div>
        <div style={{ display: tab === 'pipeline' ? 'contents' : 'none' }}>
          <PipelinePanel active={tab === 'pipeline'} />
        </div>
        <div
          className="graph-container"
          style={{ display: tab === 'graph' ? 'flex' : 'none', flex: 1 }}
        >
          <GraphErrorBoundary>
            <IdentityGraph nodes={graph.nodes} edges={graph.edges} coherenceScore={graph.coherence_score} />
          </GraphErrorBoundary>
        </div>
        <div style={{ display: tab === 'consolidation' ? 'contents' : 'none' }}>
          <ConsolidationPanel />
        </div>
        <div style={{ display: tab === 'analytics' ? 'contents' : 'none' }}>
          <AnalyticsPanel history={analyticsHistory} />
        </div>
        <div style={{ display: tab === 'vectors' ? 'contents' : 'none' }}>
          <VectorMemoriesPanel />
        </div>
        <div style={{ display: tab === 'curiosity' ? 'contents' : 'none' }}>
          <CuriosityPanel />
        </div>
        <div
          style={{ display: tab === 'wiki' ? 'flex' : 'none', flex: 1, height: '100%' }}
        >
          <WikiGraphPanel active={tab === 'wiki'} />
        </div>
        <div style={{ display: tab === 'goals' ? 'contents' : 'none' }}>
          <GoalsPanel active={tab === 'goals'} />
        </div>
        <div style={{ display: tab === 'setup' ? 'contents' : 'none' }}>
          <SetupPanel />
        </div>
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
