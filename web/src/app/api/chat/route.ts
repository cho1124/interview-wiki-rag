import { google } from '@ai-sdk/google';
import { streamText } from 'ai';

// BM25-like simple search over bundled data
import { searchChunks } from '@/lib/search';

export const maxDuration = 30;

export async function POST(req: Request) {
  const { messages } = await req.json();
  const lastMessage = messages[messages.length - 1]?.content || '';

  // 검색
  const chunks = searchChunks(lastMessage, 5);

  // 컨텍스트 구성
  let context = '';
  if (chunks.length > 0) {
    context = chunks
      .map((c, i) => `[${i + 1}] ${c.heading ? `(${c.heading}) ` : ''}${c.content}`)
      .join('\n\n');
  }

  const systemPrompt = `당신은 면접 준비를 도와주는 AI 어시스턴트입니다.
아래 검색된 문서를 근거로 답변하고, 각 주장에 [번호] 인용을 포함하세요.
검색된 문서에 없는 내용은 "해당 내용은 문서에서 찾을 수 없습니다"라고 답하세요.

## 검색된 문서
${context || '(검색 결과 없음)'}`;

  const result = streamText({
    model: google('gemini-2.0-flash'),
    system: systemPrompt,
    messages,
  });

  return result.toTextStreamResponse();
}
