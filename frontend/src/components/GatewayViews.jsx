import { Fragment } from 'react'

const PLACEHOLDER = /(<[A-Z_]+_\d+>)/g
const IS_PLACEHOLDER = /^<[A-Z_]+_\d+>$/  // non-global: no lastIndex state between calls

// Original document with every detected span marked and labelled with its type.
// Only rendered locally in the browser that submitted the text; the original never leaves the gateway.
export function HighlightedOriginal({ text, entities }) {
  const spans = [...(entities || [])].sort((a, b) => a.start - b.start)
  const parts = []
  let pos = 0
  spans.forEach((e, i) => {
    if (e.start < pos) return
    if (e.start > pos) parts.push(<Fragment key={`t${i}`}>{text.slice(pos, e.start)}</Fragment>)
    parts.push(
      <mark key={`m${i}`} className="pii-mark" title={`${e.type} → ${e.placeholder}`}>
        {text.slice(e.start, e.end)}<span className="pii-tag">{e.type}</span>
      </mark>,
    )
    pos = e.end
  })
  if (pos < text.length) parts.push(<Fragment key="tail">{text.slice(pos)}</Fragment>)
  return <pre className="doc-view">{parts}</pre>
}

// Text with <TYPE_N> placeholders highlighted; `flag` marks placeholders that need attention.
export function PlaceholderText({ text, flag = [] }) {
  if (!text) return <pre className="doc-view muted">No text.</pre>
  return <pre className="doc-view">{text.split(PLACEHOLDER).map((part, i) =>
    IS_PLACEHOLDER.test(part)
      ? <span key={i} className={`ph-chip ${flag.includes(part) ? 'flagged' : ''}`}>{part}</span>
      : <Fragment key={i}>{part}</Fragment>)}</pre>
}

// One row per placeholder: type, how many mentions it covers, best confidence. Never the value.
export function EntityTable({ entities }) {
  const rows = new Map()
  for (const e of entities || []) {
    const r = rows.get(e.placeholder) || { placeholder: e.placeholder, type: e.type, count: 0, confidence: 0 }
    r.count += 1
    r.confidence = Math.max(r.confidence, e.confidence || 0)
    rows.set(e.placeholder, r)
  }
  if (!rows.size) return <p className="muted small">No personal data detected.</p>
  return <table className="entity-table">
    <thead><tr><th>Placeholder</th><th>Type</th><th>Mentions</th><th>Confidence</th></tr></thead>
    <tbody>{[...rows.values()].map(r => <tr key={r.placeholder}>
      <td><span className="ph-chip">{r.placeholder}</span></td>
      <td>{r.type}</td>
      <td className="num">{r.count}</td>
      <td className="num">{r.confidence.toFixed(2)}</td>
    </tr>)}</tbody>
  </table>
}
