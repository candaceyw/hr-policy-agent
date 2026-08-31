import { useState } from 'react';

const demoQuestions = [
  // The two graded demo workflows first.
  'Is Marcus Silva (E-1002) allowed to work remotely from another state for six weeks? What approvals and data-security rules apply?',
  'Can I take three days of PTO next week? My employee id is E-1002.',
  // Supporting demos: plain policy Q&A, expense compliance, multi-doc, out-of-scope, clarify.
  'How much PTO do employees accrue per month?',
  'Can I expense a company laptop and a home office chair?',
  'I want to work from Ireland for six weeks. What approvals do I need and what applies to my laptop and data access?',
  'What time does the pizza place close?',
  'How much PTO do I have left?',
];

export default function App() {
  const [message, setMessage] = useState(demoQuestions[0]);
  const [response, setResponse] = useState(null);
  const [loading, setLoading] = useState(false);

  function handleNewConversation() {
    setMessage('');
    setResponse(null);
    setLoading(false);
  }

  async function sendMessage(confirmValue) {
    setLoading(true);

    const body = { message };
    if (typeof confirmValue === 'boolean') {
      body.confirm = confirmValue;
    }

    try {
      const res = await fetch('http://localhost:8000/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      const data = await res.json();
      setResponse(data);
    } catch (error) {
      setResponse({
        answer: 'The backend is not running yet. Start the FastAPI server on port 8000 to test the UI flow.',
        citations: [],
        trace: [{ step: 0, name: 'connection_error', result_summary: String(error) }],
      });
    } finally {
      setLoading(false);
    }
  }

  function handleSubmit(event) {
    event.preventDefault();
    sendMessage();
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-mark">H</div>
        <div>
          <div className="eyebrow">Policy support</div>
          <h1>HR Policy Agent</h1>
        </div>
      </header>

      <main className="workspace">
        <aside className="panel sidebar-panel">
          <div className="hero-header">
            <div className="status-pill">
              <span className="dot" />
              Active
            </div>
            <button className="ghost-button" type="button" onClick={handleNewConversation}>New conversation</button>
          </div>

          <div className="onboarding-card">
            <div className="mini-label">First-time here?</div>
            <h2>Ask a policy question</h2>
            <p>Get grounded answers backed by company policy and supporting citations.</p>
          </div>

          <div className="quick-actions">
            <div className="section-label">Quick prompts</div>
            <div className="preset-list">
              {demoQuestions.map((item) => (
                <button key={item} type="button" onClick={() => setMessage(item)} className="preset-button">
                  {item}
                </button>
              ))}
            </div>
          </div>

          <form onSubmit={handleSubmit} className="composer">
            <textarea
              value={message}
              onChange={(event) => setMessage(event.target.value)}
              rows={4}
              placeholder="Ask a question about PTO, benefits, travel, or policy compliance..."
            />
            <div className="composer-actions">
              <button type="submit" className="primary-button" disabled={loading}>
                {loading ? 'Searching policies...' : 'Ask the agent'}
              </button>
            </div>
          </form>
        </aside>

        <section className="panel result-panel">
          {response ? (
            <>
              <div className="answer-header">
                <div>
                  <div className="mini-label">Latest response</div>
                  <h2>Policy answer</h2>
                </div>
                <div className="pill-row">
                  {response.escalation ? (
                    <div className="escalation-pill">Recommend HR follow-up</div>
                  ) : null}
                  <div className="confidence-pill">Grounded answer</div>
                </div>
              </div>

              <div className="answer-box">
                <p>{response.answer}</p>
              </div>

              {response.pending_action ? (
                <div className="pending-action">
                  <div className="section-label">Confirmation required</div>
                  <p>
                    {response.pending_action.description}. This is a mock action &mdash; nothing has run yet.
                  </p>
                  <div className="pending-action-buttons">
                    <button
                      type="button"
                      className="primary-button"
                      disabled={loading}
                      onClick={() => sendMessage(true)}
                    >
                      Confirm
                    </button>
                    <button
                      type="button"
                      className="ghost-button"
                      disabled={loading}
                      onClick={() => sendMessage(false)}
                    >
                      Deny
                    </button>
                  </div>
                </div>
              ) : null}

              {response.llm_error ? (
                <div className="llm-warning">
                  <strong>LLM fallback:</strong> {response.llm_error}
                </div>
              ) : null}

              <div className="meta-row">
                <div className="citation-box">
                  <div className="section-label">Citations</div>
                  {response.citations?.length ? (
                    <ul>
                      {response.citations.map((citation, index) => (
                        <li key={`${citation.doc_id}-${index}`}>
                          <div className="citation-title">{citation.title}</div>
                          <div className="citation-section">{citation.section}</div>
                          <div className="citation-snippet">{citation.snippet}</div>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p>No citations returned.</p>
                  )}
                </div>

                <div className="trace-box">
                  <div className="section-label">Trace</div>
                  <ul>
                    {response.trace?.map((item) => (
                      <li key={`${item.step}-${item.name}`}>
                        <div className="trace-name">{item.name}</div>
                        <small>{item.result_summary}</small>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </>
          ) : (
            <div className="placeholder-panel">
              <div className="placeholder-mark">AI</div>
              <h2>Grounded answers for people operations</h2>
              <p>Ask a question to see the policy answer, supporting citations, and the workflow trace.</p>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
