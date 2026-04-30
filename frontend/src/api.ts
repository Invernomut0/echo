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
  arousal: number
  agent_weights: Record<string, number>
  drive_weights: Record<string, number>
  total_motivation: number
}

export interface MemoryItem {
  id: string
  content: string
  memory_type: string
  salience: number
  current_strength: number
  created_at: string
  tags: string[]
  is_dormant?: boolean
  has_vector?: boolean
}

export interface GraphNode {
  id: string
  content: string
  confidence: number
  tags: string[]
  /** 'belief' (identity) | 'semantic' (vector memory). Default: 'belief' */
  node_type?: string
  source_agent?: string
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

export interface DreamEntry {
  id: string
  dream: string
  source_memory_count: number
  created_at: string
  cycle_type: 'light' | 'rem'
}

export interface HeartbeatStatus {
  last_light_at: string | null
  last_deep_at: string | null
  next_light_at: string | null
  next_deep_at: string | null
  light_interval_seconds: number
  deep_interval_seconds: number
  running: boolean
}

// ── Pipeline Trace ─────────────────────────────────────────────────────────
export interface PipelineWorkspaceItem {
  source: string
  content: string
  salience: number
  competition_score: number
}

export interface PipelineTrace {
  interaction_id: string
  timestamp: string
  retrieval: {
    episodic_count: number
    semantic_count: number
    episodic_snippets: string[]
    semantic_snippets: string[]
  }
  self_prediction: string
  learning_priors: {
    emotional_valence_forecast: number
    curiosity_spike_prob: number
    identity_drift_risk: number
    consolidation_urgency: number
    is_notable: boolean
    workspace_items: [string, number][]
  }
  personalization: {
    verbosity: number
    topic_depth: number
    recall_frequency: number
    style_hint: string
    n_observations: number
  }
  workspace_items: PipelineWorkspaceItem[]
  drives_before: Record<string, number>
  valence_before: number
  arousal_before: number
  identity_drift: number
  post_interact_complete: boolean
  drive_scores: Record<string, number>
  prediction_error: number | null
  valence_after: number | null
  arousal_after: number | null
  response_length: number | null
  step_times: {
    retrieval_ms: number | null
    generation_ms: number | null
    total_ms: number | null
  } | null
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

export interface VectorStoreStatus {
  episodic_sqlite_count: number
  episodic_vector_count: number
  semantic_sqlite_count: number
  semantic_vector_count: number
  episodic_coverage_pct: number
  semantic_coverage_pct: number
}

export async function fetchVectorStatus(): Promise<VectorStoreStatus> {
  const r = await fetch(`${BASE}/memory/vectors`)
  if (!r.ok) throw new Error(`vector-status: ${r.status}`)
  return r.json()
}

export async function fetchSemanticMemories(
  limit = 50
): Promise<{ total: number; items: MemoryItem[] }> {
  const r = await fetch(`${BASE}/memory/semantic?limit=${limit}`)
  if (!r.ok) throw new Error(`semantic-memories: ${r.status}`)
  return r.json()
}

// ── Chunks (ChromaDB chunk viewer) ─────────────────────────────────────────
export interface ChunkItem {
  chunk_id: string
  chunk_index: number
  text: string
  char_count: number
  embedding_dim: number
  embedding_preview: number[]  // first N dims for visualization
}

export interface MemoryWithChunks {
  memory_id: string
  content: string
  salience: number
  created_at: string
  tags: string[]
  chunk_count: number
  chunks: ChunkItem[]
}

export interface ChunksResponse {
  total_memories: number
  total_chunks: number
  memories: MemoryWithChunks[]
}

export async function fetchChunks(limit = 200): Promise<ChunksResponse> {
  const r = await fetch(`${BASE}/memory/chunks?limit=${limit}`)
  if (!r.ok) throw new Error(`chunks: ${r.status}`)
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

export async function fetchHeartbeat(): Promise<HeartbeatStatus> {
  const r = await fetch(`${BASE}/consolidation/heartbeat`)
  if (!r.ok) throw new Error(`heartbeat: ${r.status}`)
  return r.json()
}

export async function fetchDreams(limit = 20): Promise<DreamEntry[]> {
  const r = await fetch(`${BASE}/consolidation/dreams?limit=${limit}`)
  if (!r.ok) throw new Error(`dreams: ${r.status}`)
  return r.json()
}

export async function triggerREM(): Promise<{ status: string; dream: DreamEntry }> {
  const r = await fetch(`${BASE}/consolidation/trigger-rem`, { method: 'POST' })
  if (!r.ok) throw new Error(`trigger-rem: ${r.status}`)
  return r.json()
}

export async function fetchPipelineTrace(): Promise<PipelineTrace | null> {
  const r = await fetch(`${BASE}/pipeline/trace`)
  if (!r.ok) return null
  const data = await r.json()
  // Return null if no trace yet (empty object)
  if (!data?.interaction_id) return null
  return data as PipelineTrace
}

// ── SSE Streaming chat ─────────────────────────────────────────────────────
export interface MemorySources {
  episodic: number
  semantic: number
  wiki?: number
}

export function streamInteract(
  message: string,
  history: Array<{ role: string; content: string }>,
  onDelta: (delta: string) => void,
  onDone: (metaState: MetaState, memorySources: MemorySources, toolsUsed: string[]) => void,
  onError: (err: string) => void,
  onStatus?: (message: string) => void,
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
    let doneReceived = false
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
            else if (data.type === 'status') onStatus?.(data.message)
            else if (data.type === 'done') {
              doneReceived = true
              const sources: MemorySources = data.memory_sources ?? { episodic: 0, semantic: 0 }
              const toolsUsed: string[] = data.tools_used ?? []
              onDone(data.meta_state, sources, toolsUsed)
            }
            else if (data.type === 'error') onError(data.content)
          } catch {
            // ignore parse error
          }
        }
      }
    }
    // Safety net: if the stream closed without a 'done' event (e.g. server crash),
    // unblock the UI so the user can keep writing.
    if (!doneReceived) {
      onError('Stream ended unexpectedly')
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

// ── Setup / Config ─────────────────────────────────────────────────────────

export interface SetupConfig {
  lm_studio_base_url: string
  lm_studio_api_key: string
  lm_studio_model: string
  lm_studio_embedding_model: string
  has_github_token: boolean
  llm_provider: 'copilot' | 'lm_studio'
  copilot_model: string
}

export interface DeviceCodeResponse {
  device_code: string
  user_code: string
  verification_uri: string
  expires_in: number
  interval: number
}

export interface DevicePollResponse {
  access_token?: string
  token_type?: string
  scope?: string
  error?: string
  error_description?: string
}

export interface CopilotTokenResponse {
  token: string
  expires_at: string
  endpoint: string
}

export interface LMStudioTestResponse {
  ok: boolean
  models?: string[]
  error?: string
}

export async function fetchSetupConfig(): Promise<SetupConfig> {
  const r = await fetch(`${BASE}/setup/config`)
  if (!r.ok) throw new Error(`setup config: ${r.status}`)
  return r.json()
}

export async function saveSetupConfig(
  payload: Partial<Omit<SetupConfig, 'has_github_token'> & { github_token?: string }>,
): Promise<void> {
  const r = await fetch(`${BASE}/setup/config`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!r.ok) throw new Error(`save config: ${r.status}`)
}

export async function startGitHubDeviceFlow(): Promise<DeviceCodeResponse> {
  // Backend uses VS Code's OAuth App client ID — no parameters needed.
  const r = await fetch(`${BASE}/setup/github/device`, { method: 'POST' })
  if (!r.ok) {
    const body = await r.json().catch(() => ({ detail: r.statusText }))
    throw new Error(body.detail ?? `device flow: ${r.status}`)
  }
  return r.json()
}

export async function pollGitHubDeviceFlow(
  deviceCode: string,
): Promise<DevicePollResponse> {
  const r = await fetch(`${BASE}/setup/github/poll`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ device_code: deviceCode }),
  })
  if (!r.ok) {
    const body = await r.json().catch(() => ({ detail: r.statusText }))
    throw new Error(body.detail ?? `poll: ${r.status}`)
  }
  return r.json()
}

export async function fetchCopilotToken(): Promise<CopilotTokenResponse> {
  const r = await fetch(`${BASE}/setup/github/copilot-token`)
  if (!r.ok) {
    const body = await r.json().catch(() => ({ detail: r.statusText }))
    throw new Error(body.detail ?? `copilot token: ${r.status}`)
  }
  return r.json()
}

export async function testLMStudio(baseUrl?: string): Promise<LMStudioTestResponse> {
  const r = await fetch(`${BASE}/setup/lmstudio/test`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: baseUrl ? JSON.stringify({ base_url: baseUrl }) : '{}',
  })
  if (!r.ok) throw new Error(`lmstudio test: ${r.status}`)
  return r.json()
}

// ── MCP ────────────────────────────────────────────────────────────────────

export interface McpServerStatus {
  name: string
  transport: string
  enabled: boolean
  connected: boolean
  error: string | null
  tool_count: number
  description: string
}

export interface McpTool {
  qualified_name: string
  server_name: string
  name: string
  description: string
  input_schema: Record<string, unknown>
}

export interface AddMcpServerRequest {
  name: string
  transport: 'stdio' | 'sse'
  command?: string
  args?: string[]
  env?: Record<string, string>
  url?: string
  description?: string
}

export async function fetchMcpServers(): Promise<McpServerStatus[]> {
  const r = await fetch(`${BASE}/mcp/servers`)
  if (!r.ok) throw new Error(`mcp servers: ${r.status}`)
  return r.json()
}

export async function fetchMcpTools(): Promise<McpTool[]> {
  const r = await fetch(`${BASE}/mcp/tools`)
  if (!r.ok) throw new Error(`mcp tools: ${r.status}`)
  return r.json()
}

export async function addMcpServer(req: AddMcpServerRequest): Promise<McpServerStatus> {
  const r = await fetch(`${BASE}/mcp/servers`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!r.ok) {
    const body = await r.json().catch(() => ({ detail: r.statusText }))
    throw new Error(body.detail ?? `add server: ${r.status}`)
  }
  return r.json()
}

export async function removeMcpServer(name: string): Promise<void> {
  const r = await fetch(`${BASE}/mcp/servers/${encodeURIComponent(name)}`, {
    method: 'DELETE',
  })
  if (!r.ok) throw new Error(`remove server: ${r.status}`)
}

// ── Curiosity ─────────────────────────────────────────────────────────────

export interface CuriosityFinding {
  title: string
  source: string
  topic: string
  url: string | null
}

export interface CycleRecord {
  id: string
  started_at: string
  finished_at: string | null
  status: 'running' | 'completed' | 'skipped' | 'error'
  skip_reason: string | null
  idle_seconds: number | null
  topics_proposed: string[]
  topics_searched: string[]
  results_by_source: Record<string, number>
  total_found: number
  total_stored: number
  total_deduped: number
  findings: CuriosityFinding[]
}

export interface CuriosityActivity {
  is_running: boolean
  recently_searched: string[]
  stats: {
    total_cycles: number
    completed: number
    skipped: number
    total_stored: number
  }
  cycles: CycleRecord[]
}

export async function fetchCuriosityActivity(limit = 50): Promise<CuriosityActivity> {
  const r = await fetch(`${BASE}/curiosity/activity?limit=${limit}`)
  if (!r.ok) throw new Error(`curiosity activity: ${r.status}`)
  return r.json()
}

export async function triggerCuriosityCycle(): Promise<{ status: string; stored: number }> {
  const r = await fetch(`${BASE}/curiosity/trigger`, { method: 'POST' })
  if (!r.ok) throw new Error(`curiosity trigger: ${r.status}`)
  return r.json()
}

export async function toggleMcpServer(
  name: string,
  enabled: boolean,
): Promise<McpServerStatus> {
  const r = await fetch(`${BASE}/mcp/servers/${encodeURIComponent(name)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled }),
  })
  if (!r.ok) {
    const body = await r.json().catch(() => ({ detail: r.statusText }))
    throw new Error(body.detail ?? `toggle server: ${r.status}`)
  }
  return r.json()
}

export async function reloadMcpServers(): Promise<McpServerStatus[]> {
  const r = await fetch(`${BASE}/mcp/reload`, { method: 'POST' })
  if (!r.ok) throw new Error(`reload: ${r.status}`)
  return r.json()
}

export interface CopilotTestResponse {
  ok: boolean
  model?: string
  error?: string
}

export async function testCopilot(): Promise<CopilotTestResponse> {
  const r = await fetch(`${BASE}/setup/copilot/test`, { method: 'POST' })
  if (!r.ok) {
    const body = await r.json().catch(() => ({ detail: r.statusText }))
    throw new Error(body.detail ?? `copilot test: ${r.status}`)
  }
  return r.json()
}

// ── Wiki ───────────────────────────────────────────────────────────────────

export interface WikiNode {
  id: string
  title: string
  category: 'entities' | 'concepts' | 'sources' | 'syntheses' | string
  tags: string[]
  summary: string
  path: string
  degree: number
}

export interface WikiLink {
  source: string
  target: string
  label: string
}

export interface WikiGraphData {
  nodes: WikiNode[]
  links: WikiLink[]
  stats: {
    total_pages: number
    total_links: number
    by_category: Record<string, number>
  }
}

export async function fetchWikiGraph(): Promise<WikiGraphData> {
  const r = await fetch(`${BASE}/wiki/graph`)
  if (!r.ok) throw new Error(`wiki graph: ${r.status}`)
  return r.json()
}

export async function fetchWikiPage(path: string): Promise<string> {
  const r = await fetch(`${BASE}/wiki/page?path=${encodeURIComponent(path)}`)
  if (!r.ok) throw new Error(`wiki page: ${r.status}`)
  const data = await r.json()
  return data.content as string
}

export async function fetchWikiLog(last = 20): Promise<string> {
  const r = await fetch(`${BASE}/wiki/log?last=${last}`)
  if (!r.ok) throw new Error(`wiki log: ${r.status}`)
  const data = await r.json()
  return data.content as string
}

export async function ingestWikiSource(
  title: string,
  sourceText: string,
  sourceType = 'text',
): Promise<{ title: string; slug: string; pages_written: string[]; entities: number; concepts: number; summary: string }> {
  const r = await fetch(`${BASE}/wiki/ingest`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title, source_text: sourceText, source_type: sourceType }),
  })
  if (!r.ok) {
    const body = await r.json().catch(() => ({ detail: r.statusText }))
    throw new Error(body.detail ?? `wiki ingest: ${r.status}`)
  }
  return r.json()
}

export type WikiIngestResult = { title: string; slug: string; pages_written: string[]; entities: number; concepts: number; summary: string }

export async function ingestWikiFiles(
  files: File[],
  sourceType = 'document',
): Promise<WikiIngestResult[]> {
  const form = new FormData()
  for (const f of files) form.append('files', f)
  const r = await fetch(`${BASE}/wiki/ingest_files?source_type=${encodeURIComponent(sourceType)}`, {
    method: 'POST',
    body: form,
  })
  if (!r.ok) {
    const body = await r.json().catch(() => ({ detail: r.statusText }))
    throw new Error(body.detail ?? `wiki ingest_files: ${r.status}`)
  }
  return r.json()
}

export async function queryWiki(
  question: string,
): Promise<{ question: string; answer: string; pages_consulted: string[]; synthesis_page: string | null }> {
  const r = await fetch(`${BASE}/wiki/query`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
  })
  if (!r.ok) throw new Error(`wiki query: ${r.status}`)
  return r.json()
}
