/**
 * PipelinePanel — visualises the full response pipeline for each interaction.
 *
 * Shows: retrieval → self-prediction → learning engine priors →
 *        personalization → global workspace → (async) post-process.
 *
 * Polls /api/pipeline/trace every 1.5 s while active.
 */

import { usePipelineTrace } from '../hooks'
import type { PipelineTrace, PipelineWorkspaceItem } from '../api'

// ── Design tokens (match CSS vars) ──────────────────────────────────────────
const CLR = {
  retrieval:       '#22d3ee',  // cyan
  prediction:      '#a78bfa',  // violet
  learning:        '#fbbf24',  // amber
  personalization: '#34d399',  // emerald
  workspace:       '#60a5fa',  // blue
  postprocess:     '#fb7185',  // rose
  slate:           '#64748b',
}

// Source badge colour map (workspace items)
const SOURCE_CLR: Record<string, string> = {
  archivist:  '#22d3ee',
  self_model: '#a78bfa',
  learning:   '#fbbf24',
  pipeline:   '#60a5fa',
}
function sourceColor(s: string) { return SOURCE_CLR[s] ?? CLR.slate }

// ── Hex → CSS rgb(...) helper for rgba() usage ───────────────────────────────
function rgb(hex: string, alpha = 1): string {
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  return `rgba(${r},${g},${b},${alpha})`
}

// ── Sub-components ────────────────────────────────────────────────────────────

interface PhaseCardProps {
  color:    string
  label:    string
  icon:     string
  badge?:   string
  badgeClr?: string
  loading?: boolean
  children: React.ReactNode
}
function PhaseCard({ color, label, icon, badge, badgeClr, loading, children }: PhaseCardProps) {
  return (
    <div style={{
      background:    rgb(color, 0.04),
      border:        `1px solid ${rgb(color, 0.18)}`,
      borderLeft:    `3px solid ${color}`,
      borderRadius:  10,
      padding:       '13px 16px',
      marginBottom:  10,
    }}>
      {/* header row */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 10 }}>
        <span style={{ fontSize: 14 }}>{icon}</span>
        <span style={{
          fontSize: 10.5, fontWeight: 700, letterSpacing: '0.1em',
          textTransform: 'uppercase', color,
        }}>{label}</span>

        {badge && (
          <span style={{
            fontSize: 10, padding: '1px 7px', borderRadius: 20,
            background: rgb(badgeClr ?? color, 0.18),
            color: badgeClr ?? color,
            border: `1px solid ${rgb(badgeClr ?? color, 0.35)}`,
            marginLeft: 'auto',
          }}>{badge}</span>
        )}

        {loading && (
          <span style={{ marginLeft: badge ? 6 : 'auto', display: 'flex', alignItems: 'center', gap: 4 }}>
            <span style={{
              width: 7, height: 7, borderRadius: '50%',
              background: color, opacity: 0.9,
              animation: 'ppPulse 1.2s ease-in-out infinite',
            }} />
            <span style={{ fontSize: 10, color: '#64748b' }}>processing…</span>
          </span>
        )}
      </div>
      {children}
    </div>
  )
}

// Horizontal bar + value label
interface BarProps { label: string; value: number; color: string; pct?: boolean }
function Bar({ label, value, color, pct = true }: BarProps) {
  const display = pct ? `${(value * 100).toFixed(0)}%` : value.toFixed(2)
  const width   = Math.min(100, Math.round((pct ? value : value) * 100))
  return (
    <div style={{ marginBottom: 7 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
        <span style={{ fontSize: 11, color: '#8888aa' }}>{label}</span>
        <span style={{ fontSize: 11, color: '#c0c0d8', fontVariantNumeric: 'tabular-nums' }}>{display}</span>
      </div>
      <div style={{ height: 4, background: 'rgba(255,255,255,0.05)', borderRadius: 2 }}>
        <div style={{
          width: `${width}%`, height: '100%',
          background: color, borderRadius: 2,
          transition: 'width 0.5s cubic-bezier(.4,0,.2,1)',
          boxShadow: `0 0 6px ${rgb(color, 0.4)}`,
        }} />
      </div>
    </div>
  )
}

// Small "chip" pill
function Chip({ text, color }: { text: string; color: string }) {
  return (
    <span style={{
      display: 'inline-block', fontSize: 10.5, padding: '2px 8px', borderRadius: 20,
      background: rgb(color, 0.14), color,
      border: `1px solid ${rgb(color, 0.30)}`,
      marginRight: 5, marginBottom: 4,
    }}>{text}</span>
  )
}

// Badge for workspace source
function SourceBadge({ source }: { source: string }) {
  const c = sourceColor(source)
  return (
    <span style={{
      fontSize: 10, padding: '1px 6px', borderRadius: 4, flexShrink: 0,
      background: rgb(c, 0.18), color: c, border: `1px solid ${rgb(c, 0.30)}`,
      fontFamily: 'monospace',
    }}>{source}</span>
  )
}

// Divider
function Divider() {
  return <div style={{ height: 1, background: 'rgba(255,255,255,0.05)', margin: '8px 0' }} />
}

// Snippet text
function Snippet({ text }: { text: string }) {
  return (
    <p style={{
      fontSize: 11, color: '#7a7a9a', margin: '3px 0',
      whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
    }}>"{text}"</p>
  )
}

// ── Phase sections ────────────────────────────────────────────────────────────

function RetrievalSection({ trace }: { trace: PipelineTrace }) {
  const { episodic_count, semantic_count, episodic_snippets, semantic_snippets } = trace.retrieval
  const total = episodic_count + semantic_count
  return (
    <PhaseCard color={CLR.retrieval} label="Retrieval" icon="◈">
      <div style={{ display: 'flex', gap: 10, marginBottom: 8 }}>
        <StatPill label="Episodic" value={episodic_count} color={CLR.retrieval} />
        <StatPill label="Semantic" value={semantic_count} color={CLR.prediction} />
        <StatPill label="Total"    value={total}          color={CLR.slate} />
      </div>
      {episodic_snippets.length > 0 && (
        <>
          <span style={{ fontSize: 10, color: '#44445a', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Episodic</span>
          {episodic_snippets.map((s, i) => <Snippet key={i} text={s} />)}
        </>
      )}
      {semantic_snippets.length > 0 && (
        <>
          <Divider />
          <span style={{ fontSize: 10, color: '#44445a', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Semantic</span>
          {semantic_snippets.map((s, i) => <Snippet key={i} text={s} />)}
        </>
      )}
      {total === 0 && (
        <p style={{ fontSize: 11, color: '#44445a', fontStyle: 'italic' }}>No memories retrieved</p>
      )}
    </PhaseCard>
  )
}

function StatPill({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div style={{
      flex: 1, textAlign: 'center', padding: '6px 4px',
      background: 'rgba(255,255,255,0.03)', borderRadius: 6,
      border: '1px solid rgba(255,255,255,0.05)',
    }}>
      <div style={{ fontSize: 16, fontWeight: 700, color, lineHeight: 1.1 }}>{value}</div>
      <div style={{ fontSize: 9.5, color: '#44445a', textTransform: 'uppercase', letterSpacing: '0.07em', marginTop: 1 }}>{label}</div>
    </div>
  )
}

function SelfPredictionSection({ trace }: { trace: PipelineTrace }) {
  const text = trace.self_prediction
  return (
    <PhaseCard color={CLR.prediction} label="Self-Prediction" icon="◎">
      {text
        ? (
          <p style={{
            fontSize: 12, color: '#c4b5fd', lineHeight: 1.6,
            background: rgb(CLR.prediction, 0.07), borderRadius: 6,
            padding: '8px 10px', margin: 0,
            borderLeft: `2px solid ${rgb(CLR.prediction, 0.4)}`,
          }}>{text}</p>
        )
        : <p style={{ fontSize: 11, color: '#44445a', fontStyle: 'italic' }}>No prediction generated</p>
      }
    </PhaseCard>
  )
}

function LearningSection({ trace }: { trace: PipelineTrace }) {
  const lp  = trace.learning_priors
  const notable = lp.is_notable
  return (
    <PhaseCard
      color={CLR.learning} label="Learning Engine" icon="◇"
      badge={notable ? '★ NOTABLE' : undefined}
      badgeClr={CLR.learning}
    >
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 16px' }}>
        <Bar label="Curiosity spike"   value={lp.curiosity_spike_prob}       color={CLR.learning} />
        <Bar label="Identity drift risk" value={lp.identity_drift_risk}      color={CLR.postprocess} />
        <Bar label="Consolidation urgency" value={lp.consolidation_urgency}  color={CLR.prediction} />
        <Bar label="Valence forecast"  value={(lp.emotional_valence_forecast + 1) / 2} color={CLR.retrieval} />
      </div>

      {lp.workspace_items.length > 0 && (
        <>
          <Divider />
          <span style={{ fontSize: 10, color: '#44445a', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            Injected priors ({lp.workspace_items.length})
          </span>
          <div style={{ marginTop: 5, display: 'flex', flexDirection: 'column', gap: 4 }}>
            {lp.workspace_items.map(([content, sal], i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <div style={{ flex: 1, height: 3, background: 'rgba(255,255,255,0.04)', borderRadius: 2 }}>
                  <div style={{ width: `${Math.round(sal * 100)}%`, height: '100%', background: CLR.learning, borderRadius: 2 }} />
                </div>
                <span style={{ fontSize: 10, color: '#7a7a9a', flex: 5,
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {content}
                </span>
                <span style={{ fontSize: 10, color: CLR.learning, minWidth: 28, textAlign: 'right' }}>
                  {sal.toFixed(2)}
                </span>
              </div>
            ))}
          </div>
        </>
      )}
    </PhaseCard>
  )
}

function PersonalizationSection({ trace }: { trace: PipelineTrace }) {
  const p = trace.personalization
  return (
    <PhaseCard color={CLR.personalization} label="Personalization" icon="⬡"
      badge={`${p.n_observations} obs`} badgeClr={CLR.slate}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 16px' }}>
        <Bar label="Verbosity"      value={p.verbosity}       color={CLR.personalization} />
        <Bar label="Topic depth"    value={p.topic_depth}     color={CLR.retrieval} />
        <Bar label="Recall freq."   value={p.recall_frequency} color={CLR.prediction} />
      </div>
      {p.style_hint && (
        <>
          <Divider />
          <p style={{ fontSize: 11, color: '#6ee7b7', fontStyle: 'italic', margin: 0 }}>
            {p.style_hint}
          </p>
        </>
      )}
    </PhaseCard>
  )
}

function WorkspaceSection({ trace }: { trace: PipelineTrace }) {
  const items = trace.workspace_items
  const sorted = [...items].sort((a, b) => b.competition_score - a.competition_score)
  return (
    <PhaseCard color={CLR.workspace} label="Global Workspace" icon="⬣"
      badge={`${items.length} items`} badgeClr={CLR.workspace}>
      {sorted.length === 0 && (
        <p style={{ fontSize: 11, color: '#44445a', fontStyle: 'italic' }}>Workspace empty</p>
      )}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
        {sorted.map((item, i) => <WorkspaceItemRow key={i} item={item} />)}
      </div>
    </PhaseCard>
  )
}

function WorkspaceItemRow({ item }: { item: PipelineWorkspaceItem }) {
  const compPct = Math.round(item.competition_score * 100)
  const salPct  = Math.round(item.salience * 100)
  return (
    <div style={{
      background:   'rgba(255,255,255,0.025)',
      border:       '1px solid rgba(255,255,255,0.05)',
      borderRadius: 6, padding: '7px 8px',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 5 }}>
        <SourceBadge source={item.source} />
        <span style={{
          fontSize: 11, color: '#9090b0',
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1,
        }}>{item.content}</span>
      </div>
      <div style={{ display: 'flex', gap: 10 }}>
        {/* competition score bar */}
        <div style={{ flex: 3 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 2 }}>
            <span style={{ fontSize: 9.5, color: '#44445a' }}>competition</span>
            <span style={{ fontSize: 9.5, color: '#7070a0' }}>{compPct}%</span>
          </div>
          <div style={{ height: 3, background: 'rgba(255,255,255,0.05)', borderRadius: 2 }}>
            <div style={{
              width: `${compPct}%`, height: '100%', borderRadius: 2,
              background: `linear-gradient(90deg, ${CLR.workspace}, ${CLR.retrieval})`,
            }} />
          </div>
        </div>
        {/* salience mini */}
        <div style={{ flex: 2 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 2 }}>
            <span style={{ fontSize: 9.5, color: '#44445a' }}>salience</span>
            <span style={{ fontSize: 9.5, color: '#7070a0' }}>{salPct}%</span>
          </div>
          <div style={{ height: 3, background: 'rgba(255,255,255,0.05)', borderRadius: 2 }}>
            <div style={{
              width: `${salPct}%`, height: '100%', borderRadius: 2,
              background: CLR.learning,
            }} />
          </div>
        </div>
      </div>
    </div>
  )
}

function PostProcessSection({ trace }: { trace: PipelineTrace }) {
  const done = trace.post_interact_complete
  const ds   = trace.drive_scores
  const err  = trace.prediction_error

  return (
    <PhaseCard color={CLR.postprocess} label="Post-Process" icon="◈"
      loading={!done}
      badge={done ? 'complete' : undefined}
      badgeClr={CLR.postprocess}>

      {!done && (
        <p style={{ fontSize: 11, color: '#7a7a9a', fontStyle: 'italic', marginBottom: 8 }}>
          Awaiting async evaluation…
        </p>
      )}

      {done && (
        <>
          {/* Drive scores */}
          {Object.keys(ds).length > 0 && (
            <>
              <span style={{ fontSize: 10, color: '#44445a', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                Drive updates
              </span>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 16px', marginTop: 5 }}>
                {Object.entries(ds).map(([k, v]) => (
                  <Bar key={k} label={k} value={Math.max(0, v)} color={CLR.postprocess} />
                ))}
              </div>
              <Divider />
            </>
          )}

          {/* Prediction error */}
          {err !== null && err !== undefined && (
            <Bar label="Prediction error" value={err} color={err > 0.5 ? CLR.postprocess : CLR.retrieval} />
          )}

          {/* Valence / Arousal after */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 16px', marginTop: 4 }}>
            {trace.valence_after !== null && trace.valence_after !== undefined && (
              <Bar label="Valence (after)"  value={(trace.valence_after + 1) / 2}  color={CLR.prediction} />
            )}
            {trace.arousal_after !== null && trace.arousal_after !== undefined && (
              <Bar label="Arousal (after)"  value={trace.arousal_after}            color={CLR.learning} />
            )}
          </div>

          {/* Identity drift + response length */}
          <div style={{ display: 'flex', gap: 6, marginTop: 6, flexWrap: 'wrap' }}>
            <Chip text={`drift: ${trace.identity_drift.toFixed(3)}`}  color={CLR.postprocess} />
            {trace.response_length !== null && trace.response_length !== undefined &&
              <Chip text={`${trace.response_length} chars`} color={CLR.slate} />
            }
          </div>
        </>
      )}
    </PhaseCard>
  )
}

// ── State-change summary (response transform delta) ──────────────────────────
function DeltaSummary({ trace }: { trace: PipelineTrace }) {
  const done         = trace.post_interact_complete
  const valenceDelta = done && trace.valence_after !== null
    ? trace.valence_after! - trace.valence_before
    : null
  const arousalDelta = done && trace.arousal_after !== null
    ? trace.arousal_after! - trace.arousal_before
    : null

  const styleHint = trace.personalization.style_hint
  const priorCount = trace.learning_priors.workspace_items.length
  const wsCount    = trace.workspace_items.length

  return (
    <div style={{
      background:   'rgba(255,255,255,0.02)',
      border:       '1px solid rgba(255,255,255,0.06)',
      borderRadius: 10, padding: '12px 16px', marginBottom: 10,
    }}>
      <div style={{ fontSize: 10, color: '#44445a', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8 }}>
        Response transform
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
        <Chip text={`${priorCount} learning priors`} color={CLR.learning} />
        <Chip text={`${wsCount} workspace items`}    color={CLR.workspace} />
        {styleHint && <Chip text={styleHint.length > 30 ? styleHint.slice(0, 30) + '…' : styleHint} color={CLR.personalization} />}
        {valenceDelta !== null && (
          <Chip
            text={`Δvalence ${valenceDelta >= 0 ? '+' : ''}${valenceDelta.toFixed(2)}`}
            color={valenceDelta >= 0 ? CLR.retrieval : CLR.postprocess}
          />
        )}
        {arousalDelta !== null && (
          <Chip
            text={`Δarousal ${arousalDelta >= 0 ? '+' : ''}${arousalDelta.toFixed(2)}`}
            color={CLR.learning}
          />
        )}
      </div>
    </div>
  )
}

// ── Empty / loading state ─────────────────────────────────────────────────────
function EmptyState() {
  return (
    <div style={{
      display:        'flex', flexDirection: 'column', alignItems: 'center',
      justifyContent: 'center', height: '100%', gap: 14, padding: 40,
    }}>
      <div style={{
        width: 56, height: 56, borderRadius: '50%',
        background:  `linear-gradient(135deg, ${rgb(CLR.retrieval, 0.15)}, ${rgb(CLR.prediction, 0.15)})`,
        border:      `2px solid ${rgb(CLR.retrieval, 0.25)}`,
        display:     'flex', alignItems: 'center', justifyContent: 'center',
        fontSize:    24, color: CLR.retrieval,
      }}>◈</div>
      <div style={{ textAlign: 'center' }}>
        <p style={{ fontSize: 14, fontWeight: 600, color: '#8888aa', margin: 0 }}>
          No pipeline trace yet
        </p>
        <p style={{ fontSize: 12, color: '#44445a', marginTop: 4 }}>
          Send a message to visualise the response pipeline
        </p>
      </div>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

interface Props {
  active: boolean
}

export default function PipelinePanel({ active }: Props) {
  const { trace } = usePipelineTrace(active)

  if (!trace) return <EmptyState />

  // Format timestamp
  const ts = new Date(trace.timestamp)
  const timeStr = ts.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  const idShort  = trace.interaction_id.slice(-8)

  return (
    <>
      {/* pulse keyframes (injected once) */}
      <style>{`
        @keyframes ppPulse {
          0%, 100% { opacity: 1; transform: scale(1); }
          50%       { opacity: .4; transform: scale(.75); }
        }
      `}</style>

      {/* panel */}
      <div style={{
        height:    '100%',
        overflowY: 'auto',
        padding:   '16px 16px 40px',
      }}>
        {/* ── Header ── */}
        <div style={{
          display:       'flex', alignItems: 'center', gap: 10,
          marginBottom:  14, paddingBottom: 12,
          borderBottom:  '1px solid rgba(255,255,255,0.06)',
        }}>
          <div style={{
            width:      30, height: 30, borderRadius: '50%',
            background: `linear-gradient(135deg, ${CLR.retrieval}, ${CLR.prediction})`,
            display:    'flex', alignItems: 'center', justifyContent: 'center',
            fontSize:   14, color: '#fff', flexShrink: 0,
          }}>◈</div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: '#e0e0f0' }}>Pipeline Trace</div>
            <div style={{ fontSize: 10.5, color: '#44445a', marginTop: 1 }}>
              {timeStr} · id:{idShort}
            </div>
          </div>
          {/* post_interact status dot */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
            <span style={{
              width: 7, height: 7, borderRadius: '50%',
              background:  trace.post_interact_complete ? CLR.personalization : CLR.learning,
              boxShadow:   trace.post_interact_complete
                ? `0 0 6px ${rgb(CLR.personalization, 0.5)}`
                : `0 0 6px ${rgb(CLR.learning, 0.5)}`,
              animation:   trace.post_interact_complete ? 'none' : 'ppPulse 1.2s infinite',
            }} />
            <span style={{ fontSize: 10, color: '#44445a' }}>
              {trace.post_interact_complete ? 'complete' : 'processing'}
            </span>
          </div>
        </div>

        {/* ── Response transform summary ── */}
        <DeltaSummary trace={trace} />

        {/* ── Phase timeline ── */}
        <div style={{ position: 'relative' }}>
          {/* vertical connector line */}
          <div style={{
            position:   'absolute', left: 14, top: 24, bottom: 24,
            width:       2, background: 'rgba(255,255,255,0.04)',
            borderRadius: 1, zIndex: 0,
          }} />

          <div style={{ position: 'relative', zIndex: 1 }}>
            <RetrievalSection       trace={trace} />
            <SelfPredictionSection  trace={trace} />
            <LearningSection        trace={trace} />
            <PersonalizationSection trace={trace} />
            <WorkspaceSection       trace={trace} />
            <PostProcessSection     trace={trace} />
          </div>
        </div>

        {/* ── Before/after state snapshot ── */}
        {trace.post_interact_complete && (
          <div style={{
            background:   'rgba(255,255,255,0.02)',
            border:       '1px solid rgba(255,255,255,0.06)',
            borderRadius: 10, padding: '12px 16px', marginTop: 4,
          }}>
            <div style={{ fontSize: 10, color: '#44445a', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8 }}>
              State snapshot
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 24px' }}>
              <div>
                <span style={{ fontSize: 10, color: '#44445a' }}>Valence before / after</span>
                <div style={{ fontSize: 13, fontWeight: 600, color: '#c0c0d8', marginTop: 2 }}>
                  {trace.valence_before.toFixed(3)}
                  <span style={{ color: '#44445a', margin: '0 4px' }}>→</span>
                  {trace.valence_after?.toFixed(3) ?? '—'}
                </div>
              </div>
              <div>
                <span style={{ fontSize: 10, color: '#44445a' }}>Arousal before / after</span>
                <div style={{ fontSize: 13, fontWeight: 600, color: '#c0c0d8', marginTop: 2 }}>
                  {trace.arousal_before.toFixed(3)}
                  <span style={{ color: '#44445a', margin: '0 4px' }}>→</span>
                  {trace.arousal_after?.toFixed(3) ?? '—'}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </>
  )
}
