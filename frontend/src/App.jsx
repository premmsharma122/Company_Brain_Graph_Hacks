import { useCallback, useEffect, useState } from 'react'
import Chat from './components/Chat'
import GraphView from './components/GraphView'
import SourcesPanel from './components/SourcesPanel'
import LiveUpdate from './components/LiveUpdate'
import { chat, errorText, getDemoQuestions, getHealth, getOverview, getSubgraph } from './api'

const EMPTY = { nodes: [], links: [] }

export default function App() {
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)
  const [suggestions, setSuggestions] = useState([])
  const [overview, setOverview] = useState(EMPTY)
  const [graph, setGraph] = useState(EMPTY)
  const [highlight, setHighlight] = useState(new Set())
  const [mode, setMode] = useState('overview')
  const [resp, setResp] = useState(null)
  const [selected, setSelected] = useState(null)
  const [live, setLive] = useState(false)
  const [health, setHealth] = useState(null)

  useEffect(() => {
    getHealth().then(setHealth).catch((e) => setHealth({ status: 'down', error: errorText(e) }))
    getDemoQuestions().then(setSuggestions).catch(() => {})
    getOverview().then((g) => { setOverview(g); setGraph(g) }).catch(() => {})
  }, [])

  const showSubgraph = useCallback(async (ids) => {
    if (!ids?.length) return
    try {
      const g = await getSubgraph(ids)
      setGraph(g); setHighlight(new Set(g.highlight)); setMode('answer')
    } catch { /* keep current graph */ }
  }, [])

  const reset = () => { setGraph(overview); setHighlight(new Set()); setMode('overview') }

  const ask = useCallback(async (question) => {
    setMessages((m) => [...m, { role: 'user', text: question }])
    setLoading(true)
    try {
      const r = await chat(question)
      setMessages((m) => [...m, { role: 'assistant', text: r.answer, resp: r }])
      setResp(r); setSelected(null)
      await showSubgraph(r.highlight)
    } catch (e) {
      setMessages((m) => [...m, { role: 'assistant', text: `Error: ${errorText(e)}` }])
    } finally { setLoading(false) }
  }, [showSubgraph])

  const onLiveDone = async (r) => {
    setLive(false)
    const t = r.touched || {}
    const ids = [...(t.messages || []), ...(t.decisions || []), ...(t.superseded || []), ...(t.services || []), ...(t.topics || [])]
    const note = r.touched?.superseded?.length
      ? `Ingested ${r.message_id} (parsed by ${r.parsed_by}). New decision ${t.decisions[0]} now supersedes ${t.superseded.join(', ')}.`
      : `Ingested ${r.message_id} (parsed by ${r.parsed_by}). ${t.decisions?.length ? 'Recorded decision ' + t.decisions[0] + '.' : 'No decision detected.'}`
    setMessages((m) => [...m, { role: 'assistant', text: note }])
    await showSubgraph(ids)
    if (t.superseded?.length) await ask(`Is ${t.superseded[0]} still the plan?`)
  }

  return (
    <div className="app">
      <header>
        <h1>OrgMind <span>Company Brain</span></h1>
        <div className="status">
          {health?.status === 'ok'
            ? <span className="ok">graph online: {health.nodes} nodes, llm: {health.llm}</span>
            : <span className="bad">backend unreachable {health?.error ? `(${health.error})` : ''}</span>}
        </div>
      </header>
      <main>
        <Chat messages={messages} loading={loading} suggestions={suggestions} onAsk={ask} onOpenLive={() => setLive(true)} />
        <GraphView graph={graph} highlight={highlight} selected={selected} onSelect={setSelected} mode={mode} onReset={reset} />
        <SourcesPanel resp={resp} selected={selected} onSelect={setSelected} />
      </main>
      {live && <LiveUpdate onClose={() => setLive(false)} onDone={onLiveDone} />}
    </div>
  )
}
