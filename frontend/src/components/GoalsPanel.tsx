import { useEffect, useRef, useState } from 'react'
import {
  type Goal,
  type GoalAction,
  type GoalsResponse,
  addGoalAction,
  createGoal,
  deleteGoal,
  fetchGoals,
  updateGoalStatus,
} from '../api'

// ── Colour helpers ─────────────────────────────────────────────────────────────

const STATUS_COLOR: Record<string, string> = {
  active: '#06b6d4',
  achieved: '#10b981',
  abandoned: '#475569',
}

const ACTION_COLOR: Record<string, string> = {
  done: '#10b981',
  failed: '#ef4444',
  pending: '#f59e0b',
}

function completionBar(goal: Goal) {
  let pct: number
  if (goal.status === 'achieved') {
    pct = 100
  } else if (goal.actions.length === 0) {
    pct = 0
  } else {
    const done = goal.actions.filter(a => a.status === 'done').length
    pct = Math.round((done / goal.actions.length) * 100)
  }
  const color = pct === 100 ? '#10b981' : pct >= 50 ? '#06b6d4' : '#f59e0b'
  const priorityPct = Math.round(goal.priority * 100)
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '5px', fontSize: '11px', color: '#94a3b8' }}>
      {/* Completion bar */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
        <span style={{ minWidth: '70px' }}>Completion</span>
        <div style={{ flex: 1, background: '#1e293b', borderRadius: '4px', height: '6px', minWidth: '80px' }}>
          <div style={{ width: `${pct}%`, height: '100%', borderRadius: '4px', background: color, transition: 'width .4s' }} />
        </div>
        <span style={{ color, fontWeight: 600, minWidth: '32px', textAlign: 'right' }}>{pct}%</span>
      </div>
      {/* Priority as number only */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#475569' }}>
        <span style={{ minWidth: '70px' }}>Priority</span>
        <span style={{ fontWeight: 600, color: priorityPct >= 70 ? '#f97316' : priorityPct >= 40 ? '#94a3b8' : '#475569' }}>
          {priorityPct}%
        </span>
      </div>
    </div>
  )
}

// ── Action timeline ────────────────────────────────────────────────────────────

function ActionTimeline({ actions }: { actions: GoalAction[] }) {
  if (!actions.length) return <div style={{ color: '#475569', fontSize: '12px', padding: '8px 0' }}>No actions logged yet.</div>
  return (
    <div style={{ borderLeft: '2px solid #1e293b', paddingLeft: '12px', marginTop: '8px' }}>
      {actions.map((a) => (
        <div key={a.id} style={{ marginBottom: '10px', position: 'relative' }}>
          <div style={{
            position: 'absolute', left: '-17px', top: '4px',
            width: '10px', height: '10px', borderRadius: '50%',
            background: ACTION_COLOR[a.status] ?? '#94a3b8',
            border: '2px solid #0f172a',
          }} />
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center', marginBottom: '2px' }}>
            <span style={{
              fontSize: '10px', fontWeight: 700, color: '#475569',
              background: '#1e293b', borderRadius: '4px', padding: '1px 5px',
            }}>#{a.step}</span>
            <span style={{
              fontSize: '10px', fontWeight: 600,
              color: ACTION_COLOR[a.status] ?? '#94a3b8',
              textTransform: 'uppercase', letterSpacing: '.04em',
            }}>{a.status}</span>
            <span style={{ fontSize: '10px', color: '#475569', marginLeft: 'auto' }}>
              {new Date(a.created_at).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' })}
            </span>
          </div>
          <div style={{ fontSize: '12px', color: '#cbd5e1' }}>{a.description}</div>
          {a.result && <div style={{ fontSize: '11px', color: '#94a3b8', marginTop: '2px', fontStyle: 'italic' }}>{a.result}</div>}
        </div>
      ))}
    </div>
  )
}

// ── Goal card ──────────────────────────────────────────────────────────────────

function GoalCard({
  goal,
  onUpdate,
  onDelete,
  onAddAction,
}: {
  goal: Goal
  onUpdate: (id: string, data: Partial<{ status: Goal['status']; description: string }>) => Promise<void>
  onDelete: (id: string) => Promise<void>
  onAddAction: (id: string, description: string, result?: string) => Promise<void>
}) {
  const [expanded, setExpanded] = useState(false)
  const [addingAction, setAddingAction] = useState(false)
  const [actionDesc, setActionDesc] = useState('')
  const [actionResult, setActionResult] = useState('')
  const [busy, setBusy] = useState(false)

  const statusColor = STATUS_COLOR[goal.status] ?? '#94a3b8'
  const isActive = goal.status === 'active'

  return (
    <div style={{
      background: '#0f172a',
      border: `1px solid ${statusColor}33`,
      borderLeft: `3px solid ${statusColor}`,
      borderRadius: '8px',
      padding: '14px 16px',
      marginBottom: '10px',
    }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '8px' }}>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
            <span style={{
              fontSize: '10px', fontWeight: 700, color: statusColor,
              textTransform: 'uppercase', letterSpacing: '.06em',
              background: `${statusColor}22`, borderRadius: '4px', padding: '1px 6px',
            }}>{goal.status}</span>
            {goal.tags.map(t => (
              <span key={t} style={{
                fontSize: '10px', color: '#64748b',
                background: '#1e293b', borderRadius: '4px', padding: '1px 5px',
              }}>#{t}</span>
            ))}
          </div>
          <div style={{ fontSize: '14px', fontWeight: 600, color: '#f1f5f9', marginBottom: '4px' }}>{goal.title}</div>
          {goal.description && <div style={{ fontSize: '12px', color: '#94a3b8', marginBottom: '8px' }}>{goal.description}</div>}
          {completionBar(goal)}
        </div>
        {/* Expand toggle */}
        <button
          onClick={() => setExpanded(e => !e)}
          style={{ background: 'none', border: 'none', color: '#475569', cursor: 'pointer', padding: '4px', fontSize: '14px' }}
          title={expanded ? 'Collapse' : 'Expand actions'}
        >
          {expanded ? '▲' : '▼'} {goal.actions.length}
        </button>
      </div>

      {/* Action buttons */}
      {isActive && (
        <div style={{ display: 'flex', gap: '8px', marginTop: '10px', flexWrap: 'wrap' }}>
          <button
            disabled={busy}
            onClick={async () => { setBusy(true); await onUpdate(goal.id, { status: 'achieved' }); setBusy(false) }}
            style={{
              fontSize: '11px', padding: '3px 10px', borderRadius: '5px', cursor: 'pointer',
              background: '#052e16', color: '#10b981', border: '1px solid #10b981',
            }}
          >✓ Achieved</button>
          <button
            disabled={busy}
            onClick={async () => { setBusy(true); await onUpdate(goal.id, { status: 'abandoned' }); setBusy(false) }}
            style={{
              fontSize: '11px', padding: '3px 10px', borderRadius: '5px', cursor: 'pointer',
              background: '#1e293b', color: '#94a3b8', border: '1px solid #334155',
            }}
          >✕ Abandon</button>
          <button
            onClick={() => setAddingAction(a => !a)}
            style={{
              fontSize: '11px', padding: '3px 10px', borderRadius: '5px', cursor: 'pointer',
              background: '#0c1a2e', color: '#06b6d4', border: '1px solid #06b6d4',
            }}
          >+ Log action</button>
        </div>
      )}

      {/* Manual action form */}
      {addingAction && (
        <div style={{ marginTop: '10px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <input
            value={actionDesc}
            onChange={e => setActionDesc(e.target.value)}
            placeholder="Action description…"
            style={{
              background: '#1e293b', border: '1px solid #334155', borderRadius: '5px',
              color: '#f1f5f9', padding: '5px 8px', fontSize: '12px',
            }}
          />
          <input
            value={actionResult}
            onChange={e => setActionResult(e.target.value)}
            placeholder="Result / notes (optional)…"
            style={{
              background: '#1e293b', border: '1px solid #334155', borderRadius: '5px',
              color: '#f1f5f9', padding: '5px 8px', fontSize: '12px',
            }}
          />
          <div style={{ display: 'flex', gap: '6px' }}>
            <button
              disabled={!actionDesc.trim() || busy}
              onClick={async () => {
                setBusy(true)
                await onAddAction(goal.id, actionDesc.trim(), actionResult.trim() || undefined)
                setActionDesc('')
                setActionResult('')
                setAddingAction(false)
                setBusy(false)
              }}
              style={{
                fontSize: '11px', padding: '3px 10px', borderRadius: '5px', cursor: 'pointer',
                background: '#06b6d422', color: '#06b6d4', border: '1px solid #06b6d4',
              }}
            >Save</button>
            <button
              onClick={() => setAddingAction(false)}
              style={{
                fontSize: '11px', padding: '3px 10px', borderRadius: '5px', cursor: 'pointer',
                background: '#1e293b', color: '#64748b', border: '1px solid #334155',
              }}
            >Cancel</button>
          </div>
        </div>
      )}

      {/* Actions timeline */}
      {expanded && (
        <div style={{ marginTop: '12px' }}>
          <ActionTimeline actions={goal.actions} />
        </div>
      )}

      {/* Footer */}
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '8px', fontSize: '10px', color: '#334155' }}>
        <span>Created {new Date(goal.created_at).toLocaleDateString()}</span>
        {goal.achieved_at && <span>Achieved {new Date(goal.achieved_at).toLocaleDateString()}</span>}
        <button
          onClick={async () => { if (window.confirm('Delete this goal?')) await onDelete(goal.id) }}
          style={{ background: 'none', border: 'none', color: '#334155', cursor: 'pointer', padding: 0, fontSize: '11px' }}
        >🗑</button>
      </div>
    </div>
  )
}

// ── New goal form ──────────────────────────────────────────────────────────────

function NewGoalForm({ onSave, onCancel }: { onSave: (d: { title: string; description: string; priority: number }) => Promise<void>; onCancel: () => void }) {
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [priority, setPriority] = useState(0.5)
  const [busy, setBusy] = useState(false)

  return (
    <div style={{
      background: '#0f172a', border: '1px solid #06b6d444', borderRadius: '8px',
      padding: '14px', marginBottom: '12px',
    }}>
      <div style={{ fontSize: '12px', fontWeight: 700, color: '#06b6d4', marginBottom: '10px', textTransform: 'uppercase', letterSpacing: '.06em' }}>New Goal</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        <input
          value={title}
          onChange={e => setTitle(e.target.value)}
          placeholder="Goal title…"
          style={{
            background: '#1e293b', border: '1px solid #334155', borderRadius: '5px',
            color: '#f1f5f9', padding: '6px 10px', fontSize: '13px',
          }}
        />
        <textarea
          value={description}
          onChange={e => setDescription(e.target.value)}
          placeholder="Description (optional)…"
          rows={2}
          style={{
            background: '#1e293b', border: '1px solid #334155', borderRadius: '5px',
            color: '#f1f5f9', padding: '6px 10px', fontSize: '12px', resize: 'vertical',
          }}
        />
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', fontSize: '12px', color: '#94a3b8' }}>
          <span>Priority</span>
          <input
            type="range" min={0} max={1} step={0.05} value={priority}
            onChange={e => setPriority(Number(e.target.value))}
            style={{ flex: 1 }}
          />
          <span style={{ color: '#06b6d4', fontWeight: 600, minWidth: '32px' }}>{Math.round(priority * 100)}%</span>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button
            disabled={!title.trim() || busy}
            onClick={async () => {
              setBusy(true)
              await onSave({ title: title.trim(), description: description.trim(), priority })
              setBusy(false)
            }}
            style={{
              fontSize: '12px', padding: '5px 14px', borderRadius: '5px', cursor: 'pointer',
              background: '#06b6d422', color: '#06b6d4', border: '1px solid #06b6d4',
              opacity: !title.trim() || busy ? 0.5 : 1,
            }}
          >Create</button>
          <button
            onClick={onCancel}
            style={{
              fontSize: '12px', padding: '5px 14px', borderRadius: '5px', cursor: 'pointer',
              background: '#1e293b', color: '#64748b', border: '1px solid #334155',
            }}
          >Cancel</button>
        </div>
      </div>
    </div>
  )
}

// ── Main panel ─────────────────────────────────────────────────────────────────

export default function GoalsPanel({ active }: { active: boolean }) {
  const [data, setData] = useState<GoalsResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [showNewForm, setShowNewForm] = useState(false)
  const [showHistory, setShowHistory] = useState(false)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const load = async () => {
    try {
      setLoading(true)
      const d = await fetchGoals()
      setData(d)
      setError(null)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  // Auto-refresh every 10 s while tab is active
  useEffect(() => {
    if (!active) { intervalRef.current && clearInterval(intervalRef.current); return }
    load()
    intervalRef.current = setInterval(load, 10_000)
    return () => { intervalRef.current && clearInterval(intervalRef.current) }
  }, [active])

  const refresh = async () => { await load() }

  const handleCreate = async (d: { title: string; description: string; priority: number }) => {
    await createGoal(d)
    setShowNewForm(false)
    await refresh()
  }

  const handleUpdate = async (id: string, patch: Partial<{ status: Goal['status']; description: string }>) => {
    await updateGoalStatus(id, patch)
    await refresh()
  }

  const handleDelete = async (id: string) => {
    await deleteGoal(id)
    await refresh()
  }

  const handleAddAction = async (id: string, description: string, result?: string) => {
    await addGoalAction(id, { description, result: result ?? '' })
    await refresh()
  }

  const activeGoals = data?.active ?? []
  const historyGoals = data?.history ?? []
  const maxActive = data?.max_active ?? 5

  return (
    <div style={{ height: '100%', overflow: 'auto', padding: '20px', fontFamily: 'inherit' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '18px' }}>
        <div>
          <div style={{ fontSize: '16px', fontWeight: 700, color: '#f1f5f9' }}>Goals</div>
          <div style={{ fontSize: '11px', color: '#475569' }}>Autonomous objectives — reviewed each curiosity cycle</div>
        </div>
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span style={{
            fontSize: '12px', fontWeight: 700, color: '#06b6d4',
            background: '#06b6d422', borderRadius: '6px', padding: '3px 10px',
            border: '1px solid #06b6d444',
          }}>
            {activeGoals.length}/{maxActive} active
          </span>
          <button
            onClick={refresh}
            disabled={loading}
            style={{
              background: '#1e293b', border: '1px solid #334155', borderRadius: '6px',
              color: '#64748b', cursor: 'pointer', padding: '4px 10px', fontSize: '12px',
            }}
          >{loading ? '⟳' : '↺'} Refresh</button>
          {activeGoals.length < maxActive && (
            <button
              onClick={() => setShowNewForm(f => !f)}
              style={{
                background: '#06b6d422', border: '1px solid #06b6d4', borderRadius: '6px',
                color: '#06b6d4', cursor: 'pointer', padding: '4px 12px', fontSize: '12px', fontWeight: 600,
              }}
            >+ New Goal</button>
          )}
        </div>
      </div>

      {error && (
        <div style={{ background: '#450a0a', border: '1px solid #ef4444', borderRadius: '6px', padding: '10px', color: '#ef4444', marginBottom: '12px', fontSize: '12px' }}>
          {error}
        </div>
      )}

      {showNewForm && (
        <NewGoalForm
          onSave={handleCreate}
          onCancel={() => setShowNewForm(false)}
        />
      )}

      {/* Active goals */}
      {activeGoals.length === 0 && !loading ? (
        <div style={{
          textAlign: 'center', color: '#334155', padding: '40px 20px',
          border: '1px dashed #1e293b', borderRadius: '8px', marginBottom: '16px',
        }}>
          <div style={{ fontSize: '32px', marginBottom: '8px' }}>◎</div>
          <div style={{ fontSize: '13px' }}>No active goals. Click <strong style={{ color: '#06b6d4' }}>+ New Goal</strong> to add one,<br />or wait for the curiosity cycle to generate goals automatically.</div>
        </div>
      ) : (
        activeGoals.map(g => (
          <GoalCard
            key={g.id}
            goal={g}
            onUpdate={handleUpdate}
            onDelete={handleDelete}
            onAddAction={handleAddAction}
          />
        ))
      )}

      {/* History section */}
      {historyGoals.length > 0 && (
        <div style={{ marginTop: '20px' }}>
          <button
            onClick={() => setShowHistory(h => !h)}
            style={{
              background: 'none', border: 'none', cursor: 'pointer',
              color: '#475569', fontSize: '12px', fontWeight: 600,
              textTransform: 'uppercase', letterSpacing: '.06em', padding: '0 0 8px',
              display: 'flex', alignItems: 'center', gap: '6px',
            }}
          >
            {showHistory ? '▲' : '▶'} History ({historyGoals.length})
          </button>
          {showHistory && historyGoals.map(g => (
            <GoalCard
              key={g.id}
              goal={g}
              onUpdate={handleUpdate}
              onDelete={handleDelete}
              onAddAction={handleAddAction}
            />
          ))}
        </div>
      )}
    </div>
  )
}
