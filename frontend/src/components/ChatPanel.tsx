import { useState, useRef, useEffect, useCallback } from 'react'
import { streamInteract, type MetaState } from '../api'

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  streaming?: boolean
}

interface Props {
  onMetaStateUpdate?: (ms: MetaState) => void
}

export default function ChatPanel({ onMetaStateUpdate }: Props) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const stopRef = useRef<(() => void) | null>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

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
      (ms) => {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMsg.id ? { ...m, streaming: false } : m
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
            <div className={`chat-bubble${msg.streaming && !msg.content ? ' streaming-cursor' : ''}`}>
              {msg.content}
              {msg.streaming && msg.content && <span className="streaming-cursor" />}
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
      </div>
    </>
  )
}
