import { useEffect, useState } from 'react'
import { getPeople, ingest, errorText } from '../api'

const EXAMPLE = 'Decision: we are reversing D-008. Going back to Kafka for the notification queue because SQS fan-out costs too much.'

export default function LiveUpdate({ onClose, onDone }) {
  const [people, setPeople] = useState([])
  const [author, setAuthor] = useState('Priya Nair')
  const [text, setText] = useState(EXAMPLE)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  useEffect(() => { getPeople().then((p) => setPeople(p.filter((x) => x.active))).catch(() => {}) }, [])

  const submit = async () => {
    setBusy(true); setErr('')
    try { onDone(await ingest({ text, author, channel: '#live' })) } catch (e) { setErr(errorText(e)) } finally { setBusy(false) }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3>Live update: paste a new message</h3>
        <p className="hint">Ingest writes the message, extracts topics and decisions, and links a reversal with a SUPERSEDES edge. Then ask the decision question again.</p>
        <label>Author
          <select value={author} onChange={(e) => setAuthor(e.target.value)}>
            {people.length === 0 && <option>{author}</option>}
            {people.map((p) => <option key={p.id}>{p.name}</option>)}
          </select>
        </label>
        <label>Message
          <textarea rows={4} value={text} onChange={(e) => setText(e.target.value)} />
        </label>
        {err && <p className="error">{err}</p>}
        <div className="row">
          <button className="ghost" onClick={onClose}>Cancel</button>
          <button onClick={submit} disabled={busy || !text.trim()}>{busy ? 'Ingesting...' : 'Ingest message'}</button>
        </div>
      </div>
    </div>
  )
}
