import { useMemo, useState } from "react";
import Markdown from "react-markdown";
import { sendChat } from "./api";
import "./App.css";

const SUGGESTIONS = [
  "Show me properties in Dubai.",
  "Find 3 bedroom properties.",
  "What properties are under AED 2 million?",
  "Which properties are from DarGlobal?",
  "Show me villas in Dubai.",
  "Which properties have swimming pools?",
];

const WELCOME = {
  role: "assistant",
  text: "Ask about DarGlobal or Wasalt listings. I search stored records first, then check the live sites only if needed.",
  sources: [],
};

function connectionErrorCopy(err) {
  const timedOut = err?.code === "ECONNABORTED" || /timeout/i.test(err?.message || "");
  if (timedOut) {
    return {
      bubble: "This is taking a little longer than usual. Please try again in a moment.",
      status: "Still starting up — please send your question again.",
    };
  }
  return {
    bubble: "I'm having trouble connecting right now. Please wait a few seconds and try again.",
    status: "Temporarily unavailable. If you just opened the chat, it may need a moment to wake up.",
  };
}

function metaLine(source) {
  const parts = [
    source.property_type,
    source.bedrooms && source.bedrooms !== "Not specified" ? `${source.bedrooms} beds` : null,
    source.bathrooms ? `${source.bathrooms} baths` : null,
    source.area_sqm ? `${source.area_sqm} sqm` : null,
  ].filter(Boolean);
  return parts.join(" · ");
}

export default function App() {
  const [messages, setMessages] = useState([WELCOME]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const canSend = useMemo(() => input.trim().length > 0 && !loading, [input, loading]);
  const showEmpty = messages.length === 1 && !loading;

  async function ask(question) {
    const trimmed = question.trim();
    if (!trimmed || loading) return;
    setError("");
    setInput("");
    setMessages((current) => [...current, { role: "user", text: trimmed, sources: [] }]);
    setLoading(true);
    try {
      const response = await sendChat(trimmed);
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          text: response.answer,
          sources: (response.sources || []).slice(0, 3),
        },
      ]);
    } catch (err) {
      const copy = connectionErrorCopy(err);
      setError(copy.status);
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          text: copy.bubble,
          sources: [],
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  function onSubmit(event) {
    event.preventDefault();
    ask(input);
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <div className="logo">AI</div>
          <div>
            <h1>AI assistant</h1>
            <p>Real estate AI assistant</p>
          </div>
        </div>
        <div className="badge">DarGlobal · Wasalt</div>
      </header>

      <section className="thread">
        {showEmpty && (
          <div className="empty">
            <h2>Find the next place to live.</h2>
            <p>Ask about city, bedrooms, budget, or a project name. Answers stay grounded in retrieved listings.</p>
            <div className="suggestions">
              {SUGGESTIONS.map((item) => (
                <button key={item} type="button" onClick={() => ask(item)}>
                  {item}
                </button>
              ))}
            </div>
          </div>
        )}

        {!showEmpty &&
          messages.slice(1).map((message, index) => (
            <div key={`${message.role}-${index}`} className={`row ${message.role}`}>
              {message.role === "assistant" && <div className="avatar">AI</div>}
              <div className={`bubble ${message.role}`}>
                {message.role === "assistant" ? (
                  <div className="markdown">
                    <Markdown
                      components={{
                        a: ({ href, children }) => (
                          <a href={href} target="_blank" rel="noreferrer">
                            {children}
                          </a>
                        ),
                      }}
                    >
                      {message.text}
                    </Markdown>
                  </div>
                ) : (
                  <div>{message.text}</div>
                )}
                {message.sources?.length > 0 && (
                  <div className="cards">
                    {message.sources.map((source) => (
                      <article className="card" key={source.id}>
                        <div className="card-kicker">{source.source}</div>
                        <strong>{source.title}</strong>
                        <div className="card-location">{source.location || "Location not specified"}</div>
                        {metaLine(source) && <div className="card-meta">{metaLine(source)}</div>}
                        <div className="card-price">{source.price}</div>
                        {source.status && <div className="card-status">{source.status}</div>}
                        {source.amenities?.length > 0 && (
                          <div className="card-amenities">{source.amenities.slice(0, 4).join(" · ")}</div>
                        )}
                        <a href={source.url} target="_blank" rel="noreferrer">
                          View listing →
                        </a>
                      </article>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}

        {loading && (
          <div className="row assistant">
            <div className="avatar">AI</div>
            <div className="bubble assistant typing">…</div>
          </div>
        )}
      </section>

      <div className="composer-wrap">
        <form className="composer" onSubmit={onSubmit}>
          <input
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="Ask about a city, budget, or project…"
          />
          <button className="send" type="submit" disabled={!canSend}>
            Send
          </button>
        </form>
        {error && <div className="status">{error}</div>}
      </div>
    </div>
  );
}
