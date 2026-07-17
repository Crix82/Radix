import { Fragment, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import type { ChatFinal, Citation } from "../api/chat";
import { streamChat } from "../api/chat";
import { PageHead } from "../components/Layout";
import { t } from "../i18n";

const c = t.pages.chat;

interface AssistantMsg {
  role: "assistant";
  text: string;
  citations: Citation[];
  refusal: boolean;
  streaming: boolean;
  error?: boolean;
}
interface UserMsg {
  role: "user";
  text: string;
}
type Msg = UserMsg | AssistantMsg;

const CITE_RE = /\[(\d{1,2})\]/g;

// Render answer text with [n] markers turned into clickable amber citation chips.
function AnswerBody({ msg, onCite }: { msg: AssistantMsg; onCite: (cit: Citation) => void }) {
  const byN = new Map(msg.citations.map((cit) => [cit.n, cit]));
  const parts: React.ReactNode[] = [];
  let last = 0;
  let m: RegExpExecArray | null;
  CITE_RE.lastIndex = 0;
  while ((m = CITE_RE.exec(msg.text)) !== null) {
    const n = Number(m[1]);
    const cit = byN.get(n);
    if (m.index > last) parts.push(msg.text.slice(last, m.index));
    if (cit) {
      parts.push(
        <button key={`${m.index}-${n}`} type="button" className="cite" onClick={() => onCite(cit)}>
          <span className="balloon">{n}</span>
          {c.pageAbbr} {cit.page}
        </button>,
      );
    } else {
      parts.push(m[0]);
    }
    last = m.index + m[0].length;
  }
  if (last < msg.text.length) parts.push(msg.text.slice(last));

  return (
    <p className="whitespace-pre-wrap text-[13.5px] leading-relaxed">
      {parts.map((p, i) => (
        <Fragment key={i}>{p}</Fragment>
      ))}
      {msg.streaming && <span className="ml-[2px] animate-pulse text-ink3">▋</span>}
    </p>
  );
}

function SourcesPanel({ citations, onCite }: { citations: Citation[]; onCite: (c: Citation) => void }) {
  if (citations.length === 0) return null;
  return (
    <>
      <div className="src-label">{c.sources}</div>
      <div className="flex flex-col gap-[6px]">
        {citations.map((cit) => (
          <button key={cit.n} type="button" className="src-item" onClick={() => onCite(cit)}>
            <span className="balloon">{cit.n}</span>
            <span className="text-[12.5px] font-semibold">{cit.title ?? `#${cit.document_id}`}</span>
            <span className="font-mono text-[10.5px] text-ink2">
              {cit.lang ? `${cit.lang.toUpperCase()} · ` : ""}
              {c.pageAbbr} {cit.page}
            </span>
          </button>
        ))}
      </div>
    </>
  );
}

export function ChatPage() {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const navigate = useNavigate();
  const threadEndRef = useRef<HTMLDivElement>(null);

  const openCitation = (cit: Citation) => {
    navigate(`/viewer/${cit.document_id}/${cit.page}`, {
      state: { bboxes: cit.bboxes, from: "chat", title: cit.title, lang: cit.lang },
    });
  };

  const send = () => {
    const question = input.trim();
    if (!question || streaming) return;
    const history = messages.map((m) =>
      m.role === "user" ? { role: "user" as const, content: m.text } : { role: "assistant" as const, content: m.text },
    );
    const outgoing = [...history, { role: "user" as const, content: question }];

    setMessages((prev) => [
      ...prev,
      { role: "user", text: question },
      { role: "assistant", text: "", citations: [], refusal: false, streaming: true },
    ]);
    setInput("");
    setStreaming(true);

    const patchLast = (patch: Partial<AssistantMsg>) =>
      setMessages((prev) => {
        const next = [...prev];
        const i = next.length - 1;
        next[i] = { ...(next[i] as AssistantMsg), ...patch };
        return next;
      });

    void streamChat(
      outgoing,
      {},
      {
        onToken: (text) =>
          setMessages((prev) => {
            const next = [...prev];
            const i = next.length - 1;
            const cur = next[i] as AssistantMsg;
            next[i] = { ...cur, text: cur.text + text };
            return next;
          }),
        onFinal: (final: ChatFinal) => {
          patchLast({
            text: final.answer_md,
            citations: final.citations,
            refusal: final.refusal,
            streaming: false,
          });
          setStreaming(false);
        },
        onError: () => {
          patchLast({ streaming: false, error: true, text: c.error });
          setStreaming(false);
        },
      },
    ).finally(() => threadEndRef.current?.scrollIntoView({ behavior: "smooth" }));
  };

  return (
    <div className="flex h-full flex-col">
      <PageHead title={c.title} subtitle={c.subtitle} />

      <div className="flex flex-1 flex-col gap-[14px] overflow-y-auto pb-[18px]">
        {messages.length === 0 && <div className="text-[13px] text-ink3">{c.empty}</div>}
        {messages.map((m, i) =>
          m.role === "user" ? (
            <div key={i} className="msg-user">
              {m.text}
            </div>
          ) : m.refusal ? (
            <div key={i} className="card msg-ai border-l-[3px] border-ink3">
              <div className="mb-[3px] text-[13px] font-bold">{c.refusalTitle}</div>
              <p className="text-[13px] text-ink2">{c.refusalAddSource}</p>
            </div>
          ) : (
            <div key={i} className={`card msg-ai ${m.error ? "text-err" : ""}`}>
              <AnswerBody msg={m} onCite={openCitation} />
              {!m.streaming && <SourcesPanel citations={m.citations} onCite={openCitation} />}
            </div>
          ),
        )}
        {streaming && <div className="self-start px-1 py-[6px] text-[12px] text-ink3">{c.searching}</div>}
        <div ref={threadEndRef} />
      </div>

      <div className="composer">
        <div className="search-box">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && send()}
            placeholder={c.inputPlaceholder}
            aria-label={c.inputLabel}
            disabled={streaming}
          />
        </div>
        <button type="button" className="send" onClick={send} disabled={streaming} aria-label="Invia">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden="true" className="h-4 w-4">
            <path d="M22 2 11 13" />
            <path d="M22 2 15 22l-4-9-9-4z" />
          </svg>
        </button>
      </div>
    </div>
  );
}
