// API client for PROJECT ECHO backend

const BASE = '/api'

export interface DriveScores {
  coherence: number
  curiosity: number
  stability: number
  competence: number
  compression: number
  weights: Record<string, number>
}

export interface MetaState {
  drives: DriveScores
  emotional_valence: number
  arousal: number
  timestamp: string
  agent_weights: Record<string, number>
}

export interface StateResponse {
  meta_state: MetaState
  workspace_items: number
  identity_beliefs: number
  episodic_memories: number
  interaction_count: number
}

export interface HistoryPoint {
  timestamp: string
  drives: Record<string, number>
  emotional_valence: number
}

export interface MemoryItem {
  id: string
  content: string
  memory_type: string
  salience: number
  current_strength: number
  created_at: string
  tags: string[]
}

export interface GraphNode {
  id: string
  content: string
  confidence: number
  tags: string[]
}

export interface GraphEdge {
  source: string
  target: string
  relation: string
  weight: number
}

export interface GraphResponse {
  nodes: GraphNode[]
  edges: GraphEdge[]
  coherence_score: number
}

export interface ConsolidationReport {
  id: string
  memories_processed: number
  memories_promoted: number
  memories_pruned: number
  beliefs_updated: number
  patterns_found: string[]
  started_at: string
  finished_at: string | null
}

// ── State ──────────────────────────────────────────────────────────────────
export async function fetchState(): Promise<StateResponse> {
  const r = await fetch(`${BASE}/state`)
  if (!r.ok) throw new Error(`state: ${r.status}`)
  return r.json()
}

export async function fetchHistory(limit = 60): Promise<HistoryPoint[]> {
  const r = await fetch(`${BASE}/state/history?limit=${limit}`)
  if (!r.ok) throw new Error(`history: ${r.status}`)
  return r.json()
}

// ── Memory ─────────────────────────────────────────────────────────────────
export async function fetchMemories(limit = 50): Promise<{ total: number; items: MemoryItem[] }> {
  const r = await fetch(`${BASE}/memory?limit=${limit}`)
  if (!r.ok) throw new Error(`memories: ${r.status}`)
  return r.json()
}

// ── Identity graph ─────────────────────────────────────────────────────────
export async function fetchGraph(): Promise<GraphResponse> {
  const r = await fetch(`${BASE}/identity/graph`)
  if (!r.ok) throw new Error(`graph: ${r.status}`)
  return r.json()
}

// ── Consolidation ──────────────────────────────────────────────────────────
export async function triggerConsolidation(): Promise<{ status: string; report: ConsolidationReport }> {
  const r = await fetch(`${BASE}/consolidation/trigger`, { method: 'POST' })
  if (!r.ok) throw new Error(`consolidation: ${r.status}`)
  return r.json()
}

// ── SSE Streaming chat ─────────────────────────────────────────────────────
export function streamInteract(
  message: string,
  history: Array<{ role: string; content: string }>,
  onDelta: (delta: string) => void,
  onDone: (metaState: MetaState) => void,
  onError: (err: string) => void,
): () => void {
  const controller = new AbortController()

  fetch(`${BASE}/interact`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, history }),
    signal: controller.signal,
  }).then(async (res) => {
    if (!res.ok || !res.body) {
      onError(`HTTP ${res.status}`)
      return
    }
    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const lines = buf.split('\n')
      buf = lines.pop() ?? ''
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6))
            if (data.type === 'delta') onDelta(data.content)
            else if (data.type === 'done') onDone(data.meta_state)
            else if (data.type === 'error') onError(data.content)
          } catch {
            // ignore parse error
          }
        }
      }
    }
  }).catch((err) => {
    if (err.name !== 'AbortError') onError(String(err))
  })

  return () => controller.abort()
}

// ── WebSocket events ───────────────────────────────────────────────────────
export function connectEventStream(
  onEvent: (topic: string, payload: unknown) => void,
): () => void {
  const ws = new WebSocket(`ws://${window.location.host}/ws/events`)
  ws.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data)
      onEvent(data.topic, data)
    } catch {
      // ignore
    }
  }
  return () => ws.close()
}
