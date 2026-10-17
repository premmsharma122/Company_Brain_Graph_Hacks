import { useEffect, useMemo, useRef } from 'react'
import ForceGraph2D from 'react-force-graph-2d'

export const KIND_COLOR = {
  Person: '#f59e0b', Team: '#38bdf8', Service: '#34d399', Project: '#a78bfa', Document: '#f472b6',
  Ticket: '#fb923c', Message: '#94a3b8', Topic: '#22d3ee', Decision: '#ef4444',
}

export default function GraphView({ graph, highlight, selected, onSelect, mode, onReset }) {
  const fg = useRef(null)
  // react-force-graph mutates its input (links get node objects); hand it a fresh copy per dataset
  const data = useMemo(() => ({
    nodes: graph.nodes.map((n) => ({ ...n })),
    links: graph.links.map((l) => ({ ...l })),
  }), [graph])

  useEffect(() => {
    const t = setTimeout(() => fg.current?.zoomToFit(400, 60), 600)
    return () => clearTimeout(t)
  }, [data])

  const hasHL = highlight.size > 0
  const paint = (node, ctx, scale) => {
    const hl = highlight.has(node.id)
    const dim = hasHL && !hl
    const r = hl ? 7 : 4.5
    ctx.globalAlpha = dim ? 0.25 : 1
    ctx.beginPath()
    ctx.arc(node.x, node.y, r, 0, 2 * Math.PI)
    ctx.fillStyle = KIND_COLOR[node.kind] || '#cbd5e1'
    ctx.fill()
    if (hl || node.id === selected) {
      ctx.lineWidth = 2 / scale
      ctx.strokeStyle = node.id === selected ? '#ffffff' : '#fde047'
      ctx.stroke()
    }
    if (hl || scale > 2.2) {
      const label = String(node.label || node.id).slice(0, 34)
      ctx.font = `${(hl ? 11 : 9) / scale}px sans-serif`
      ctx.fillStyle = '#e2e8f0'
      ctx.textAlign = 'center'
      ctx.fillText(label, node.x, node.y + r + 9 / scale)
    }
    ctx.globalAlpha = 1
  }

  return (
    <section className="graph">
      <div className="graph-bar">
        <strong>{mode === 'answer' ? 'Subgraph used in the answer' : 'Company map (teams, services, projects)'}</strong>
        {mode === 'answer' && <button className="link" onClick={onReset}>Show full map</button>}
        <div className="legend">
          {Object.entries(KIND_COLOR).map(([k, c]) => (
            <span key={k}><i style={{ background: c }} />{k}</span>
          ))}
        </div>
      </div>
      <div className="graph-canvas">
        <ForceGraph2D
          ref={fg}
          graphData={data}
          backgroundColor="#0b1220"
          nodeCanvasObject={paint}
          nodePointerAreaPaint={(n, color, ctx) => { ctx.fillStyle = color; ctx.beginPath(); ctx.arc(n.x, n.y, 8, 0, 2 * Math.PI); ctx.fill() }}
          linkColor={(l) => (hasHL && highlight.has(l.source.id) && highlight.has(l.target.id) ? '#fde047' : '#334155')}
          linkWidth={(l) => (hasHL && highlight.has(l.source.id) && highlight.has(l.target.id) ? 2 : 0.8)}
          linkDirectionalArrowLength={4}
          linkDirectionalArrowRelPos={1}
          cooldownTicks={120}
          onNodeClick={(n) => onSelect(n.id)}
        />
      </div>
    </section>
  )
}
