import { useEffect, useState } from 'react'
import { AlertTriangle, CheckCircle2, RefreshCw } from 'lucide-react'
import { getEvaluation, getMetrics } from '../services/api'

const TYPES = ['PERSON', 'AADHAAR', 'PAN', 'GSTIN', 'VOTER_ID', 'PASSPORT', 'ADDRESS']
const MODE_LABEL = {
  echo: 'Keeps every placeholder', reorder: 'Reorders placeholders', paraphrase: 'Paraphrases around them',
  drop: 'Drops placeholders', unknown: 'Invents unknown placeholders',
}
const pct = v => (v == null ? '—' : `${(v * 100).toFixed(1)}%`)
const f3 = v => (v == null ? '—' : v.toFixed(3))

function Status({ ok, okText, badText }) {
  return ok
    ? <span className="status good"><CheckCircle2 size={14} /> {okText}</span>
    : <span className="status danger"><AlertTriangle size={14} /> {badText}</span>
}

function Tile({ label, value, sub, children }) {
  return <div className="stat-tile"><div className="stat-label">{label}</div><div className="stat-value">{value}</div>
    {sub && <div className="stat-sub">{sub}</div>}{children}</div>
}

function DetectionTable({ full, rules }) {
  return <div className="table-wrap"><table className="metric-table">
    <thead><tr><th>Type</th><th className="num">Precision</th><th className="num">Recall</th><th className="num">F1</th>
      <th className="num">Strict F1</th>{rules && <th className="num">Recall, rules only</th>}<th className="num">TP / FP / FN</th></tr></thead>
    <tbody>{[...TYPES, 'overall'].map(t => {
      const r = t === 'overall' ? full.relaxed.overall : full.relaxed.per_type[t]
      const s = t === 'overall' ? full.strict.overall : full.strict.per_type[t]
      const base = rules && (t === 'overall' ? rules.relaxed.overall : rules.relaxed.per_type[t])
      return <tr key={t} className={t === 'overall' ? 'total' : ''}>
        <td>{t === 'overall' ? 'Overall' : t}</td><td className="num">{f3(r.precision)}</td><td className="num">{f3(r.recall)}</td>
        <td className="num">{f3(r.f1)}</td><td className="num">{f3(s.f1)}</td>
        {rules && <td className="num">{f3(base.recall)}</td>}
        <td className="num">{r.tp} / {r.fp} / {r.fn}</td></tr>
    })}</tbody></table></div>
}

export default function EvaluationReport() {
  const [report, setReport] = useState(null)
  const [metrics, setMetrics] = useState(null)
  const [error, setError] = useState('')
  const [view, setView] = useState('heldout')

  async function load() {
    setError('')
    try { setReport(await getEvaluation()) } catch (e) { setError(e.message) }
    try { setMetrics(await getMetrics()) } catch { setMetrics(null) }
  }
  useEffect(() => { load() }, [])

  if (error) return <section className="panel eval-panel"><div className="error-box" role="alert">{error}
    <div className="small">Run <code>python dataset/generate_dataset.py</code> and <code>python evaluation/run_eval.py</code>.</div></div></section>
  if (!report) return <section className="panel eval-panel"><p className="muted">Loading evaluation report…</p></section>

  const held = report.heldout
  const det = view === 'heldout' && held ? held.detection.full : report.detection.full
  const leak = report.leakage
  const lat = report.detection.full.latency_overhead_ms
  const rein = report.reinsertion
  const wrong = Object.values(rein).reduce((n, m) => n + (m.wrong_person || 0), 0)
  const reinAcc = ['echo', 'reorder', 'paraphrase', 'drop'].map(m => rein[m]?.accuracy).filter(v => v != null)

  return <section className="eval">
    <div className="panel eval-panel">
      <div className="panel-title"><div><span className="step">✓</span><div><h2>Evaluation on synthetic data</h2>
        <p>{report.dataset.documents} labelled documents ({report.dataset.entities} entities) · seed {report.dataset.seed}
          {held && <> · plus {held.dataset.documents} held-out documents never used for tuning</>} · generated {report.generated_at}</p></div></div>
        <button className="icon-button" onClick={load} aria-label="Reload report"><RefreshCw size={16} /></button></div>

      <div className="tile-row">
        <Tile label="Raw PII in outbound payloads" value={leak.full_value_count + (held ? held.leakage.full_value_count : 0)}
          sub={`${leak.checked_payloads + (held ? held.leakage.checked_payloads : 0)} audited payloads · target 0`}>
          <Status ok={leak.full_value_count + (held?.leakage.full_value_count || 0) === 0} okText="Zero leakage" badText="Leak found" /></Tile>
        <Tile label="Detection F1, held-out" value={held ? f3(held.detection.full.relaxed.overall.f1) : '—'}
          sub={`recall ${held ? f3(held.detection.full.relaxed.overall.recall) : '—'} · tuned set ${f3(report.detection.full.relaxed.overall.f1)}`} />
        <Tile label="Reinsertion accuracy" value={pct(Math.min(...reinAcc))} sub="worst of keep / reorder / paraphrase / drop">
          <Status ok={wrong === 0} okText="0 wrong-person restorations" badText={`${wrong} wrong-person`} /></Tile>
        <Tile label="Added latency per request" value={`${lat.median} ms`} sub={`median · mean ${lat.mean} · p95 ${lat.p95} ms (n=${lat.n})`} />
      </div>
    </div>

    <div className="panel eval-panel">
      <div className="panel-title"><div><div><h2>Detection precision and recall by type</h2>
        <p>Relaxed match = same type and ≥ 50% span overlap (headline). Strict = exact span.</p></div></div>
        {held && <div className="seg" role="tablist">
          <button role="tab" aria-selected={view === 'heldout'} className={view === 'heldout' ? 'on' : ''} onClick={() => setView('heldout')}>Held-out ({held.dataset.documents})</button>
          <button role="tab" aria-selected={view === 'main'} className={view === 'main' ? 'on' : ''} onClick={() => setView('main')}>Main set ({report.dataset.documents})</button>
        </div>}</div>
      <DetectionTable full={det} rules={view === 'main' ? report.detection.rules_only : null} />
      <p className="note">{view === 'heldout'
        ? 'Held-out documents use phrasings the detector was never tuned on: the honest estimate.'
        : 'The main set was used to find and fix detector errors, so these scores are optimistic. "Rules only" shows the same pipeline without the local NER model.'}</p>
    </div>

    <div className="panel eval-panel">
      <div className="panel-title"><div><div><h2>Placeholder reinsertion when the LLM misbehaves</h2>
        <p>Mock LLM run over every document with PII. Dropped placeholders are reported, never guessed.</p></div></div></div>
      <div className="table-wrap"><table className="metric-table">
        <thead><tr><th>LLM behaviour</th><th className="num">Placeholders in reply</th><th className="num">Restored correctly</th>
          <th className="num">Accuracy</th><th className="num">Wrong person</th><th className="num">Dropped (reported)</th><th className="num">Unknown left as-is</th></tr></thead>
        <tbody>{Object.entries(rein).map(([mode, a]) => <tr key={mode}>
          <td>{MODE_LABEL[mode] || mode}</td><td className="num">{a.expected}</td><td className="num">{a.correct}</td>
          <td className="num">{pct(a.accuracy)}</td><td className="num">{a.wrong_person}</td>
          <td className="num">{a.dropped_reported}</td><td className="num">{a.unknown_left_unrestored} / {a.unknown_seen}</td></tr>)}</tbody>
      </table></div>
    </div>

    {metrics && <div className="panel eval-panel">
      <div className="panel-title"><div><div><h2>Live gateway totals</h2><p>From this server's audit log (GET /metrics)</p></div></div></div>
      <div className="tile-row">
        <Tile label="Requests" value={metrics.n} sub={`${metrics.ok} ok · ${metrics.blocked} blocked · ${metrics.err} errors`} />
        <Tile label="Leaks found by guard" value={metrics.leaks} sub="blocked before sending" />
        <Tile label="Mean gateway overhead" value={`${metrics.avg_overhead} ms`} sub={`mean LLM time ${metrics.avg_llm} ms`} />
      </div>
    </div>}
  </section>
}
