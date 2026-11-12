import { useEffect, useState } from 'react'
import {
  Activity, AlertTriangle, ArrowRight, CheckCircle2, FileText, LockKeyhole, Pencil, RefreshCw, Send, ShieldCheck,
  ShieldX,
} from 'lucide-react'
import { getAudit, getEngines, getHealth, processDocument } from './services/api'
import { EntityTable, HighlightedOriginal, PlaceholderText } from './components/GatewayViews'
import EvaluationReport from './pages/EvaluationReport'
import { SAMPLES } from './samples'
import './App.css'

const ENGINE_LABEL = { gliner: 'Local NER (GLiNER)', presidio: 'Presidio India IDs' }

function App() {
  const [tab, setTab] = useState('process')
  const [text, setText] = useState(SAMPLES[0].text)
  const [task, setTask] = useState(SAMPLES[0].task)
  const [provider, setProvider] = useState('mock')
  const [result, setResult] = useState(null)
  const [submitted, setSubmitted] = useState('')
  const [editing, setEditing] = useState(true)
  const [records, setRecords] = useState([])
  const [health, setHealth] = useState('checking')
  const [engines, setEngines] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  async function refreshAudit() {
    try { setRecords(await getAudit()) } catch { setRecords([]) }
  }

  useEffect(() => {
    getHealth().then(() => setHealth('online')).catch(() => setHealth('offline'))
    getEngines().then(setEngines).catch(() => setEngines(null))
    refreshAudit()
  }, [])

  function loadSample(id) {
    const s = SAMPLES.find(x => x.id === id)
    if (!s) return
    setText(s.text); setTask(s.task); setResult(null); setError(null); setEditing(true)
  }

  async function submit(event) {
    event.preventDefault()
    setBusy(true); setError(null); setResult(null)
    try {
      const response = await processDocument({ text, task, provider })
      setResult(response); setSubmitted(text); setEditing(false)
      await refreshAudit()
    } catch (err) {
      setError(err)
    } finally { setBusy(false) }
  }

  const blocked = error?.code === 'OUTBOUND_PII_LEAKAGE_BLOCKED'

  return <main className="app-shell">
    <header className="topbar">
      <a className="brand" href="#home" onClick={() => setTab('process')}><span className="brand-mark"><ShieldCheck size={20} /></span><span>mine<span className="brand-accent">arena</span><small>PRIVACY GATEWAY</small></span></a>
      <nav aria-label="Main navigation">
        <button className={tab === 'process' ? 'active' : ''} onClick={() => setTab('process')}>Workspace</button>
        <button className={tab === 'eval' ? 'active' : ''} onClick={() => setTab('eval')}>Evaluation</button>
        <button className={tab === 'audit' ? 'active' : ''} onClick={() => { setTab('audit'); refreshAudit() }}>Audit trail</button>
      </nav>
      <div className="connection"><span className={`status-dot ${health}`} /> API {health}</div>
    </header>

    <section className="page-heading">
      <div><div className="eyebrow"><LockKeyhole size={14} /> DPDP-READY PRIVACY GATEWAY</div>
        <h1>{tab === 'process' ? 'Process documents, privately.' : tab === 'eval' ? 'Measured, not claimed.' : 'A clear record of every request.'}</h1>
        <p>{tab === 'process' ? 'Personal data is detected and masked on this server. Only the middle column ever reaches the AI provider.'
          : tab === 'eval' ? 'Leakage, detection accuracy, reinsertion and latency on seeded synthetic Indian documents.'
            : 'Sanitized request metadata: entity types, exact outbound payload, model. Never original values.'}</p></div>
      {engines && <div className="engine-chips" aria-label="Detection engines">
        {Object.entries(ENGINE_LABEL).map(([k, label]) => {
          const st = engines[k]?.status
          const ok = st === 'loaded'
          return <span key={k} className={`engine-chip ${ok ? 'ok' : 'warn'}`} title={engines[k]?.error || st}>
            {ok ? <CheckCircle2 size={13} /> : <AlertTriangle size={13} />} {label}: {st}</span>
        })}
      </div>}
    </section>

    {tab === 'process' && <>
      <form className="panel control-bar" onSubmit={submit}>
        <label>Sample document
          <select defaultValue="" onChange={e => loadSample(e.target.value)}>
            <option value="" disabled>Choose a synthetic sample…</option>
            {SAMPLES.map(s => <option key={s.id} value={s.id}>{s.label}</option>)}
          </select></label>
        <label>Task<select value={task} onChange={e => setTask(e.target.value)}>
          <option value="summarize">Summarize</option><option value="extract">Extract key details</option></select></label>
        <label>LLM provider<select value={provider} onChange={e => setProvider(e.target.value)}>
          <option value="mock">Mock (offline demo)</option><option value="gemini">Gemini (external)</option><option value="ollama">Ollama (local)</option></select></label>
        <button className="primary-button" type="submit" disabled={busy || !text.trim()}>
          {busy ? <><RefreshCw className="spin" size={17} /> Processing…</> : <>Mask &amp; send <ArrowRight size={17} /></>}</button>
      </form>

      <section className="workspace three">
        <article className="panel column">
          <div className="col-head"><span className="step">A</span><div><h2>Original input</h2><p>Stays on this server</p></div>
            {result && !editing && <button className="text-button" onClick={() => setEditing(true)}><Pencil size={13} /> Edit</button>}</div>
          {editing || !result
            ? <><textarea aria-label="Document text" value={text} onChange={e => setText(e.target.value)} maxLength={20000} required />
              <div className="editor-meta"><span>{text.length.toLocaleString()} / 20,000</span><span>Use synthetic data only</span></div></>
            : <><HighlightedOriginal text={submitted} entities={result.entities} />
              <p className="muted small">{result.entities.length} detected mention(s), marked with their type.</p></>}
        </article>

        <article className={`panel column ${blocked ? 'blocked' : ''}`}>
          <div className="col-head"><span className="step">B</span><div><h2>Outbound sanitized payload</h2><p>Exactly what the LLM receives</p></div>
            {result && <span className="status good"><ShieldCheck size={14} /> Guard passed · {result.leakage_count} leaks</span>}</div>
          {blocked && <div className="block-banner" role="alert"><ShieldX size={18} /><div><strong>Blocked, nothing was sent.</strong>
            <div>The outbound check found {error.details?.leakage_count ?? 'some'} raw value(s)
              ({(error.details?.finding_types || []).join(', ') || 'personal data'}). The LLM was never called.</div></div></div>}
          {error && !blocked && <div className="error-box" role="alert">{error.message}</div>}
          {!result && !error && <Empty icon={<Send size={22} />} title="Nothing sent yet" text="Submit a document to see the exact text that leaves the organisation." />}
          {result && <>
            <PlaceholderText text={result.outbound_payload} />
            <h3 className="sub-head">Detected entities</h3>
            <EntityTable entities={result.entities} />
          </>}
        </article>

        <article className="panel column">
          <div className="col-head"><span className="step">C</span><div><h2>Final response</h2><p>Original values restored locally</p></div></div>
          {!result && <Empty icon={<FileText size={22} />} title="No response yet" text="The LLM reply appears here after local reinsertion." />}
          {result && <>
            <pre className="doc-view final">{result.final_response}</pre>
            {result.missing_placeholders.length > 0 && <p className="note"><AlertTriangle size={13} /> The LLM dropped {result.missing_placeholders.join(', ')}. Reported, not guessed.</p>}
            {result.unknown_placeholders.length > 0 && <p className="note"><AlertTriangle size={13} /> Unknown placeholder(s) {result.unknown_placeholders.join(', ')} left unchanged.</p>}
            <details className="raw"><summary>LLM reply before reinsertion</summary>
              <PlaceholderText text={result.llm_response} flag={[...result.missing_placeholders, ...result.unknown_placeholders]} /></details>
            <dl className="facts">
              <div><dt>Model</dt><dd>{result.provider} · {result.model}{result.fallback_used ? ' (fallback)' : ''}</dd></div>
              <div><dt>LLM time</dt><dd>{result.llm_time_ms} ms</dd></div>
              <div><dt>Gateway overhead</dt><dd>{result.gateway_overhead_ms} ms</dd></div>
              <div><dt>Request</dt><dd className="mono">{result.request_id}</dd></div>
            </dl>
          </>}
        </article>
      </section>
    </>}

    {tab === 'eval' && <EvaluationReport />}

    {tab === 'audit' && <section className="panel audit-panel">
      <div className="panel-title"><div><span className="step">✓</span><div><h2>Recent requests</h2><p>Sanitized audit records from the backend</p></div></div>
        <button className="icon-button" onClick={refreshAudit} aria-label="Refresh audit"><RefreshCw size={16} /></button></div>
      {records.length ? <div className="audit-table-wrap"><table><thead><tr><th>Request</th><th>Status</th><th>Model</th><th>Entity types</th><th>Leaks</th><th>Duration</th></tr></thead>
        <tbody>{records.map((r, i) => <tr key={r.request_id || i}><td className="mono">{r.request_id}</td>
          <td><span className={`table-status ${r.status === 'success' ? '' : 'bad'}`}>{r.status}</span></td>
          <td>{r.provider || '—'}{r.model ? ` · ${r.model}` : ''}</td>
          <td>{Array.isArray(r.entity_types) ? r.entity_types.join(', ') : '—'}</td><td>{r.leakage_count ?? 0}</td>
          <td>{r.processing_time_ms ? `${Math.round(r.processing_time_ms)} ms` : '—'}</td></tr>)}</tbody></table></div>
        : <Empty icon={<Activity size={22} />} title="No audit records yet" text="Process a document and its sanitized metadata will appear here." />}
    </section>}

    <footer><span>MineArena Privacy Gateway · synthetic data only</span><span><LockKeyhole size={12} /> Mappings stay local and are destroyed after each request</span></footer>
  </main>
}

function Empty({ icon, title, text }) {
  return <div className="empty-state"><div className="empty-icon">{icon}</div><h3>{title}</h3><p>{text}</p></div>
}

export default App
