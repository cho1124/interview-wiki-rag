# 면접위키 RAG 시스템

> 면접 준비를 위한 AI 질의응답 시스템 — [적대적 검증](https://github.com/cho1124/multi-agent-adversarial-verification) 설계 기반

## 라이브 데모

https://interview-wiki-rag.pages.dev

## 개요

면접위키의 18개 기술 토픽(React, Spring Boot, Docker, 자료구조 등)을 기반으로 면접 질문에 답변하는 RAG 시스템입니다.

3개 AI 모델(Claude/Codex/Gemini)이 서로 토론하는 [멀티 에이전트 적대적 검증](https://github.com/cho1124/multi-agent-adversarial-verification)으로 설계를 검증한 후 구현했습니다.

## 아키텍처

```
사용자 → Next.js (Cloudflare Pages)
  → /api/chat
    → 면접위키 Supabase에서 실시간 검색
    → 관련 섹션 추출 (토큰 절감)
    → Cloudflare Workers AI (Llama 3.1 8B)
    → 스트리밍 응답
```

## 기술 스택

| 영역 | 기술 | 비용 |
|------|------|------|
| 프론트엔드 | Next.js 16, TypeScript, Tailwind CSS | 무료 |
| 호스팅 | Cloudflare Pages | 무료 |
| AI 모델 | Cloudflare Workers AI (Llama 3.1 8B) | 무료 |
| 데이터 | 면접위키 Supabase (실시간 조회) | 무료 |
| **월 비용** | | **$0** |

## 4단계 검증 기록

이 시스템은 설계부터 배포까지 4단계 검증을 거쳤습니다.

### 1차: 설계 검증 (21라운드, 47건)

RAG 시스템의 3개 소주제(청크 분할, 검색-생성, 캐싱)를 적대적 검증으로 설계.
- 파이프라인 **3번 재설계**, 청크 ID **7번 변경**
- 상세: [적대적 검증 레포 — 1차 실험](https://github.com/cho1124/multi-agent-adversarial-verification/tree/master/docs/experiments/2026-04-06-RAG-%EC%8B%9C%EC%8A%A4%ED%85%9C-%EA%B2%80%EC%A6%9D)

### 2차: 구현 검증 (7라운드, 40건)

실제 코드를 3모델(Claude/Codex/Gemini)로 검증. Codex가 행 번호까지 인용하며 결함 발견.

| 결함 (심각) | 수정 |
|------------|------|
| 벡터 차원 SQL(384) vs 설정(1536) 불일치 | 384로 통일 |
| match_chunks 함수 삭제 후 미복원 | SQL에 함수 복원 |
| 라우터 JSON 파싱 예외처리 없음 | try-catch + 의미 검증 추가 |
| 캐시-파이프라인 무효화 미연결 | 저장 후 무효화 호출 |

| 결함 (기능) | 수정 |
|------------|------|
| 인용 검증이 계산만 하고 강제 안 함 | 재생성/거절 로직 추가 |
| 충분성 게이트가 최고점만 확인 | 복합 판정 (건수 + 임계값 분리) |
| 캐시 키에 모델/복잡도 미포함 | 3계층 캐시 키 정합성 수정 |
| 도구 호출이 1회만 가능 | 반복 호출 루프 전환 |

- 상세: [적대적 검증 레포 — 2차 실험](https://github.com/cho1124/multi-agent-adversarial-verification/tree/master/docs/experiments/2026-04-08-RAG-%EA%B5%AC%ED%98%84-%EA%B2%80%EC%A6%9D)

### 3차: 배포 검증 (2라운드, 3건)

최종 배포 아키텍처(Cloudflare Pages + Workers AI)를 검증.

| 미해소 결함 | 심각도 |
|------------|--------|
| 스트리밍 중 에러 시 사용자에게 전달 불가 | 높음 |
| 검색 0건인데 인용 강제 → 환각 인용 가능 | 높음 |

### 4차: 런타임 자동 테스트 (9개 TC)

적대적 검증 결과에서 자동 생성된 테스트 케이스를 실제 배포 URL에서 실행.

| 테스트 | 결과 |
|--------|------|
| 페이지 로드 | 통과 |
| API 엔드포인트 | 통과 |
| 정상 질문 스트리밍 (1993자) | 통과 |
| 검색 0건 환각 인용 | 통과 (환각 없음) |
| 빈 메시지 | 통과 (크래시 없음) |
| 긴 메시지 | 통과 (크래시 없음) |
| 응답 시간 (0.035초) | 통과 |
| **인용 [1] 포함 여부** | **경고 — Llama 8B가 인용 규칙 미준수** |
| 한국어 응답 | 통과 |

- 상세: [적대적 검증 레포 — 3차/4차 실험](https://github.com/cho1124/multi-agent-adversarial-verification/tree/master/docs/experiments/2026-04-09-RAG-%EB%B0%B0%ED%8F%AC-%EA%B2%80%EC%A6%9D)

### 비용 변화

```
$20~45/월 (OpenAI + Anthropic)
  → $15/월 (Ollama 로컬)
    → $0/월 (Cloudflare Workers AI + Pages + Supabase 무료)
```

## 로컬 실행

```bash
cd web
npm install
npm run dev
# http://localhost:3000
```

Cloudflare Workers AI를 사용하려면 `.env.local`에 설정:
```
CF_ACCOUNT_ID=계정ID
CF_API_TOKEN=API토큰
```

## 배포

Cloudflare Pages에 자동 배포됩니다. 상세 가이드: [docs/DEPLOY.md](docs/DEPLOY.md)

## 관련 리포지토리

| 리포지토리 | 설명 |
|-----------|------|
| [multi-agent-adversarial-verification](https://github.com/cho1124/multi-agent-adversarial-verification) | 적대적 검증 시스템 — 설계 이론 + 실험 기록 |
| [interview-wiki](https://github.com/cho1124/interview-wiki) | 면접위키 원본 사이트 |

## 라이선스

MIT License