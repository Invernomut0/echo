import { useState, useEffect, useCallback } from 'react'

const API = '/api/consolidation'

async function fetchSelfGrowth(): Promise<string> {
  const res = await fetch(`${API}/self-growth`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  const data = await res.json()
  return data.content as string
}

interface NoteItem { name: string; date: string; title: string }

async function fetchNotesList(): Promise<NoteItem[]> {
  const res = await fetch(`${API}/notes`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  const data = await res.json()
  return data.notes as NoteItem[]
}

async function fetchNote(name: string): Promise<string> {
  const res = await fetch(`${API}/notes/${encodeURIComponent(name)}`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  const data = await res.json()
  return data.content as string
}

// ── Simple markdown renderer ─────────────────────────────────────────────────

function inlineMarkdown(text: string): (string | JSX.Element)[] {
  const parts: (string | JSX.Element)[] = []
  const re = /(\*\*(.+?)\*\*|\*(.+?)\*|`(.+?)`)/g
  let last = 0
  let m: RegExpExecArray | null
  let key = 0
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index))
    if (m[2]) parts.push(<strong key={key++}>{m[2]}</strong>)
    else if (m[3]) parts.push(<em key={key++}>{m[3]}</em>)
    else if (m[4]) parts.push(<code key={key++} className="emd-code">{m[4]}</code>)
    last = m.index + m[0].length
  }
  if (last < text.length) parts.push(text.slice(last))
  return parts
}

function renderMarkdown(md: string): JSX.Element[] {
  const lines = md.split('\n')
  const elements: JSX.Element[] = []
  let key = 0

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    if (line.startsWith('# ')) {
      elements.push(<h1 key={key++} className="emd-h1">{line.slice(2)}</h1>)
    } else if (line.startsWith('## ')) {
      elements.push(<h2 key={key++} className="emd-h2">{line.slice(3)}</h2>)
    } else if (line.startsWith('### ')) {
      elements.push(<h3 key={key++} className="emd-h3">{line.slice(4)}</h3>)
    } else if (line.match(/^---+$/)) {
      elements.push(<hr key={key++} className="emd-hr" />)
    } else if (line.startsWith('- ') || line.startsWith('* ')) {
      elements.push(
        <li key={key++} className="emd-li">
          {inlineMarkdown(line.slice(2))}
        </li>
      )
    } else if (line.startsWith('> ')) {
      elements.push(
        <blockquote key={key++} className="emd-blockquote">
          {inlineMarkdown(line.slice(2))}
        </blockquote>
      )
    } else if (line.startsWith('```')) {
      // collect until closing ```
      const codeLines: string[] = []
      i++
      while (i < lines.length && !lines[i].startsWith('```')) {
        codeLines.push(lines[i])
        i++
      }
      elements.push(
        <pre key={key++} className="emd-codeblock">
          <code>{codeLines.join('\n')}</code>
        </pre>
      )
    } else if (line.trim() === '') {
      elements.push(<div key={key++} className="emd-spacer" />)
    } else {
      elements.push(
        <p key={key++} className="emd-p">
          {inlineMarkdown(line)}
        </p>
      )
    }
  }
  return elements
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function SelfGrowthPanel() {
  const [content, setContent] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [lastUpdated, setLastUpdated] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [rawMode, setRawMode] = useState(false)

  // Notes state
  const [notes, setNotes] = useState<NoteItem[]>([])
  const [notesExpanded, setNotesExpanded] = useState(false)
  const [selectedNote, setSelectedNote] = useState<string | null>(null)
  const [noteContent, setNoteContent] = useState<string | null>(null)
  const [noteLoading, setNoteLoading] = useState(false)
  const [noteError, setNoteError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const text = await fetchSelfGrowth()
      setContent(text)
      setLastUpdated(new Date().toLocaleTimeString())
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  const loadNotes = useCallback(async () => {
    try {
      const list = await fetchNotesList()
      setNotes(list)
    } catch (_) {
      // non-critical
    }
  }, [])

  const openNote = useCallback(async (name: string) => {
    if (selectedNote === name) {
      setSelectedNote(null)
      setNoteContent(null)
      return
    }
    setSelectedNote(name)
    setNoteLoading(true)
    setNoteError(null)
    setNoteContent(null)
    try {
      const text = await fetchNote(name)
      setNoteContent(text)
    } catch (e) {
      setNoteError(String(e))
    } finally {
      setNoteLoading(false)
    }
  }, [selectedNote])

  useEffect(() => { load() }, [load])
  useEffect(() => { loadNotes() }, [loadNotes])

  return (
    <div className="echo-md-panel">
      {/* Header */}
      <div className="echo-md-header">
        <div className="echo-md-title-row">
          <span className="echo-md-title">self_growth.md</span>
          <span className="echo-md-subtitle">ECHO's autonomous growth &amp; development journal</span>
        </div>
        <div className="echo-md-actions">
          {lastUpdated && (
            <span className="echo-md-timestamp">fetched {lastUpdated}</span>
          )}
          <button
            className={`echo-md-btn${rawMode ? ' active' : ''}`}
            onClick={() => setRawMode(r => !r)}
            title="Toggle raw markdown"
          >
            {rawMode ? 'Rendered' : 'Raw'}
          </button>
          <button
            className="echo-md-btn"
            onClick={load}
            disabled={loading}
            title="Reload file"
          >
            {loading ? '…' : '↻'}
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="echo-md-error">{error}</div>
      )}

      {/* Content */}
      <div className="echo-md-body">
        {loading && !content ? (
          <div className="echo-md-loading">Loading…</div>
        ) : content ? (
          rawMode ? (
            <pre className="echo-md-raw">{content}</pre>
          ) : (
            <div className="echo-md-rendered">
              {renderMarkdown(content)}
            </div>
          )
        ) : null}
      </div>

      {/* ── Notes section ─────────────────────────────────────────────────── */}
      <div className="echo-notes-section">
        <button
          className="echo-notes-toggle"
          onClick={() => setNotesExpanded(e => !e)}
        >
          <span className="echo-notes-toggle-icon">{notesExpanded ? '▾' : '▸'}</span>
          <span className="echo-notes-toggle-label">
            Change notes ({notes.length})
          </span>
        </button>

        {notesExpanded && (
          <div className="echo-notes-list">
            {notes.length === 0 ? (
              <div className="echo-notes-empty">No notes found.</div>
            ) : (
              notes.map(n => (
                <div key={n.name} className="echo-note-item">
                  <button
                    className={`echo-note-row${selectedNote === n.name ? ' selected' : ''}`}
                    onClick={() => openNote(n.name)}
                  >
                    <span className="echo-note-date">{n.date}</span>
                    <span className="echo-note-title">{n.title}</span>
                    <span className="echo-note-chevron">{selectedNote === n.name ? '▴' : '▾'}</span>
                  </button>
                  {selectedNote === n.name && (
                    <div className="echo-note-body">
                      {noteLoading && <div className="echo-md-loading">Loading…</div>}
                      {noteError && <div className="echo-md-error">{noteError}</div>}
                      {noteContent && (
                        <div className="echo-md-rendered echo-note-content">
                          {renderMarkdown(noteContent)}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        )}
      </div>
    </div>
  )
}
