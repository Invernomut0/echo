import { useEffect, useRef, useState } from 'react'
import {
  type CronRun,
  type CronTask,
  type CronTaskCreate,
  type CronTaskTypeInfo,
  createCronTask,
  deleteCronTask,
  disableCronTask,
  enableCronTask,
  fetchCronRuns,
  fetchCronTaskTypes,
  fetchCronTasks,
  triggerCronTask,
} from '../api'

// ── Colours ────────────────────────────────────────────────────────────────

const TASK_TYPE_COLOR: Record<string, string> = {
  reflection:           '#a78bfa',
  consolidation_light:  '#06b6d4',
  consolidation_deep:   '#3b82f6',
  curiosity_cycle:      '#10b981',
  llm_task:             '#f59e0b',
  memory_store:         '#ec4899',
  goal_reflect:         '#f97316',
}

const RUN_STATUS_COLOR: Record<string, string> = {
  running: '#f59e0b',
  success: '#10b981',
  error:   '#ef4444',
}

const RUN_STATUS_ICON: Record<string, string> = {
  running: '⟳',
  success: '✓',
  error:   '✕',
}

// ── Helpers ────────────────────────────────────────────────────────────────

function fmtDate(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' })
}

function fmtDuration(ms: number | null): string {
  if (ms === null) return '—'
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

function scheduleLabel(task: CronTask): string {
  if (task.schedule_type === 'interval') {
    const sec = parseInt(task.schedule, 10)
    if (isNaN(sec)) return task.schedule
    if (sec < 60) return `every ${sec}s`
    if (sec < 3600) return `every ${Math.round(sec / 60)}m`
    if (sec < 86400) return `every ${Math.round(sec / 3600)}h`
    return `every ${Math.round(sec / 86400)}d`
  }
  return task.schedule // cron expression shown as-is
}

function timeUntil(iso: string | null): string {
  if (!iso) return '—'
  const diff = new Date(iso).getTime() - Date.now()
  if (diff <= 0) return 'now'
  const s = Math.floor(diff / 1000)
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ${s % 60}s`
  const h = Math.floor(m / 60)
  return `${h}h ${m % 60}m`
}

// ── Run history list ───────────────────────────────────────────────────────

function RunHistory({ taskId }: { taskId: string }) {
  const [runs, setRuns] = useState<CronRun[]>([])
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    fetchCronRuns(taskId, 15)
      .then(setRuns)
      .catch(() => setRuns([]))
      .finally(() => setLoading(false))
  }, [taskId])

  if (loading) {
    return <div style={{ color: '#475569', fontSize: '11px', padding: '8px 0' }}>Loading runs…</div>
  }
  if (!runs.length) {
    return <div style={{ color: '#334155', fontSize: '11px', padding: '8px 0' }}>No runs yet.</div>
  }

  return (
    <div style={{ marginTop: '8px' }}>
      <div style={{ fontSize: '10px', fontWeight: 700, color: '#475569', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: '6px' }}>
        Run History ({runs.length})
      </div>
      <div style={{ borderLeft: '2px solid #1e293b', paddingLeft: '10px' }}>
        {runs.map(run => {
          const color = RUN_STATUS_COLOR[run.status] ?? '#94a3b8'
          const icon  = RUN_STATUS_ICON[run.status]  ?? '?'
          const isOpen = expanded === run.id
          return (
            <div key={run.id} style={{ marginBottom: '8px', position: 'relative' }}>
              {/* Timeline dot */}
              <div style={{
                position: 'absolute', left: '-14px', top: '3px',
                width: '8px', height: '8px', borderRadius: '50%',
                background: color, border: '2px solid #0f172a',
              }} />
              <div
                style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}
                onClick={() => setExpanded(isOpen ? null : run.id)}
              >
                <span style={{ fontSize: '10px', fontWeight: 700, color, minWidth: '16px' }}>{icon}</span>
                <span style={{ fontSize: '11px', color: '#94a3b8' }}>{fmtDate(run.started_at)}</span>
                <span style={{ fontSize: '11px', color: '#475569', marginLeft: 'auto' }}>
                  {fmtDuration(run.duration_ms)}
                </span>
                <span style={{ fontSize: '10px', color: '#334155' }}>{isOpen ? '▲' : '▶'}</span>
              </div>
              {/* Expanded result */}
              {isOpen && !!run.result && (
                <pre style={{
                  marginTop: '4px', padding: '6px 8px',
                  background: '#0f172a', borderRadius: '4px',
                  fontSize: '10px', color: '#94a3b8',
                  whiteSpace: 'pre-wrap', wordBreak: 'break-all',
                  maxHeight: '120px', overflowY: 'auto',
                }}>
                  {typeof run.result === 'string' ? run.result : JSON.stringify(run.result as object, null, 2)}
                </pre>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Task card ──────────────────────────────────────────────────────────────

function TaskCard({
  task,
  onToggle,
  onDelete,
  onTrigger,
}: {
  task: CronTask
  onToggle: (id: string, enabled: boolean) => Promise<void>
  onDelete: (id: string) => Promise<void>
  onTrigger: (id: string) => Promise<string>
}) {
  const [expanded, setExpanded] = useState(false)
  const [busy, setBusy] = useState(false)
  const [triggerResult, setTriggerResult] = useState<string | null>(null)

  const typeColor = TASK_TYPE_COLOR[task.task_type] ?? '#94a3b8'
  const borderColor = task.enabled ? typeColor : '#334155'

  const handleTrigger = async () => {
    setBusy(true)
    setTriggerResult(null)
    try {
      const res = await onTrigger(task.id)
      setTriggerResult(`✓ ${res ?? 'OK'}`)
    } catch (e) {
      setTriggerResult(`✕ ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setBusy(false)
      setTimeout(() => setTriggerResult(null), 5000)
    }
  }

  return (
    <div style={{
      background: '#0f172a',
      border: `1px solid ${borderColor}33`,
      borderLeft: `3px solid ${borderColor}`,
      borderRadius: '8px',
      padding: '14px 16px',
      marginBottom: '10px',
      opacity: task.enabled ? 1 : 0.65,
      transition: 'opacity .2s',
    }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px' }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          {/* Badges row */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '5px', flexWrap: 'wrap' }}>
            {/* Task type badge */}
            <span style={{
              fontSize: '10px', fontWeight: 700,
              color: typeColor, background: `${typeColor}18`,
              borderRadius: '4px', padding: '1px 6px',
              textTransform: 'uppercase', letterSpacing: '.06em',
            }}>{task.task_type.replace(/_/g, ' ')}</span>

            {/* Enabled/disabled */}
            <span style={{
              fontSize: '10px', fontWeight: 700,
              color: task.enabled ? '#10b981' : '#475569',
              background: task.enabled ? '#10b98118' : '#1e293b',
              borderRadius: '4px', padding: '1px 6px',
              textTransform: 'uppercase', letterSpacing: '.04em',
            }}>{task.enabled ? 'enabled' : 'disabled'}</span>

            {/* Schedule badge */}
            <span style={{
              fontSize: '10px', color: '#64748b',
              background: '#1e293b', borderRadius: '4px',
              padding: '1px 6px', fontFamily: 'monospace',
            }}>
              {task.schedule_type === 'cron' ? '◷' : '↻'} {scheduleLabel(task)}
            </span>
          </div>

          {/* Title */}
          <div style={{ fontSize: '14px', fontWeight: 600, color: '#f1f5f9', marginBottom: '3px' }}>
            {task.name}
          </div>
          {task.description && (
            <div style={{ fontSize: '12px', color: '#64748b' }}>{task.description}</div>
          )}
        </div>

        {/* Expand toggle */}
        <button
          onClick={() => setExpanded(e => !e)}
          style={{ background: 'none', border: 'none', color: '#475569', cursor: 'pointer', fontSize: '13px', padding: '2px 4px', flexShrink: 0 }}
          title={expanded ? 'Collapse' : 'Show details'}
        >{expanded ? '▲' : '▼'}</button>
      </div>

      {/* Stats row */}
      <div style={{ display: 'flex', gap: '16px', marginTop: '10px', fontSize: '11px', color: '#475569' }}>
        <div>
          <span style={{ color: '#334155' }}>Runs: </span>
          <span style={{ color: '#94a3b8', fontWeight: 600 }}>{task.run_count}</span>
        </div>
        <div>
          <span style={{ color: '#334155' }}>Last: </span>
          <span style={{ color: '#94a3b8' }}>{fmtDate(task.last_run_at)}</span>
        </div>
        <div>
          <span style={{ color: '#334155' }}>Next: </span>
          <span style={{ color: task.enabled ? typeColor : '#334155', fontWeight: 600 }}>
            {task.enabled ? timeUntil(task.next_run_at) : '—'}
          </span>
          {task.enabled && task.next_run_at && (
            <span style={{ color: '#475569', marginLeft: '4px' }}>({fmtDate(task.next_run_at)})</span>
          )}
        </div>
      </div>

      {/* Action buttons */}
      <div style={{ display: 'flex', gap: '8px', marginTop: '10px', flexWrap: 'wrap', alignItems: 'center' }}>
        {/* Enable/Disable toggle */}
        <button
          disabled={busy}
          onClick={async () => { setBusy(true); await onToggle(task.id, !task.enabled); setBusy(false) }}
          style={{
            fontSize: '11px', padding: '3px 10px', borderRadius: '5px', cursor: 'pointer',
            background: task.enabled ? '#1e293b' : '#052e16',
            color: task.enabled ? '#64748b' : '#10b981',
            border: `1px solid ${task.enabled ? '#334155' : '#10b981'}`,
          }}
        >{task.enabled ? '⏸ Disable' : '▶ Enable'}</button>

        {/* Manual trigger */}
        <button
          disabled={busy}
          onClick={handleTrigger}
          title="Run now"
          style={{
            fontSize: '11px', padding: '3px 10px', borderRadius: '5px', cursor: 'pointer',
            background: '#0c1a2e', color: typeColor, border: `1px solid ${typeColor}`,
          }}
        >{busy ? '⟳ Running…' : '⚡ Run now'}</button>

        {/* Delete */}
        <button
          disabled={busy}
          onClick={async () => {
            if (!window.confirm(`Delete task "${task.name}"?`)) return
            await onDelete(task.id)
          }}
          style={{
            fontSize: '11px', padding: '3px 8px', borderRadius: '5px', cursor: 'pointer',
            background: 'none', color: '#334155', border: '1px solid transparent',
            marginLeft: 'auto',
          }}
          title="Delete task"
        >🗑</button>
      </div>

      {/* Trigger result flash */}
      {triggerResult && (
        <div style={{
          marginTop: '8px', padding: '6px 10px',
          background: triggerResult.startsWith('✓') ? '#052e16' : '#450a0a',
          borderRadius: '5px', fontSize: '11px',
          color: triggerResult.startsWith('✓') ? '#10b981' : '#ef4444',
          border: `1px solid ${triggerResult.startsWith('✓') ? '#10b981' : '#ef4444'}44`,
        }}>
          {triggerResult}
        </div>
      )}

      {/* Expanded details */}
      {expanded && (
        <div style={{ marginTop: '14px', borderTop: '1px solid #1e293b', paddingTop: '12px' }}>
          {/* Config */}
          {Object.keys(task.task_config).length > 0 && (
            <div style={{ marginBottom: '12px' }}>
              <div style={{ fontSize: '10px', fontWeight: 700, color: '#475569', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: '6px' }}>
                Config
              </div>
              <pre style={{
                background: '#070a12', borderRadius: '5px', padding: '8px 10px',
                fontSize: '11px', color: '#94a3b8',
                whiteSpace: 'pre-wrap', wordBreak: 'break-all',
                maxHeight: '120px', overflowY: 'auto',
                border: '1px solid #1e293b',
              }}>
                {JSON.stringify(task.task_config, null, 2)}
              </pre>
            </div>
          )}

          {/* Meta */}
          <div style={{ display: 'flex', gap: '16px', fontSize: '10px', color: '#334155', marginBottom: '10px' }}>
            <span>Created: {fmtDate(task.created_at)}</span>
            <span>Updated: {fmtDate(task.updated_at)}</span>
            <span style={{ fontFamily: 'monospace' }}>ID: {task.id.slice(0, 8)}…</span>
          </div>

          {/* Run history */}
          <RunHistory taskId={task.id} />
        </div>
      )}
    </div>
  )
}

// ── New task form ──────────────────────────────────────────────────────────

const SCHEDULE_PRESETS = [
  { label: 'Every 5 min',   value: '300',        type: 'interval' as const },
  { label: 'Every 30 min',  value: '1800',       type: 'interval' as const },
  { label: 'Every hour',    value: '3600',       type: 'interval' as const },
  { label: 'Every 6 hours', value: '0 */6 * * *', type: 'cron' as const },
  { label: 'Daily at 3am',  value: '0 3 * * *',  type: 'cron' as const },
  { label: 'Custom…',       value: '',           type: 'interval' as const },
]

function NewTaskForm({
  taskTypes,
  onSave,
  onCancel,
}: {
  taskTypes: CronTaskTypeInfo[]
  onSave: (data: CronTaskCreate) => Promise<void>
  onCancel: () => void
}) {
  const [name, setName]               = useState('')
  const [description, setDesc]        = useState('')
  const [taskType, setTaskType]       = useState(taskTypes[0]?.type ?? 'llm_task')
  const [preset, setPreset]           = useState(SCHEDULE_PRESETS[2])  // every hour default
  const [customSchedule, setCustom]   = useState('')
  const [scheduleType, setSType]      = useState<'cron' | 'interval'>('interval')
  const [configText, setConfigText]   = useState('{}')
  const [configError, setConfigErr]   = useState<string | null>(null)
  const [busy, setBusy]               = useState(false)

  // When a task type is selected, pre-fill the config example
  const handleTypeChange = (t: string) => {
    setTaskType(t)
    const info = taskTypes.find(ti => ti.type === t)
    if (info) {
      setConfigText(JSON.stringify(info.config_example, null, 2))
      setConfigErr(null)
    }
  }

  const handlePreset = (p: typeof SCHEDULE_PRESETS[0]) => {
    setPreset(p)
    if (p.value) {
      setSType(p.type)
      setCustom(p.value)
    }
  }

  const resolvedSchedule = preset.value ? preset.value : customSchedule
  const resolvedType     = preset.value ? preset.type  : scheduleType

  const handleSave = async () => {
    let config: Record<string, unknown> = {}
    try {
      config = JSON.parse(configText)
      setConfigErr(null)
    } catch (e) {
      setConfigErr(e instanceof Error ? e.message : 'Invalid JSON')
      return
    }
    setBusy(true)
    try {
      await onSave({
        name: name.trim(),
        description: description.trim(),
        schedule_type: resolvedType,
        schedule: resolvedSchedule,
        task_type: taskType,
        task_config: config,
        enabled: true,
      })
    } finally {
      setBusy(false)
    }
  }

  const canSave = name.trim() && resolvedSchedule.trim() && !configError

  return (
    <div style={{
      background: '#0f172a', border: '1px solid #06b6d444',
      borderRadius: '10px', padding: '16px', marginBottom: '14px',
    }}>
      <div style={{ fontSize: '12px', fontWeight: 700, color: '#06b6d4', marginBottom: '12px', textTransform: 'uppercase', letterSpacing: '.06em' }}>
        New Cron Task
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
        {/* Name */}
        <div>
          <label style={{ fontSize: '11px', color: '#64748b', display: 'block', marginBottom: '4px' }}>Name *</label>
          <input
            value={name}
            onChange={e => setName(e.target.value)}
            placeholder="Task name…"
            style={inputStyle}
          />
        </div>

        {/* Description */}
        <div>
          <label style={{ fontSize: '11px', color: '#64748b', display: 'block', marginBottom: '4px' }}>Description</label>
          <input
            value={description}
            onChange={e => setDesc(e.target.value)}
            placeholder="Optional description…"
            style={inputStyle}
          />
        </div>

        {/* Task type */}
        <div>
          <label style={{ fontSize: '11px', color: '#64748b', display: 'block', marginBottom: '4px' }}>Task Type *</label>
          <select
            value={taskType}
            onChange={e => handleTypeChange(e.target.value)}
            style={{ ...inputStyle, cursor: 'pointer' }}
          >
            {taskTypes.map(t => (
              <option key={t.type} value={t.type}>{t.type.replace(/_/g, ' ')}</option>
            ))}
          </select>
          {/* Description of selected type */}
          <div style={{ fontSize: '11px', color: '#475569', marginTop: '4px' }}>
            {taskTypes.find(t => t.type === taskType)?.description}
          </div>
        </div>

        {/* Schedule presets */}
        <div>
          <label style={{ fontSize: '11px', color: '#64748b', display: 'block', marginBottom: '4px' }}>Schedule *</label>
          <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginBottom: '6px' }}>
            {SCHEDULE_PRESETS.map(p => (
              <button
                key={p.label}
                onClick={() => handlePreset(p)}
                style={{
                  fontSize: '11px', padding: '3px 8px', borderRadius: '5px', cursor: 'pointer',
                  background: preset.label === p.label ? '#06b6d422' : '#1e293b',
                  color: preset.label === p.label ? '#06b6d4' : '#64748b',
                  border: `1px solid ${preset.label === p.label ? '#06b6d4' : '#334155'}`,
                }}
              >{p.label}</button>
            ))}
          </div>

          {/* Custom schedule inputs (when "Custom…" selected) */}
          {preset.label === 'Custom…' && (
            <div style={{ display: 'flex', gap: '8px' }}>
              <select
                value={scheduleType}
                onChange={e => setSType(e.target.value as 'cron' | 'interval')}
                style={{ ...inputStyle, width: '90px' }}
              >
                <option value="interval">Interval</option>
                <option value="cron">Cron</option>
              </select>
              <input
                value={customSchedule}
                onChange={e => setCustom(e.target.value)}
                placeholder={scheduleType === 'interval' ? 'Seconds (e.g. 3600)' : 'Cron (e.g. 0 */6 * * *)'}
                style={{ ...inputStyle, flex: 1 }}
              />
            </div>
          )}

          {resolvedSchedule && (
            <div style={{ fontSize: '11px', color: '#475569', marginTop: '4px', fontFamily: 'monospace' }}>
              ↻ {resolvedType} · {resolvedSchedule}
            </div>
          )}
        </div>

        {/* Config JSON */}
        <div>
          <label style={{ fontSize: '11px', color: '#64748b', display: 'block', marginBottom: '4px' }}>
            Task Config (JSON)
          </label>
          <textarea
            value={configText}
            onChange={e => { setConfigText(e.target.value); setConfigErr(null) }}
            rows={5}
            spellCheck={false}
            style={{
              ...inputStyle,
              fontFamily: 'monospace', fontSize: '11px',
              resize: 'vertical', minHeight: '80px',
            }}
          />
          {configError && (
            <div style={{ fontSize: '11px', color: '#ef4444', marginTop: '4px' }}>✕ {configError}</div>
          )}
        </div>

        {/* Buttons */}
        <div style={{ display: 'flex', gap: '8px' }}>
          <button
            disabled={!canSave || busy}
            onClick={handleSave}
            style={{
              fontSize: '12px', padding: '5px 16px', borderRadius: '5px', cursor: 'pointer',
              background: '#06b6d422', color: '#06b6d4', border: '1px solid #06b6d4',
              opacity: !canSave || busy ? 0.5 : 1,
            }}
          >{busy ? 'Creating…' : 'Create Task'}</button>
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

const inputStyle: React.CSSProperties = {
  width: '100%', boxSizing: 'border-box',
  background: '#1e293b', border: '1px solid #334155',
  borderRadius: '5px', color: '#f1f5f9',
  padding: '6px 10px', fontSize: '12px',
  outline: 'none',
}

// ── Summary stats bar ──────────────────────────────────────────────────────

function SummaryBar({ tasks }: { tasks: CronTask[] }) {
  const enabled = tasks.filter(t => t.enabled).length
  const typeCounts = tasks.reduce<Record<string, number>>((acc, t) => {
    acc[t.task_type] = (acc[t.task_type] ?? 0) + 1
    return acc
  }, {})
  const totalRuns = tasks.reduce((s, t) => s + t.run_count, 0)

  return (
    <div style={{
      display: 'flex', gap: '16px', flexWrap: 'wrap',
      background: '#0f172a', borderRadius: '8px',
      padding: '10px 14px', marginBottom: '16px',
      border: '1px solid #1e293b', fontSize: '12px', color: '#64748b',
    }}>
      <div>
        <span style={{ color: '#334155' }}>Total: </span>
        <span style={{ color: '#f1f5f9', fontWeight: 700 }}>{tasks.length}</span>
      </div>
      <div>
        <span style={{ color: '#334155' }}>Enabled: </span>
        <span style={{ color: '#10b981', fontWeight: 700 }}>{enabled}</span>
      </div>
      <div>
        <span style={{ color: '#334155' }}>Disabled: </span>
        <span style={{ color: '#475569', fontWeight: 700 }}>{tasks.length - enabled}</span>
      </div>
      <div>
        <span style={{ color: '#334155' }}>Total runs: </span>
        <span style={{ color: '#94a3b8', fontWeight: 700 }}>{totalRuns}</span>
      </div>
      {/* Type breakdown */}
      <div style={{ marginLeft: 'auto', display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center' }}>
        {Object.entries(typeCounts).map(([type, count]) => (
          <span key={type} style={{
            fontSize: '10px', padding: '1px 6px', borderRadius: '4px',
            background: `${TASK_TYPE_COLOR[type] ?? '#94a3b8'}18`,
            color: TASK_TYPE_COLOR[type] ?? '#94a3b8',
            fontWeight: 600,
          }}>{type.replace(/_/g, ' ')}: {count}</span>
        ))}
      </div>
    </div>
  )
}

// ── Main panel ─────────────────────────────────────────────────────────────

export default function CronPanel({ active }: { active: boolean }) {
  const [tasks, setTasks]             = useState<CronTask[]>([])
  const [taskTypes, setTaskTypes]     = useState<CronTaskTypeInfo[]>([])
  const [error, setError]             = useState<string | null>(null)
  const [loading, setLoading]         = useState(false)
  const [showNewForm, setShowNewForm] = useState(false)
  const [filter, setFilter]           = useState<'all' | 'enabled' | 'disabled'>('all')
  const intervalRef                   = useRef<ReturnType<typeof setInterval> | null>(null)

  const load = async () => {
    try {
      setLoading(true)
      const [t, tt] = await Promise.all([fetchCronTasks(), fetchCronTaskTypes()])
      setTasks(t)
      setTaskTypes(tt.task_types)
      setError(null)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!active) { intervalRef.current && clearInterval(intervalRef.current); return }
    load()
    intervalRef.current = setInterval(load, 10_000)
    return () => { intervalRef.current && clearInterval(intervalRef.current) }
  }, [active])

  const handleCreate = async (data: CronTaskCreate) => {
    await createCronTask(data)
    setShowNewForm(false)
    await load()
  }

  const handleToggle = async (id: string, enable: boolean) => {
    if (enable) await enableCronTask(id)
    else await disableCronTask(id)
    await load()
  }

  const handleDelete = async (id: string) => {
    await deleteCronTask(id)
    await load()
  }

  const handleTrigger = async (id: string) => {
    const res = await triggerCronTask(id)
    await load()
    return JSON.stringify(res.result ?? res.status)
  }

  const filteredTasks = tasks.filter(t => {
    if (filter === 'enabled')  return t.enabled
    if (filter === 'disabled') return !t.enabled
    return true
  })

  return (
    <div style={{ height: '100%', overflow: 'auto', padding: '20px', fontFamily: 'inherit' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
        <div>
          <div style={{ fontSize: '16px', fontWeight: 700, color: '#f1f5f9' }}>Cron Tasks</div>
          <div style={{ fontSize: '11px', color: '#475569' }}>
            Internal recurring tasks — scheduled and executed autonomously by ECHO
          </div>
        </div>
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <button
            onClick={() => load()}
            disabled={loading}
            style={{
              background: '#1e293b', border: '1px solid #334155', borderRadius: '6px',
              color: '#64748b', cursor: 'pointer', padding: '4px 10px', fontSize: '12px',
            }}
          >{loading ? '⟳' : '↺'} Refresh</button>
          <button
            onClick={() => setShowNewForm(f => !f)}
            style={{
              background: '#06b6d422', border: '1px solid #06b6d4', borderRadius: '6px',
              color: '#06b6d4', cursor: 'pointer', padding: '4px 12px', fontSize: '12px', fontWeight: 600,
            }}
          >+ New Task</button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div style={{
          background: '#450a0a', border: '1px solid #ef4444',
          borderRadius: '6px', padding: '10px', color: '#ef4444',
          marginBottom: '12px', fontSize: '12px',
        }}>
          {error}
        </div>
      )}

      {/* New task form */}
      {showNewForm && (
        <NewTaskForm
          taskTypes={taskTypes}
          onSave={handleCreate}
          onCancel={() => setShowNewForm(false)}
        />
      )}

      {/* Summary */}
      {tasks.length > 0 && <SummaryBar tasks={tasks} />}

      {/* Filter tabs */}
      {tasks.length > 0 && (
        <div style={{ display: 'flex', gap: '6px', marginBottom: '14px' }}>
          {(['all', 'enabled', 'disabled'] as const).map(f => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              style={{
                fontSize: '11px', padding: '3px 10px', borderRadius: '5px', cursor: 'pointer',
                background: filter === f ? '#1e3a5f' : '#1e293b',
                color: filter === f ? '#06b6d4' : '#475569',
                border: `1px solid ${filter === f ? '#06b6d4' : '#334155'}`,
                textTransform: 'capitalize',
              }}
            >{f} {f === 'all' ? `(${tasks.length})` : f === 'enabled' ? `(${tasks.filter(t => t.enabled).length})` : `(${tasks.filter(t => !t.enabled).length})`}</button>
          ))}
        </div>
      )}

      {/* Empty state */}
      {filteredTasks.length === 0 && !loading && (
        <div style={{
          textAlign: 'center', color: '#334155', padding: '48px 20px',
          border: '1px dashed #1e293b', borderRadius: '10px',
        }}>
          <div style={{ fontSize: '36px', marginBottom: '10px' }}>⏱</div>
          <div style={{ fontSize: '13px', lineHeight: 1.6 }}>
            {tasks.length === 0
              ? <>No cron tasks yet.<br />Click <strong style={{ color: '#06b6d4' }}>+ New Task</strong> to schedule your first recurring task.</>
              : 'No tasks match this filter.'}
          </div>
        </div>
      )}

      {/* Task list */}
      {filteredTasks.map(task => (
        <TaskCard
          key={task.id}
          task={task}
          onToggle={handleToggle}
          onDelete={handleDelete}
          onTrigger={handleTrigger}
        />
      ))}
    </div>
  )
}
