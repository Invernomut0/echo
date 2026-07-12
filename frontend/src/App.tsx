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
import EchoMdPanel from './components/EchoMdPanel'
import CronPanel from './components/CronPanel'
import HeartbeatPanel from './components/HeartbeatPanel'
import { useEchoState, useHistory, useAnalyticsHistory, useGraph } from './hooks'
import type { MetaState } from './api'

type Tab = 'chat' | 'pipeline' | 'memory' | 'consolidation' | 'analytics' | 'vectors' | 'curiosity' | 'wiki' | 'goals' | 'echo' | 'cron' | 'heartbeat' | 'setup'

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
  const { graph } = useGraph(tab === 'memory')
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
          <span style={{ color: error ? '#ef4444' : '#22c55e', fontWeight: 600 }}>
            {error ? 'Backend offline' : 'Connected'}
          </span>
          {state && (
            <>
              <span style={{ marginLeft: 12, color: '#06b6d4' }}>
                {state.interaction_count} interactions
              </span>
              {state.llm_provider && (
                <span style={{ marginLeft: 10, color: '#94a3b8', fontSize: 11, fontFamily: 'monospace' }}>
                  {state.llm_provider}/{state.llm_model}
                </span>
              )}
            </>
          )}
        </div>
      </header>

      {/* Main panel */}
      <main className="main-panel">
        <div className="tab-bar">
          {(['chat', 'pipeline', 'memory', 'consolidation', 'analytics', 'vectors', 'curiosity', 'wiki', 'goals', 'echo', 'cron', 'heartbeat'] as Tab[]).map((t) => (
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
          style={{ display: tab === 'memory' ? 'flex' : 'none', flex: 1 }}
        >
          <GraphErrorBoundary>
            <IdentityGraph
              nodes={graph.nodes}
              edges={graph.edges}
              coherenceScore={graph.coherence_score}
              active={tab === 'memory'}
            />
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
        <div style={{ display: tab === 'echo' ? 'contents' : 'none' }}>
          <EchoMdPanel />
        </div>
        <div style={{ display: tab === 'cron' ? 'contents' : 'none' }}>
          <CronPanel active={tab === 'cron'} />
        </div>
        <div style={{ display: tab === 'heartbeat' ? 'contents' : 'none' }}>
          <HeartbeatPanel active={tab === 'heartbeat'} />
        </div>
        <div style={{ display: tab === 'setup' ? 'contents' : 'none' }}>
          <SetupPanel />
        </div>
      </main>

      {/* Right sidebar */}
      <aside className="sidebar">
        {/* Sentiment / mood display */}
        {state && (() => {
          const v = state.meta_state.emotional_valence
          const d = state.meta_state.drives
          // Mood emoji based on valence
          const moodEmoji = v < -0.5 ? '😔' : v < -0.2 ? '😕' : v < 0.05 ? '😐' : v < 0.3 ? '🙂' : v < 0.6 ? '😊' : '🤩'
          const moodLabel = v < -0.5 ? 'Distressed' : v < -0.2 ? 'Uneasy' : v < 0.05 ? 'Neutral' : v < 0.3 ? 'Calm' : v < 0.6 ? 'Content' : 'Enthusiastic'
          const moodColor = v < -0.3 ? '#ef4444' : v < 0.1 ? '#94a3b8' : v < 0.4 ? '#22c55e' : '#06b6d4'
          // Drive emoji indicators
          const driveRows: [string, string, number][] = [
            ['🔗', 'Coherence',  d.coherence],
            ['🔍', 'Curiosity',  d.curiosity],
            ['🏔️', 'Stability',  d.stability],
            ['💡', 'Competence', d.competence],
          ]
          const fillBar = (val: number, color: string) => {
            const blocks = Math.round(val * 8)
            return Array.from({ length: 8 }, (_, i) => (
              <span key={i} style={{
                display: 'inline-block', width: 8, height: 8, borderRadius: 2,
                margin: '0 1px',
                background: i < blocks ? color : 'rgba(255,255,255,0.08)',
              }} />
            ))
          }
          return (
            <div className="sidebar-section">
              <div className="sidebar-title">System State</div>

              {/* Central mood indicator */}
              <div style={{ textAlign: 'center', padding: '12px 0 8px' }}>
                <div style={{ fontSize: 48, lineHeight: 1.1 }}>{moodEmoji}</div>
                <div style={{ color: moodColor, fontWeight: 600, fontSize: 13, marginTop: 4 }}>{moodLabel}</div>
                <div style={{ color: '#64748b', fontSize: 11, marginTop: 2 }}>
                  valence {v >= 0 ? '+' : ''}{v.toFixed(2)}
                </div>
              </div>

              {/* Drive mini bars */}
              <div style={{ padding: '4px 0 8px' }}>
                {driveRows.map(([icon, label, val]) => (
                  <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 5 }}>
                    <span style={{ fontSize: 13, width: 20 }}>{icon}</span>
                    <span style={{ fontSize: 10, color: '#64748b', width: 62 }}>{label}</span>
                    <div>{fillBar(val, val > 0.7 ? '#06b6d4' : val > 0.4 ? '#22c55e' : '#f59e0b')}</div>
                    <span style={{ fontSize: 10, color: '#475569', marginLeft: 2 }}>{(val * 100).toFixed(0)}%</span>
                  </div>
                ))}
              </div>

              {/* Stats row */}
              <div className="stat-grid" style={{ marginTop: 4 }}>
                <div className="stat-card">
                  <div className="stat-label">Beliefs</div>
                  <div className="stat-value">{state.identity_beliefs}</div>
                </div>
                <div className="stat-card">
                  <div className="stat-label">Memories</div>
                  <div className="stat-value">{state.episodic_memories}</div>
                </div>
                <div className="stat-card">
                  <div className="stat-label">Workspace</div>
                  <div className="stat-value">{state.workspace_items}</div>
                </div>
                <div className="stat-card">
                  <div className="stat-label">Turns</div>
                  <div className="stat-value">{state.interaction_count}</div>
                </div>
              </div>
            </div>
          )
        })()}

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
