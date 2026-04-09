# 면접위키 RAG 시스템

> 면접 준비를 위한 AI 질의응답 시스템 — 적대적 검증 설계 기반

## 개요

면접위키의 18개 기술 토픽(React, Spring Boot, Docker, 자료구조 등)을 기반으로 면접 질문에 답변하는 RAG(Retrieval-Augmented Generation) 시스템입니다.

[멀티 에이전트 적대적 검증](https://github.com/cho1124/multi-agent-adversarial-verification)으로 설계를 검증한 후 구현했습니다.

## 라이브 데모

**Cloudflare Pages**: (배포 완료 후 URL 추가)

## 아키텍처

```
사용자 → Next.js (Cloudflare Pages)
  → /api/chat
    → 면접위키 Supabase 실시간 검색
    → 관련 섹션 추출 (토큰 절감)
    → Cloudflare Workers AI (Llama 3.1 8B)
    → 스트리밍 응답
```

## 적대적 검증으로 발견된 결함과 수정

이 시스템은 3모델(Claude/Codex/Gemini) 적대적 검증을 통해 40건의 구조적 결함을 발견하고 수정했습니다.

### P0 (런타임 크래시) — 수정 완료
| 결함 | 수정 |
|------|------|
| 벡터 차원 SQL(384) vs Config(1536) 불일치 | 384로 통일 |
| match_chunks RPC 삭제 미복원 | setup_v3.sql에 함수 복원 |
| 라우터 JSON 파싱 예외처리 없음 | try-catch + semantic validation |
| 캐시-파이프라인 무효화 미연결 | store_chunks() 후 invalidation 호출 |

### P1 (기능 결함) — 수정 완료
| 결함 | 수정 |
|------|------|
| Citation validation 비강제 | 재생성/거절 로직 추가 |
| Sufficiency Gate max만 체크 | 복합 판정 (count + threshold 분리) |
| 캐시 키에 model/complexity 미포함 | L1/L2/L3 키 정합성 수정 |
| _run_agent 1회 왕복 제한 | while loop 전환 |
| tiktoken 미사용 (÷3 추정) | tiktoken 기반 정확 추정 |

### 비용 제로 전환
| 이전 | 현재 |
|------|------|
| OpenAI + Anthropic ($20~45/월) | Cloudflare Workers AI ($0) |
| Supabase 유료 | 면접위키 Supabase 공개 API 연동 |
| Vercel + Ollama | Cloudflare Pages 올인원 |

## 기술 스택

| 영역 | 기술 |
|------|------|
| 프론트엔드 | Next.js 16, TypeScript, Tailwind CSS |
| 호스팅 | Cloudflare Pages |
| LLM | Cloudflare Workers AI (Llama 3.1 8B) |
| 데이터 | 면접위키 Supabase (실시간) |
| 검증 | 적대적 검증 시스템 (Claude/Codex/Gemini) |

## 로컬 실행

```bash
cd web
npm install
# .env.local에 CF_ACCOUNT_ID, CF_API_TOKEN 설정
npm run dev
# http://localhost:3000
```

## 관련 리포지토리

- [multi-agent-adversarial-verification](https://github.com/cho1124/multi-agent-adversarial-verification) — 적대적 검증 시스템 설계 + 실험 기록
- [interview-wiki](https://github.com/cho1124/interview-wiki) — 면접위키 원본 사이트

## 라이선스

MIT License
