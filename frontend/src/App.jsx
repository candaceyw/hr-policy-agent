import { useEffect, useMemo, useRef, useState } from 'react';
import { marked } from 'marked';
import DOMPurify from 'dompurify';

marked.setOptions({ breaks: true });

const DEMO_EMPLOYEES = [
  { id: '', label: 'Not set' },
  { id: 'E-1001', label: 'Alicia Chen (E-1001)' },
  { id: 'E-1002', label: 'Marcus Silva (E-1002)' },
  { id: 'E-1003', label: 'Priya Nair (E-1003)' },
  { id: 'E-1004', label: 'Jonas Brooks (E-1004)' },
  { id: 'E-1007', label: 'Sophie Martin (E-1007)' },
];

const EXAMPLE_PROMPTS = [
  'Am I allowed to work remotely from another state for six weeks? What approvals do I need?',
  'Can I take three days of PTO next week?',
  'How much PTO do employees accrue per month?',
  'Can I expense a company laptop and a home-office chair?',
];

const PROGRESS_STAGES = [
  'Reading the request',
  'Searching policy documents',
  'Checking records',
  'Writing the answer',
];

const TRACE_LABELS = {
  classify: 'route',
  retrieval: 'search',
  tool_call: 'tool',
  compose: 'answer',
  guardrail: 'guardrail',
  clarify: 'clarify',
  confirmation: 'confirm',
  degradation: 'fallback',
};

async function postChat(body) {
  const res = await fetch('/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

/* ---------------------------------------------------------------- answer body */

function AnswerProse({ text, citations }) {
  const html = useMemo(() => {
    const idToNum = new Map();
    citations.forEach((c, i) => {
      if (!idToNum.has(c.doc_id)) idToNum.set(c.doc_id, i + 1);
    });
    const withSentinels = text.replace(/\[([a-z0-9-]+)\]/gi, (full, id) => {
      const num = idToNum.get(id);
      return num ? `@@CITE:${num}:${id}@@` : '';
    });
    const raw = marked.parse(withSentinels);
    const clean = DOMPurify.sanitize(raw, { ADD_ATTR: ['target'] });
    return clean.replace(
      /@@CITE:(\d+):([a-z0-9-]+)@@/gi,
      '<sup class="cite-ref" title="$2">$1</sup>',
    );
  }, [text, citations]);

  return <div className="answer-prose markdown-body" dangerouslySetInnerHTML={{ __html: html }} />;
}

function Sources({ citations }) {
  if (!citations.length) return null;
  return (
    <details className="disclosure">
      <summary>Sources · {citations.length}</summary>
      <ol className="source-list">
        {citations.map((c, i) => (
          <li key={`${c.doc_id}-${i}`}>
            <div>
              <span className="source-title">{c.title}</span>
              {c.section ? <span className="source-section"> — {c.section}</span> : null}
              {c.snippet ? <p className="source-snippet">{c.snippet}</p> : null}
            </div>
          </li>
        ))}
      </ol>
    </details>
  );
}

function TraceDisclosure({ trace }) {
  if (!trace?.length) return null;
  const tools = trace.filter((s) => s.type === 'tool_call').length;
  const summary = tools > 0 ? `Steps · ${tools} tool ${tools === 1 ? 'call' : 'calls'}` : 'Steps';
  return (
    <details className="disclosure">
      <summary>{summary}</summary>
      <ul className="trace-list">
        {trace.map((step, i) => (
          <li key={i}>
            <span className="trace-tag">{TRACE_LABELS[step.type] || step.type}</span>
            <span className="trace-body">
              <span className="trace-name">{step.name}</span>
              {step.args_summary ? (
                <code className="trace-args" title={step.args_summary}>
                  {step.args_summary}
                </code>
              ) : null}
              {step.result_summary ? (
                <span className="trace-result">{step.result_summary}</span>
              ) : null}
            </span>
          </li>
        ))}
      </ul>
    </details>
  );
}

/* ------------------------------------------------------------------- one turn */

function Thinking({ stage, elapsed }) {
  return (
    <div className="thinking">
      <span className="progress-bar" aria-hidden="true" />
      <span>{stage}</span>
      {elapsed > 2 ? <span className="elapsed">{elapsed}s</span> : null}
    </div>
  );
}

function AssistantTurn({ turn, loading, onConfirm }) {
  const { intent, answer, citations = [], trace = [], escalation, pending_action, llm_error } = turn;

  if (turn.error) return <p className="notice warn">{answer}</p>;

  if (pending_action) {
    return (
      <div className="pending">
        <p className="answer-label warn">Confirm this action</p>
        <p>{pending_action.description}. Nothing has run yet.</p>
        <code>{pending_action.args_summary}</code>
        <div className="pending-actions">
          <button className="btn-primary" disabled={loading} onClick={() => onConfirm(true)}>
            Confirm
          </button>
          <button className="btn-plain" disabled={loading} onClick={() => onConfirm(false)}>
            Cancel
          </button>
        </div>
      </div>
    );
  }

  const label =
    intent === 'out_of_scope'
      ? 'Outside HR policy'
      : intent === 'clarify' || intent === 'ambiguous'
        ? 'One detail first'
        : null;

  return (
    <div>
      {label ? <p className="answer-label">{label}</p> : null}
      <AnswerProse text={answer} citations={citations} />
      {escalation ? (
        <p className="notice warn">Confirm this with HR before acting — the policy coverage here is thin.</p>
      ) : null}
      {llm_error ? (
        <p className="notice">Written from a template; the language model was unavailable.</p>
      ) : null}
      <div className="disclosure-row">
        <Sources citations={citations} />
        <TraceDisclosure trace={trace} />
      </div>
    </div>
  );
}

function Turn({ turn, isLatest, loading, elapsed, stage, onConfirm }) {
  return (
    <section className={`turn ${isLatest ? 'turn-latest' : 'turn-past'}`}>
      <p className="question">{turn.query}</p>
      {turn.pending ? (
        <Thinking stage={stage} elapsed={elapsed} />
      ) : (
        <AssistantTurn turn={turn} loading={loading} onConfirm={onConfirm} />
      )}
    </section>
  );
}

/* ------------------------------------------------------------------- shell */

export default function App() {
  const [turns, setTurns] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const [employeeId, setEmployeeId] = useState('E-1002');
  const [health, setHealth] = useState(null);
  const [elapsed, setElapsed] = useState(0);
  const [stageIdx, setStageIdx] = useState(0);
  const threadRef = useRef(null);

  useEffect(() => {
    fetch('/health')
      .then((r) => r.json())
      .then((h) => {
        const vector = h?.retrieval?.active_method === 'vector';
        const mcp = h?.mcp?.connected;
        if (mcp && vector) {
          setHealth({ level: 'ok' });
        } else {
          setHealth({
            level: 'degraded',
            label: mcp ? 'Keyword search only' : 'Limited — retrieval only',
            detail: `mcp ${mcp ? 'up' : 'down'} · retrieval ${h?.retrieval?.active_method}`,
          });
        }
      })
      .catch(() => setHealth({ level: 'degraded', label: 'Backend offline', detail: 'GET /health failed' }));
  }, []);

  useEffect(() => {
    if (!loading) return undefined;
    setElapsed(0);
    setStageIdx(0);
    const started = Date.now();
    const t = setInterval(() => {
      const secs = Math.floor((Date.now() - started) / 1000);
      setElapsed(secs);
      setStageIdx(Math.min(PROGRESS_STAGES.length - 1, Math.floor(secs / 5)));
    }, 250);
    return () => clearInterval(t);
  }, [loading]);

  useEffect(() => {
    threadRef.current?.scrollTo({ top: threadRef.current.scrollHeight, behavior: 'smooth' });
  }, [turns, loading]);

  async function send(text) {
    const query = (text ?? input).trim();
    if (!query || loading) return;
    setInput('');
    setLoading(true);
    setTurns((prev) => [...prev, { query, pending: true }]);
    try {
      const data = await postChat({
        message: query,
        session_id: sessionId,
        employee_id: employeeId || undefined,
      });
      setSessionId(data.session_id);
      setTurns((prev) => [...prev.slice(0, -1), { query, ...data }]);
    } catch (err) {
      setTurns((prev) => [
        ...prev.slice(0, -1),
        { query, error: true, answer: `Could not reach the backend (${err.message}). Is the API running on :8000?` },
      ]);
    } finally {
      setLoading(false);
    }
  }

  async function resolvePending(confirmValue) {
    const target = turns[turns.length - 1];
    if (!target) return;
    setLoading(true);
    setTurns((prev) => [...prev.slice(0, -1), { query: target.query, pending: true }]);
    try {
      const data = await postChat({
        message: target.query,
        session_id: sessionId,
        employee_id: employeeId || undefined,
        confirm: confirmValue,
      });
      setSessionId(data.session_id);
      setTurns((prev) => [...prev.slice(0, -1), { query: target.query, ...data }]);
    } catch (err) {
      setTurns((prev) => [
        ...prev.slice(0, -1),
        { query: target.query, error: true, answer: `Could not reach the backend (${err.message}).` },
      ]);
    } finally {
      setLoading(false);
    }
  }

  function newConversation() {
    setTurns([]);
    setSessionId(null);
    setInput('');
  }

  function onKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  const empty = turns.length === 0;

  return (
    <div className="app">
      <header className="app-header">
        <span className="wordmark">HR Policy</span>
        <div className="header-right">
          <label className="acting-as">
            <span>Acting as</span>
            <select value={employeeId} onChange={(e) => setEmployeeId(e.target.value)}>
              {DEMO_EMPLOYEES.map((e) => (
                <option key={e.id || 'none'} value={e.id}>
                  {e.label}
                </option>
              ))}
            </select>
          </label>
          {health && health.level !== 'ok' ? (
            <span className="health" title={health.detail}>
              {health.label}
            </span>
          ) : null}
        </div>
      </header>

      <main className="thread" ref={threadRef}>
        {empty ? (
          <div className="welcome">
            <h1>Ask about company HR policy</h1>
            <p>
              Answers come from Northwind Robotics policy documents and cite the section they
              draw on. Covers time off, benefits, remote work, expenses, travel, leave, pay, and
              conduct — not IT, payroll disputes, or anything outside HR.
            </p>
            <div className="suggestions">
              <span className="suggestions-label">Try</span>
              <ul>
                {EXAMPLE_PROMPTS.map((p) => (
                  <li key={p}>
                    <button className="suggestion" onClick={() => setInput(p)}>
                      {p}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        ) : (
          turns.map((turn, i) => (
            <Turn
              key={i}
              turn={turn}
              isLatest={i === turns.length - 1}
              loading={loading}
              elapsed={elapsed}
              stage={PROGRESS_STAGES[stageIdx]}
              onConfirm={resolvePending}
            />
          ))
        )}
      </main>

      <footer className="composer">
        <div className="composer-box">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            rows={1}
            placeholder={empty ? 'Ask a question about HR policy' : 'Ask a follow-up'}
          />
          <button className="btn-primary" disabled={loading || !input.trim()} onClick={() => send()}>
            {loading ? 'Working' : 'Ask'}
          </button>
        </div>
        <div className="composer-meta">
          {empty ? (
            <span>Return to send · Shift-Return for a new line</span>
          ) : (
            <button onClick={newConversation}>New question</button>
          )}
        </div>
      </footer>
    </div>
  );
}
