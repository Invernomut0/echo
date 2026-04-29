import { useState, useRef, useEffect, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import type { Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { streamInteract, type MetaState, type MemorySources } from '../api'

const markdownComponents: Components = {
  code({ children, className, node: _node, ...rest }) {
    const match = /language-(\w+)/.exec(className ?? '')
    const text = String(children)
    const isBlock = Boolean(match) || text.endsWith('\n')
    if (isBlock) {
      return (
        <SyntaxHighlighter
          style={oneDark}
          language={match?.[1] ?? 'text'}
          PreTag="div"
          customStyle={{ borderRadius: 8, fontSize: 13, margin: '8px 0', padding: '12px 16px' }}
        >
          {text.replace(/\n$/, '')}
        </SyntaxHighlighter>
      )
    }
    return (
      <code className={className} {...rest}>
        {children}
      </code>
    )
  },
}

function MarkdownContent({ content }: { content: string }) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
      {content}
    </ReactMarkdown>
  )
}

function MemoryBadges({ sources }: { sources?: MemorySources }) {
  if (!sources || (sources.episodic === 0 && sources.semantic === 0)) return null
  return (
    <div className="memory-badges">
      {sources.episodic > 0 && (
        <span
          className="memory-badge episodic"
          title={`${sources.episodic} memoria${sources.episodic > 1 ? ' episodiche' : ' episodica'} usata`}
        >
          <span className="memory-badge-dot" />
          episodica&nbsp;&times;{sources.episodic}
        </span>
      )}
      {sources.semantic > 0 && (
        <span
          className="memory-badge semantic"
          title={`${sources.semantic} memoria${sources.semantic > 1 ? ' semantiche' : ' semantica'} usata`}
        >
          <span className="memory-badge-dot" />
          semantica&nbsp;&times;{sources.semantic}
        </span>
      )}
    </div>
  )
}

const STORAGE_KEY = 'echo_chat_messages'

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  streaming?: boolean
  memorySources?: MemorySources
}

function loadMessages(): Message[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as Message[]
    // strip any leftover streaming flag from a previous interrupted session
    return parsed.map((m) => ({ ...m, streaming: false }))
  } catch {
    return []
  }
}

function saveMessages(msgs: Message[]) {
  try {
    // only persist completed messages (no partial streaming state)
    const toSave = msgs.map((m) => ({ ...m, streaming: false }))
    localStorage.setItem(STORAGE_KEY, JSON.stringify(toSave))
  } catch { /* storage full or unavailable */ }
}

interface Props {
  onMetaStateUpdate?: (ms: MetaState) => void
}

export default function ChatPanel({ onMetaStateUpdate }: Props) {
  const [messages, setMessages] = useState<Message[]>(loadMessages)
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const stopRef = useRef<(() => void) | null>(null)

  // Persist to localStorage whenever streaming ends (not during, to avoid partial states)
  useEffect(() => {
    if (!streaming) {
      saveMessages(messages)
    }
  }, [streaming, messages])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const clearChat = useCallback(() => {
    if (streaming) return
    stopRef.current?.()
    setMessages([])
    setInput('')
    localStorage.removeItem(STORAGE_KEY)
  }, [streaming])

  const send = useCallback(() => {
    const text = input.trim()
    if (!text || streaming) return
    setInput('')

    const userMsg: Message = { id: crypto.randomUUID(), role: 'user', content: text }
    const assistantMsg: Message = { id: crypto.randomUUID(), role: 'assistant', content: '', streaming: true }

    setMessages((prev) => [...prev, userMsg, assistantMsg])
    setStreaming(true)

    const history = messages.map((m) => ({ role: m.role, content: m.content }))

    stopRef.current = streamInteract(
      text,
      history,
      (delta) => {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMsg.id
              ? { ...m, content: m.content + delta }
              : m
          )
        )
      },
      (ms, memorySources) => {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMsg.id ? { ...m, streaming: false, memorySources } : m
          )
        )
        setStreaming(false)
        onMetaStateUpdate?.(ms)
      },
      (err) => {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMsg.id
              ? { ...m, content: `[Error: ${err}]`, streaming: false }
              : m
          )
        )
        setStreaming(false)
      }
    )
  }, [input, streaming, messages, onMetaStateUpdate])

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  return (
    <>
      <div className="chat-container">
        {messages.length === 0 && (
          <div style={{ textAlign: 'center', color: '#475569', paddingTop: 60 }}>
            <div style={{ fontSize: 32, marginBottom: 8 }}>◈</div>
            <div style={{ fontSize: 13, fontWeight: 600, color: '#94a3b8' }}>ECHO is ready</div>
            <div style={{ fontSize: 11, marginTop: 4 }}>Start a conversation</div>
          </div>
        )}
        {messages.map((msg) => (
          <div key={msg.id} className={`chat-message ${msg.role}`}>
            <div className={`chat-bubble${msg.role === 'assistant' ? ' md' : ''}${msg.streaming && !msg.content ? ' streaming-cursor' : ''}`}>
              {msg.role === 'assistant'
                ? <MarkdownContent content={msg.content} />
                : msg.content}
              {msg.streaming && msg.content && <span className="streaming-cursor" />}
              {msg.role === 'assistant' && !msg.streaming && (
                <MemoryBadges sources={msg.memorySources} />
              )}
            </div>
            <div className="chat-meta">{msg.role === 'user' ? 'You' : 'ECHO'}</div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      <div className="chat-input-row">
        <textarea
          className="chat-textarea"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKey}
          placeholder="Message ECHO… (Enter to send)"
          rows={1}
          disabled={streaming}
        />
        <button className="send-btn" onClick={send} disabled={streaming || !input.trim()}>
          {streaming ? 'Thinking…' : 'Send'}
        </button>
        {messages.length > 0 && !streaming && (
          <button
            className="send-btn"
            onClick={clearChat}
            title="Clear conversation"
            style={{ background: 'rgba(239,68,68,0.12)', border: '1px solid rgba(239,68,68,0.25)', color: '#f87171', minWidth: 36, padding: '0 10px' }}
          >
            ✕
          </button>
        )}
      </div>
    </>
  )
}
