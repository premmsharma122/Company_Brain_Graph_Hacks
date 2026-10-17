import { useEffect, useState } from 'react'
import { getNode } from '../api'
import { KIND_COLOR } from './GraphView'

const short = (s, n = 90) => (s && s.length > n ? s.slice(0, n) + '...' : s)

function Sources({ resp, onSelect }) {
  const [labels, setLabels] = useState({})
  useEffect(() => {
    let alive = true
    const ids = (resp?.sources || []).slice(0, 25)
    Promise.all(ids.map((id) => getNode(id).then((n) => [id, n]).catch(() => [id, null]))).then((pairs) => {
      if (alive) setLabels(Object.fromEntries(pairs))
    })
    return () => { alive = false }
  }, [resp])

  if (!resp?.sources?.length) return <p className="hint">No document, ticket or message sources for this answer (it is derived from graph structure).</p>
  return (
    <ul className="list">
      {resp.sources.slice(0, 25).map((id) => {
        const n = labels[id]
        const p = n?.properties || {}
        return (
          <li key={id} onClick={() => onSelect(id)}>
            <span className="dot" style={{ background: KIND_COLOR[n?.kind] || '#64748b' }} />
            <b>{id}</b> <span className="dim">{n?.kind}</span>
            <div className="dim">{short(p.title || p.text || p.summary)} {p.date ? `(${p.date})` : ''}</div>
          </li>
        )
      })}
    </ul>
  )
}

function Chain({ resp, onSelect }) {
  if (!resp?.chain?.length) return <p className="hint">Ask about a decision (e.g. "Why did we move to Postgres?") to see its provenance chain.</p>
  return (
    <ol className="chain">
      {resp.chain.map((d, i) => (
        <li key={d.id}>
          <div className="chain-card" onClick={() => onSelect(d.id)}>
            <b>{d.id}</b> <span className={`pill ${d.is_current ? 'ok' : 'old'}`}>{d.is_current ? 'current' : 'superseded'}</span>
            <div>{d.summary}</div>
            <div className="dim">{d.date} by {d.made_by || 'unknown'}</div>
            <div className="chain-src">
              {(d.sources || []).filter((s) => s.id).map((s) => (
                <button key={s.id} className="link" onClick={(e) => { e.stopPropagation(); onSelect(s.id) }}>{s.id}</button>
              ))}
            </div>
          </div>
          {i < resp.chain.length - 1 && <div className="arrow">superseded by</div>}
        </li>
      ))}
    </ol>
  )
}

function Inspect({ id, onSelect }) {
  const [node, setNode] = useState(null)
  const [err, setErr] = useState('')
  useEffect(() => {
    if (!id) return
    setNode(null); setErr('')
    getNode(id).then(setNode).catch(() => setErr('Node not found'))
  }, [id])
  if (!id) return <p className="hint">Click a node in the graph or a source to inspect it.</p>
  if (err) return <p className="hint">{err}</p>
  if (!node) return <p className="hint">Loading...</p>
  const rel = (list, dir) => list.map((r, i) => (
    <li key={dir + i} onClick={() => onSelect(r.id)}>
      <span className="dim">{dir === 'out' ? '-' : '<-'}[{r.rel}]{dir === 'out' ? '->' : '-'}</span> <b>{r.id}</b> <span className="dim">{short(r.label, 60)}</span>
    </li>
  ))
  return (
    <div>
      <h4><span className="dot" style={{ background: KIND_COLOR[node.kind] }} />{node.kind} {node.id}</h4>
      <table className="props"><tbody>
        {Object.entries(node.properties).filter(([k]) => k !== 'labels').map(([k, v]) => <tr key={k}><td>{k}</td><td>{String(v)}</td></tr>)}
      </tbody></table>
      <h5>Relationships</h5>
      <ul className="list">{rel(node.outgoing, 'out')}{rel(node.incoming, 'in')}</ul>
    </div>
  )
}

export default function SourcesPanel({ resp, selected, onSelect }) {
  const [tab, setTab] = useState('sources')
  useEffect(() => { if (selected) setTab('inspect') }, [selected])
  const tabs = [['sources', 'Sources'], ['chain', 'Provenance'], ['cypher', 'Cypher'], ['rows', 'Rows'], ['inspect', 'Inspect']]
  return (
    <aside className="panel">
      <div className="tabs">
        {tabs.map(([k, label]) => <button key={k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}>{label}</button>)}
      </div>
      <div className="tab-body">
        {tab === 'sources' && <Sources resp={resp} onSelect={onSelect} />}
        {tab === 'chain' && <Chain resp={resp} onSelect={onSelect} />}
        {tab === 'cypher' && (resp?.cypher
          ? <><pre className="code">{resp.cypher}</pre><div className="dim">params</div><pre className="code">{JSON.stringify(resp.params, null, 2)}</pre></>
          : <p className="hint">Ask a question to see the exact Cypher that produced the answer.</p>)}
        {tab === 'rows' && (resp ? <pre className="code">{JSON.stringify(resp.rows, null, 2)}</pre> : <p className="hint">No result yet.</p>)}
        {tab === 'inspect' && <Inspect id={selected} onSelect={onSelect} />}
      </div>
    </aside>
  )
}
