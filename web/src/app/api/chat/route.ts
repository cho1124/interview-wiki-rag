import { searchChunks } from '@/lib/search';

export const maxDuration = 60;

const OLLAMA_URL = process.env.OLLAMA_BASE_URL || 'http://localhost:11434';
const OLLAMA_API_KEY = process.env.OLLAMA_API_KEY || '';
const OLLAMA_MODEL = process.env.OLLAMA_MODEL || 'gemma3:4b';

export async function POST(req: Request) {
  const { messages: rawMessages } = await req.json();

  // Vercel AI SDK v6: parts → content 변환
  const messages = rawMessages.map((m: Record<string, unknown>) => {
    if (m.content) return m;
    if (Array.isArray(m.parts)) {
      const text = (m.parts as Array<{ type: string; text?: string }>)
        .filter((p) => p.type === 'text')
        .map((p) => p.text || '')
        .join('');
      return { role: m.role, content: text };
    }
    return { role: m.role, content: '' };
  });

  const lastMessage = messages[messages.length - 1]?.content || '';

  // BM25 검색
  const chunks = searchChunks(lastMessage, 5);
  let context = '';
  if (chunks.length > 0) {
    context = chunks
      .map((c: { heading?: string; content: string }, i: number) =>
        `[${i + 1}] ${c.heading ? `(${c.heading}) ` : ''}${c.content}`
      )
      .join('\n\n');
  }

  const systemPrompt = `당신은 면접 준비를 도와주는 AI 어시스턴트입니다.
아래 검색된 문서를 근거로 답변하고, 각 주장에 [번호] 인용을 포함하세요.
검색된 문서에 없는 내용은 "해당 내용은 문서에서 찾을 수 없습니다"라고 답하세요.
한국어로 답변하세요.

## 검색된 문서
${context || '(검색 결과 없음)'}`;

  const fullPrompt = `${systemPrompt}\n\n질문: ${lastMessage}\n\n답변:`;

  try {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (OLLAMA_API_KEY) headers['X-API-Key'] = OLLAMA_API_KEY;

    const ollamaRes = await fetch(`${OLLAMA_URL}/api/generate`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        model: OLLAMA_MODEL,
        prompt: fullPrompt,
        stream: true,
      }),
    });

    if (!ollamaRes.ok) {
      return new Response(
        JSON.stringify({ error: 'AI 서버에 연결할 수 없습니다.' }),
        { status: 502, headers: { 'Content-Type': 'application/json' } }
      );
    }

    // Ollama NDJSON → Vercel AI SDK Data Stream 변환
    const reader = ollamaRes.body!.getReader();
    const decoder = new TextDecoder();

    const stream = new ReadableStream({
      async start(controller) {
        const encoder = new TextEncoder();
        let buffer = '';

        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
              if (!line.trim()) continue;
              try {
                const json = JSON.parse(line);
                if (json.response) {
                  controller.enqueue(encoder.encode(`0:${JSON.stringify(json.response)}\n`));
                }
                if (json.done) {
                  controller.enqueue(encoder.encode(`d:${JSON.stringify({ finishReason: 'stop' })}\n`));
                }
              } catch {}
            }
          }
        } catch (err) {
          console.error('Stream error:', err);
        } finally {
          controller.close();
        }
      },
    });

    return new Response(stream, {
      headers: {
        'Content-Type': 'text/plain; charset=utf-8',
        'X-Vercel-AI-Data-Stream': 'v1',
      },
    });
  } catch {
    return new Response(
      JSON.stringify({ error: 'AI 서버에 연결할 수 없습니다. 잠시 후 다시 시도해주세요.' }),
      { status: 503, headers: { 'Content-Type': 'application/json' } }
    );
  }
}