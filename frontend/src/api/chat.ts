export interface Citation {
  n: number;
  chunk_id: number;
  document_id: number;
  title: string | null;
  lang: string | null;
  page: number;
  bboxes: Record<string, number[][]> | null;
}

export interface ChatFinal {
  answer_md: string;
  refusal: boolean;
  citations: Citation[];
}

export interface ChatMessageIn {
  role: "user" | "assistant";
  content: string;
}

export interface ChatFilters {
  lang?: string;
  doc_type?: string;
  collection_id?: number;
}

interface StreamHandlers {
  onToken: (text: string) => void;
  onFinal: (final: ChatFinal) => void;
  onError: (err: Error) => void;
}

// POST /chat streams Server-Sent Events; parse them off the fetch body reader.
export async function streamChat(
  messages: ChatMessageIn[],
  filters: ChatFilters,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  let resp: Response;
  try {
    resp = await fetch("/api/v1/chat", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages, filters }),
      signal,
    });
  } catch (e) {
    handlers.onError(e instanceof Error ? e : new Error("network"));
    return;
  }
  if (!resp.ok || !resp.body) {
    handlers.onError(new Error(`chat failed: ${resp.status}`));
    return;
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const blocks = buffer.split("\n\n");
      buffer = blocks.pop() ?? "";
      for (const block of blocks) dispatch(block, handlers);
    }
    if (buffer.trim()) dispatch(buffer, handlers);
  } catch (e) {
    handlers.onError(e instanceof Error ? e : new Error("stream"));
  }
}

function dispatch(block: string, handlers: StreamHandlers): void {
  let event = "";
  let data = "";
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data = line.slice(5).trim();
  }
  if (!event || !data) return;
  try {
    const parsed = JSON.parse(data);
    if (event === "token") handlers.onToken(parsed.text as string);
    else if (event === "final") handlers.onFinal(parsed as ChatFinal);
  } catch {
    // ignore malformed event
  }
}
