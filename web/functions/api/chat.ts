// Cloudflare Pages Function: /api/chat

interface Env {
  CF_ACCOUNT_ID: string;
  CF_API_TOKEN: string;
}

const CF_MODEL = '@cf/qwen/qwen3-30b-a3b';
const WIKI_SUPABASE_URL = 'https://thomfxtghuszjzsljkyf.supabase.co';
const WIKI_SUPABASE_KEY = 'sb_publishable_Xgp4YibDvNI8qkghpVwK7g_Q1gs0Ke-';

async function searchWiki(query: string): Promise<string> {
  try {
    const res = await fetch(
      `${WIKI_SUPABASE_URL}/rest/v1/topics?select=id,category_id,name,content`,
      {
        headers: {
          'apikey': WIKI_SUPABASE_KEY,
          'Authorization': `Bearer ${WIKI_SUPABASE_KEY}`,
        },
      }
    );
    if (!res.ok) return '';

    const topics = await res.json() as Array<{
      id: string; category_id: string; name: string; content: string;
    }>;

    const queryLower = query.toLowerCase();
    const scored = topics.map(t => {
      const text = `${t.name} ${t.content}`.toLowerCase();
      let score = 0;
      for (const word of queryLower.split(/\s+/)) {
        if (word.length < 2) continue;
        if (text.includes(word)) score += 1;
        if (t.name.toLowerCase().includes(word)) score += 3;
      }
      return { ...t, score };
    });

    scored.sort((a, b) => b.score - a.score);
    const top = scored.filter(t => t.score > 0).slice(0, 2);
    if (top.length === 0) return '';

    return top.map((t, i) => {
      const content = extractRelevantSection(t.content, query, 800);
      return `[${i + 1}] (${t.name}) ${content}`;
    }).join('\n\n');
  } catch {
    return '';
  }
}

function extractRelevantSection(content: string, query: string, maxChars: number): string {
  const sections = content.split(/\n(?=##\s)/);
  const queryWords = query.toLowerCase().split(/\s+/).filter(w => w.length >= 2);

  const scored = sections.map(s => {
    const lower = s.toLowerCase();
    let score = 0;
    for (const w of queryWords) {
      if (lower.includes(w)) score++;
    }
    return { text: s, score };
  });

  scored.sort((a, b) => b.score - a.score);

  let result = '';
  for (const s of scored) {
    if (s.score === 0) break;
    if (result.length + s.text.length > maxChars) {
      result += s.text.slice(0, maxChars - result.length) + '...';
      break;
    }
    result += s.text + '\n';
  }

  return result || content.slice(0, maxChars);
}

export const onRequestPost: PagesFunction<Env> = async (context) => {
  const { messages: rawMessages } = await context.request.json() as { messages: Array<Record<string, unknown>> };

  const CF_ACCOUNT_ID = context.env.CF_ACCOUNT_ID;
  const CF_API_TOKEN = context.env.CF_API_TOKEN;

  const messages = rawMessages.map((m) => {
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

  const lastMessage = (messages[messages.length - 1]?.content as string) || '';
  const wikiContext = await searchWiki(lastMessage);

  const systemPrompt = `당신은 면접 준비를 도와주는 AI입니다. 아래 면접위키 문서를 근거로 정확하게 답변하세요.
- 각 주장에 [번호] 인용을 포함하세요
- 문서에 없는 내용은 "해당 내용은 면접위키에서 찾을 수 없습니다"라고 답하세요
- 한국어로 명확하고 간결하게 답변하세요
- 면접에서 어떻게 답하면 좋을지 팁도 포함하세요

## 면접위키 검색 결과
${wikiContext || '(검색 결과 없음)'}`;

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
          max_tokens: 500,
          messages: [
            { role: 'system', content: systemPrompt },
            ...messages.slice(-3),
          ],
        }),
      }
    );

    if (!response.ok) {
      return new Response(JSON.stringify({ error: `AI 서버 오류: ${response.status}` }), {
        status: 502,
        headers: { 'Content-Type': 'application/json' },
      });
    }

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
              if (data === '[DONE]') continue;
              try {
                const json = JSON.parse(data);
                if (json.response) {
                  controller.enqueue(encoder.encode(json.response));
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
        'Access-Control-Allow-Origin': '*',
      },
    });
  } catch {
    return new Response(JSON.stringify({ error: 'AI 서버에 연결할 수 없습니다.' }), {
      status: 503,
      headers: { 'Content-Type': 'application/json' },
    });
  }
};
