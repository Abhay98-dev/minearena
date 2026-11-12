import { useEffect, useState } from 'react'
import { Activity, ArrowDownToLine, ArrowRight, ClipboardCheck, FileText, LockKeyhole, RefreshCw, ShieldCheck } from 'lucide-react'
import { getAudit, getHealth, processDocument } from './services/api'
import './App.css'

const sample = 'My name is Rahul Sharma. My Aadhaar number is 1234-5678-9012 and my PAN is ABCDE1234F.'

function App() {
  const [tab, setTab] = useState('process')
  const [text, setText] = useState(sample)
  const [task, setTask] = useState('summarize')
  const [provider, setProvider] = useState('mock')
  const [result, setResult] = useState(null)
  const [records, setRecords] = useState([])
  const [health, setHealth] = useState('checking')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function refreshAudit() {
    try { setRecords(await getAudit()) } catch { setRecords([]) }
  }

  useEffect(() => {
    getHealth().then(() => setHealth('online')).catch(() => setHealth('offline'))
    refreshAudit()
  }, [])

  async function submit(event) {
    event.preventDefault()
    setBusy(true); setError(''); setResult(null)
    try {
      const response = await processDocument({ text, task, provider })
      setResult(response)
      await refreshAudit()
    } catch (err) {
      setError(err.message || 'The request could not be completed.')
    } finally { setBusy(false) }
  }

  return <main className="app-shell">
    <header className="topbar">
      <a className="brand" href="#home" onClick={() => setTab('process')}><span className="brand-mark"><ShieldCheck size={20} /></span><span>mine<span className="brand-accent">arena</span><small>PRIVACY GATEWAY</small></span></a>
      <nav aria-label="Main navigation"><button className={tab === 'process' ? 'active' : ''} onClick={() => setTab('process')}>Workspace</button><button className={tab === 'audit' ? 'active' : ''} onClick={() => { setTab('audit'); refreshAudit() }}>Audit trail</button></nav>
      <div className="connection"><span className={`status-dot ${health}`} /> API {health}</div>
    </header>

    <section className="page-heading"><div><div className="eyebrow"><LockKeyhole size={14} /> YOUR PRIVATE AI WORKSPACE</div><h1>{tab === 'process' ? 'Process documents, privately.' : 'A clear record of every request.'}</h1><p>{tab === 'process' ? 'Sensitive details are masked locally before your text reaches an AI provider.' : 'Review sanitized request metadata without exposing original identity values.'}</p></div><div className="privacy-badge"><ShieldCheck size={17} /> Local-first protection</div></section>

    {tab === 'process' ? <section className="workspace">
      <form className="panel input-panel" onSubmit={submit}>
        <div className="panel-title"><div><span className="step">01</span><div><h2>Your document</h2><p>Paste synthetic or approved text to process</p></div></div><span className="secure-label"><LockKeyhole size={13} /> Protected in transit</span></div>
        <label className="field-label" htmlFor="document">DOCUMENT TEXT</label>
        <textarea id="document" value={text} onChange={e => setText(e.target.value)} placeholder="Paste document text here…" required maxLength={20000} />
        <div className="editor-meta"><span>{text.length.toLocaleString()} / 20,000 characters</span><button type="button" className="text-button" onClick={() => setText(sample)}>Load safe sample</button></div>
        <div className="settings-row"><label>Task<select value={task} onChange={e => setTask(e.target.value)}><option value="summarize">Summarize</option><option value="extract">Extract key details</option></select></label><label>Provider<select value={provider} onChange={e => setProvider(e.target.value)}><option value="mock">Mock (offline demo)</option><option value="gemini">Gemini</option><option value="ollama">Ollama</option></select></label></div>
        <button className="primary-button" type="submit" disabled={busy || !text.trim()}>{busy ? <><RefreshCw className="spin" size={17} /> Processing securely…</> : <>Mask &amp; process <ArrowRight size={17} /></>}</button>
        <div className="privacy-note"><LockKeyhole size={14} /><span>Your original document stays within this gateway. Only sanitized text is sent to the selected provider.</span></div>
      </form>

      <section className="panel results-panel"><div className="panel-title"><div><span className="step">02</span><div><h2>Gateway results</h2><p>Masking, provider response, and restoration</p></div></div>{result && <span className="success-label"><span className="status-dot online" /> Complete</span>}</div>
        {error && <div className="error-box" role="alert">{error}</div>}
        {!result && !error ? <div className="empty-state"><div className="empty-icon"><FileText size={24} /></div><h3>Ready when you are</h3><p>Submit a document to see the sanitized payload and final response.</p><div className="flow"><span>Mask locally</span><ArrowRight size={14}/><span>Check payload</span><ArrowRight size={14}/><span>Restore labels</span></div></div> : null}
        {result && <div className="result-content"><div className="result-stat"><span><ClipboardCheck size={15}/> Privacy check</span><strong className={result.leakage_detected ? 'danger' : 'good'}>{result.leakage_detected ? 'Leak detected' : 'Passed'}</strong></div>
          <ResultBlock title="Sanitized text" value={result.sanitized_text} />
          <ResultBlock title="Exact outbound payload" value={result.outbound_payload} />
          <ResultBlock title="Final response" value={result.final_response} prominent />
          <div className="result-footer"><span>{result.provider} · {result.model}</span><span>{Math.round(result.processing_time_ms || 0)} ms</span></div>
          <button className="text-button copy-button" onClick={() => navigator.clipboard?.writeText(result.final_response || '')}><ArrowDownToLine size={14}/> Copy final response</button>
        </div>}
      </section>
    </section> : <section className="panel audit-panel"><div className="panel-title"><div><span className="step">03</span><div><h2>Recent requests</h2><p>Sanitized audit records from the backend</p></div></div><button className="icon-button" onClick={refreshAudit} aria-label="Refresh audit"><RefreshCw size={16}/></button></div>{records.length ? <div className="audit-table-wrap"><table><thead><tr><th>Request</th><th>Status</th><th>Provider</th><th>Entities</th><th>Duration</th></tr></thead><tbody>{records.map((r, i) => <tr key={r.request_id || i}><td className="mono">{r.request_id}</td><td><span className="table-status">{r.status || 'complete'}</span></td><td>{r.provider || '—'}</td><td>{Array.isArray(r.entity_types) ? r.entity_types.join(', ') : '—'}</td><td>{r.processing_time_ms ? `${Math.round(r.processing_time_ms)} ms` : '—'}</td></tr>)}</tbody></table></div> : <div className="empty-state audit-empty"><div className="empty-icon"><Activity size={24}/></div><h3>No audit records yet</h3><p>Process a document and its sanitized metadata will appear here.</p></div>}</section>}
    <footer><span>MineArena Privacy Gateway</span><span><LockKeyhole size={12}/> Sensitive mappings remain local and request-scoped</span></footer>
  </main>
}

function ResultBlock({ title, value, prominent }) {
  return <div className={`result-block ${prominent ? 'prominent' : ''}`}><div className="result-block-title">{title}</div><pre>{value || 'No response returned.'}</pre></div>
}

export default App
