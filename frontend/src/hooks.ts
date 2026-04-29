import { useEffect, useRef, useState, useCallback } from 'react'
import {
  fetchState, fetchHistory, fetchGraph, fetchMemories, fetchDreams, fetchHeartbeat,
  fetchVectorStatus, fetchSemanticMemories, fetchPipelineTrace,
  type StateResponse, type HistoryPoint, type GraphResponse, type MemoryItem,
  type DreamEntry, type HeartbeatStatus, type VectorStoreStatus, type PipelineTrace,
} from './api'

// Polling interval for live data
const POLL_MS = 3000

export function useEchoState() {
  const [state, setState] = useState<StateResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      const s = await fetchState()
      setState(s)
      setError(null)
    } catch (e) {
      setError(String(e))
    }
  }, [])

  useEffect(() => {
    refresh()
    const id = setInterval(refresh, POLL_MS)
    return () => clearInterval(id)
  }, [refresh])

  return { state, error, refresh }
}

export function useHistory(limit = 60) {
  const [history, setHistory] = useState<HistoryPoint[]>([])

  useEffect(() => {
    const load = async () => {
      try { setHistory(await fetchHistory(limit)) } catch { /* ignore */ }
    }
    load()
    const id = setInterval(load, POLL_MS * 2)
    return () => clearInterval(id)
  }, [limit])

  return history
}

export function useAnalyticsHistory(limit = 200) {
  const [history, setHistory] = useState<HistoryPoint[]>([])

  useEffect(() => {
    const load = async () => {
      try { setHistory(await fetchHistory(limit)) } catch { /* ignore */ }
    }
    load()
    const id = setInterval(load, 8000)
    return () => clearInterval(id)
  }, [limit])

  return history
}

export function useGraph(active: boolean) {
  const [graph, setGraph] = useState<GraphResponse>({ nodes: [], edges: [], coherence_score: 1 })
  // Track a topology+attribute signature so we only call setGraph (and trigger
  // a downstream 3D-graph update) when the data actually changed between polls.
  const sigRef = useRef('')

  const refresh = useCallback(async () => {
    try {
      const data = await fetchGraph()
      const nodesSig = data.nodes.map(n => `${n.id}:${n.confidence.toFixed(2)}`).sort().join(',')
      const edgesSig = data.edges.map(e => `${e.source}>${e.target}:${e.relation}:${e.weight.toFixed(2)}`).sort().join(',')
      const sig = `${nodesSig}|${edgesSig}`
      if (sig !== sigRef.current) {
        sigRef.current = sig
        setGraph(data)
      }
    } catch { /* ignore */ }
  }, [])

  // Fetch immediately when tab becomes active, then poll every 5 s while visible
  useEffect(() => {
    if (!active) return
    refresh()
    const id = setInterval(refresh, 5000)
    return () => clearInterval(id)
  }, [active, refresh])

  return { graph, refresh }
}

export function useMemories(limit = 50) {
  const [memories, setMemories] = useState<MemoryItem[]>([])
  const [total, setTotal] = useState(0)

  const load = useCallback(async () => {
    try {
      const r = await fetchMemories(limit)
      setMemories(r.items)
      setTotal(r.total)
    } catch { /* ignore */ }
  }, [limit])

  useEffect(() => {
    load()
    const id = setInterval(load, POLL_MS)
    return () => clearInterval(id)
  }, [load])

  return { memories, total, refresh: load }
}

export function useDreams(active: boolean) {
  const [dreams, setDreams] = useState<DreamEntry[]>([])
  const [loading, setLoading] = useState(false)
  const [tick, setTick] = useState(0)

  const refresh = useCallback(() => setTick(t => t + 1), [])

  useEffect(() => {
    if (!active) return
    let cancelled = false
    const load = () => {
      fetchDreams()
        .then(data => { if (!cancelled) setDreams(data) })
        .catch(() => {})
        .finally(() => { if (!cancelled) setLoading(false) })
    }
    setLoading(true)
    load()
    const id = setInterval(load, 8000)
    return () => { cancelled = true; clearInterval(id) }
  }, [active, tick])

  return { dreams, loading, refresh }
}

export function useHeartbeat(active: boolean) {
  const [status, setStatus] = useState<HeartbeatStatus | null>(null)

  useEffect(() => {
    if (!active) return
    fetchHeartbeat().then(setStatus)
    const id = setInterval(() => fetchHeartbeat().then(setStatus), 30_000)
    return () => clearInterval(id)
  }, [active])

  return status
}

export function useVectorStatus() {
  const [status, setStatus] = useState<VectorStoreStatus | null>(null)

  useEffect(() => {
    const load = () => fetchVectorStatus().then(setStatus).catch(() => {})
    load()
    const id = setInterval(load, 5000)
    return () => clearInterval(id)
  }, [])

  return status
}

export function useSemanticMemories(limit = 50) {
  const [data, setData] = useState<{ total: number; items: MemoryItem[] } | null>(null)

  useEffect(() => {
    fetchSemanticMemories(limit).then(setData).catch(() => {})
  }, [limit])

  return data
}

/** Poll /api/pipeline/trace every 1.5 s while the panel is active.
 *  Stops polling as soon as post_interact_complete becomes true,
 *  and resumes when a new interaction_id appears. */
export function usePipelineTrace(active: boolean) {
  const [trace, setTrace] = useState<PipelineTrace | null>(null)
  const lastIdRef = useRef<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      const t = await fetchPipelineTrace()
      if (!t) return
      setTrace(t)
      lastIdRef.current = t.interaction_id
    } catch { /* ignore */ }
  }, [])

  useEffect(() => {
    if (!active) return
    refresh()
    const id = setInterval(refresh, 1500)
    return () => clearInterval(id)
  }, [active, refresh])

  return { trace, refresh }
}
