import { useEffect, useRef, useState, useCallback } from 'react'
import { fetchState, fetchHistory, fetchGraph, fetchMemories, type StateResponse, type HistoryPoint, type GraphResponse, type MemoryItem } from './api'

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

export function useGraph() {
  const [graph, setGraph] = useState<GraphResponse>({ nodes: [], edges: [], coherence_score: 1 })

  const refresh = useCallback(async () => {
    try { setGraph(await fetchGraph()) } catch { /* ignore */ }
  }, [])

  useEffect(() => {
    refresh()
    const id = setInterval(refresh, POLL_MS * 2)
    return () => clearInterval(id)
  }, [refresh])

  return { graph, refresh }
}

export function useMemories(limit = 50) {
  const [memories, setMemories] = useState<MemoryItem[]>([])
  const [total, setTotal] = useState(0)

  useEffect(() => {
    const load = async () => {
      try {
        const r = await fetchMemories(limit)
        setMemories(r.items)
        setTotal(r.total)
      } catch { /* ignore */ }
    }
    load()
    const id = setInterval(load, POLL_MS * 3)
    return () => clearInterval(id)
  }, [limit])

  return { memories, total }
}
