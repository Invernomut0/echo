import { useState, useEffect, useCallback } from 'react'

const API = '/api/consolidation'

async function fetchSelfGrowth(): Promise<string> {
  const res = await fetch(`${API}/self-growth`)
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

  useEffect(() => { load() }, [load])

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
    </div>
  )
}
