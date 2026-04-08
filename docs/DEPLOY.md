# 배포 가이드: Oracle Cloud + Ollama + Vercel

PC 꺼져 있어도 24시간 작동하는 무료 RAG 시스템 구축.

## 아키텍처

```
사용자 → Vercel (Next.js 프론트) → Oracle Cloud VM (Ollama gemma3:4b)
                                 → Supabase (BM25 검색 데이터)
```

- **Vercel**: 프론트엔드 + API route (무료)
- **Oracle Cloud**: Ollama LLM 상시 운영 (영구 무료)
- **Supabase**: 벡터 DB + 검색 (무료 티어)

---

## 1단계: Oracle Cloud 계정 생성

1. https://cloud.oracle.com 접속
2. **Start for Free** 클릭
3. 계정 생성 (신용카드 필요하지만 **무료 티어 내에서 과금 없음**)
4. 리전 선택: **Japan East (Tokyo)** 또는 **South Korea Central (Seoul)** 권장

## 2단계: VM 인스턴스 생성

1. Oracle Cloud Console → **Compute → Instances → Create Instance**
2. 설정:
   - **이름**: `ollama-server`
   - **Image**: Ubuntu 22.04 (Canonical)
   - **Shape**: VM.Standard.A1.Flex (Ampere ARM)
     - OCPU: **4**
     - Memory: **24 GB**
   - **Boot volume**: 100 GB (최대 200 GB 무료)
   - **네트워킹**: Public subnet, Assign public IP
3. **SSH 키**: 새로 생성하거나 기존 키 업로드
4. **Create** 클릭

> Always Free 범위: ARM A1 최대 4 OCPU + 24GB RAM + 200GB 스토리지

## 3단계: 보안 규칙 설정

Oracle Cloud Console → **Networking → Virtual Cloud Networks → VCN → Security Lists**

**Ingress Rule 추가:**

| Source CIDR | Protocol | Port |
|-------------|----------|------|
| 0.0.0.0/0 | TCP | 11434 |

## 4단계: Ollama 설치

SSH로 인스턴스 접속:
```bash
ssh -i <private_key> ubuntu@<public_ip>
```

Ollama 설치:
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

모델 다운로드:
```bash
ollama pull gemma3:4b
```

테스트:
```bash
curl http://localhost:11434/api/generate -d '{"model":"gemma3:4b","prompt":"hello","stream":false}'
```

## 5단계: Ollama 외부 접근 허용 + 자동 시작

systemd 서비스 수정:
```bash
sudo systemctl edit ollama.service
```

아래 내용 추가:
```ini
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"
Environment="OLLAMA_ORIGINS=*"
```

재시작:
```bash
sudo systemctl daemon-reload
sudo systemctl restart ollama
```

외부 접근 확인:
```bash
curl http://<public_ip>:11434/api/tags
```

## 6단계: nginx 리버스 프록시 + API 키 보호 (선택)

Ollama를 외부에 바로 노출하면 누구나 사용 가능. 간단한 API 키 보호:

```bash
sudo apt install -y nginx
```

`/etc/nginx/sites-available/ollama`:
```nginx
server {
    listen 443 ssl;
    server_name <public_ip>;

    # 자체 서명 인증서 (테스트용)
    ssl_certificate /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/nginx/ssl/key.pem;

    location / {
        # API 키 확인
        if ($http_x_api_key != "your-secret-api-key-here") {
            return 403;
        }

        proxy_pass http://127.0.0.1:11434;
        proxy_set_header Host $host;
        proxy_read_timeout 120s;
    }
}
```

자체 서명 인증서 생성:
```bash
sudo mkdir -p /etc/nginx/ssl
sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /etc/nginx/ssl/key.pem \
  -out /etc/nginx/ssl/cert.pem \
  -subj '/CN=ollama-server'
```

활성화:
```bash
sudo ln -s /etc/nginx/sites-available/ollama /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl restart nginx
```

> nginx 없이 11434 포트 직접 사용도 가능 (보안은 약하지만 간단).

## 7단계: Next.js route.ts 수정 (Gemini → Ollama)

`web/src/app/api/chat/route.ts` 수정:

```typescript
import { searchChunks } from '@/lib/search';

export const maxDuration = 60;

const OLLAMA_URL = process.env.OLLAMA_BASE_URL || 'http://localhost:11434';
const OLLAMA_API_KEY = process.env.OLLAMA_API_KEY || '';
const OLLAMA_MODEL = process.env.OLLAMA_MODEL || 'gemma3:4b';

export async function POST(req: Request) {
  const { messages: rawMessages } = await req.json();

  // parts → content 변환
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
    // Ollama API 호출 (스트리밍)
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
      const errText = await ollamaRes.text();
      return new Response(
        JSON.stringify({ error: `LLM 서버 오류: ${ollamaRes.status}` }),
        { status: 502, headers: { 'Content-Type': 'application/json' } }
      );
    }

    // Ollama NDJSON → SSE 텍스트 스트림 변환
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
                  // Vercel AI SDK 호환 형태로 전송
                  controller.enqueue(encoder.encode(`0:${JSON.stringify(json.response)}\n`));
                }
                if (json.done) {
                  controller.enqueue(encoder.encode(`d:{"finishReason":"stop"}\n`));
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
  } catch (err) {
    return new Response(
      JSON.stringify({ error: 'AI 서버에 연결할 수 없습니다. 잠시 후 다시 시도해주세요.' }),
      { status: 503, headers: { 'Content-Type': 'application/json' } }
    );
  }
}
```

## 8단계: Vercel 환경변수 설정

Vercel Dashboard → Settings → Environment Variables:

| Key | Value |
|-----|-------|
| `OLLAMA_BASE_URL` | `http://<oracle_public_ip>:11434` |
| `OLLAMA_API_KEY` | `your-secret-api-key-here` (nginx 사용 시) |
| `OLLAMA_MODEL` | `gemma3:4b` |

> nginx 안 쓰면 OLLAMA_API_KEY는 빈 값으로.

## 9단계: 배포 확인

```bash
# Oracle Cloud에서 Ollama 상태 확인
curl http://<public_ip>:11434/api/tags

# Vercel에서 채팅 테스트
# 웹 브라우저에서 Vercel URL 접속 후 질문 입력
```

## 비용 요약

| 항목 | 비용 |
|------|------|
| Oracle Cloud VM | **영구 무료** (Always Free) |
| Vercel | **무료** (Hobby) |
| Supabase | **무료** (Free Tier) |
| Ollama + gemma3 | **무료** (오픈소스) |
| **합계** | **$0/월** |

## 문제 해결

### Ollama 응답이 느릴 때
```bash
# 모델을 더 작은 걸로 교체
ollama pull gemma3:1b
# OLLAMA_MODEL 환경변수도 변경
```

### VM이 재부팅됐을 때
systemd 서비스로 등록했으므로 자동 시작됨. 확인:
```bash
sudo systemctl status ollama
```

### Vercel에서 타임아웃
`maxDuration = 60` 설정 확인. Hobby 플랜은 최대 60초.