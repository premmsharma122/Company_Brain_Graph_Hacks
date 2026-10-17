import { useEffect, useRef, useState } from 'react'

export default function Chat({ messages, loading, suggestions, onAsk, onOpenLive }) {
  const [text, setText] = useState('')
  const bottom = useRef(null)
  useEffect(() => { bottom.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, loading])

  const submit = (e) => {
    e.preventDefault()
    if (!text.trim() || loading) return
    onAsk(text.trim())
    setText('')
  }

  return (
    <section className="chat">
      <div className="messages">
        {messages.length === 0 && (
          <div className="empty">
            <p>Ask how Acme Payments works. Every answer comes from a graph traversal, and you can inspect the Cypher.</p>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            <div className="bubble">{m.text}</div>
            {m.resp && (
              <div className="meta">
                <span className="tag">{m.resp.tool || 'no tool'}</span>
                <span className="tag dim">routed: {m.resp.routed_by}</span>
                <span className="tag dim">answer: {m.resp.answered_by}{m.resp.cached ? ' (cached)' : ''}</span>
              </div>
            )}
            {m.resp?.warnings?.length > 0 && (
              <ul className="warnings">{m.resp.warnings.map((w, j) => <li key={j}>{w}</li>)}</ul>
            )}
          </div>
        ))}
        {loading && <div className="msg assistant"><div className="bubble typing">Traversing the graph...</div></div>}
        <div ref={bottom} />
      </div>

      <div className="chips">
        {suggestions.map((q) => (
          <button key={q} className="chip" disabled={loading} onClick={() => onAsk(q)}>{q}</button>
        ))}
        <button className="chip live" onClick={onOpenLive}>Live update: reverse a decision</button>
      </div>

      <form className="composer" onSubmit={submit}>
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Ask about owners, experts, decisions, risk..." />
        <button type="submit" disabled={loading || !text.trim()}>Ask</button>
      </form>
    </section>
  )
}
