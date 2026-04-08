import { searchChunks } from '@/lib/search';

export const runtime = 'edge';
export const maxDuration = 30;

const CF_ACCOUNT_ID = process.env.CF_ACCOUNT_ID || '';
const CF_API_TOKEN = process.env.CF_API_TOKEN || '';
const CF_MODEL = '@cf/meta/llama-3.1-8b-instruct';

export async function POST(req: Request) {
  const { messages: rawMessages } = await req.json();

  // AI SDK v6: parts → content 변환
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
  const chunks = searchChunks(lastMessage, 3); // 3개로 줄여서 토큰 절감
  let context = '';
  if (chunks.length > 0) {
    context = chunks
      .map((c, i) => `[${i + 1}] ${c.heading ? `(${c.heading}) ` : ''}${c.content.slice(0, 300)}`) // 300자로 압축
      .join('\n\n');
  }

  const systemPrompt = `면접 준비 AI. 아래 문서를 근거로 답변하고 [번호] 인용을 포함하라. 문서에 없으면 "해당 내용은 문서에서 찾을 수 없습니다"라고 답하라. 한국어로 간결하게 답변하라.

## 문서
${context || '(검색 결과 없음)'}`;

  try {
    const response = await fetch(
      `https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/ai/run/${CF_MODEL}`,
      {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${CF_API_TOKEN}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          stream: true,
          max_tokens: 350,
          messages: [
            { role: 'system', content: systemPrompt },
            ...messages.slice(-3), // 최근 3개 메시지만 (토큰 절감)
          ],
        }),
      }
    );

    if (!response.ok) {
      const errorText = await response.text();
      return new Response(
        JSON.stringify({ error: `AI 서버 오류: ${response.status}` }),
        { status: 502, headers: { 'Content-Type': 'application/json' } }
      );
    }

    // Cloudflare AI SSE → Vercel AI SDK Data Stream 변환
    const reader = response.body!.getReader();
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
              if (!line.startsWith('data: ')) continue;
              const data = line.slice(6).trim();
              if (data === '[DONE]') {
                controller.enqueue(encoder.encode(`d:${JSON.stringify({ finishReason: 'stop' })}\n`));
                continue;
              }
              try {
                const json = JSON.parse(data);
                if (json.response) {
                  controller.enqueue(encoder.encode(`0:${JSON.stringify(json.response)}\n`));
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
      JSON.stringify({ error: 'AI 서버에 연결할 수 없습니다.' }),
      { status: 503, headers: { 'Content-Type': 'application/json' } }
    );
  }
}
