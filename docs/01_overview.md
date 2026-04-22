# 01. 프로젝트 개요

## 문제 정의

개인·팀의 지식(회의록, 리포트, 리서치, 스니펫)은 대개 다음 중 하나로 흩어진다:

- **워드프로세서**: 문서 단위는 좋지만 링크·검색·태깅이 약하다.
- **Notion·Confluence 류**: 강력하지만 무겁고, 벤더 락인·비용·속도 이슈가 있다.
- **로컬 마크다운 에디터**: 가볍지만 공유·협업·AI 보조가 빈약하다.

"가벼운 마크다운 기반 + 위키의 구조화 + 선택적 클라우드 동기화 + AI 보조"를 한 곳에서 제공하는 도구가 필요하다.

## 핵심 아이디어

> **로컬에서 즉시 쓰이되(Phase 1: localStorage)**, 필요할 때 원격 동기화와 협업으로 점진 확장되는 마크다운 위키.
> 편집은 **Edit / Split / Preview** 3-모드, 표준 CommonMark + GFM, AI 보조는 Gemini를 1차 백엔드로.

## 핵심 가치

- **즉시 동작(zero-setup)**: 첫 실행 시 샘플 문서가 뜨고, 타이핑은 localStorage로 저장되어 로그인·세팅 없이 쓸 수 있다.
- **마크다운 표준 준수**: 자체 포맷이 아닌 CommonMark + `remark-gfm`. 어디든 내보내기·가져오기 가능.
- **속도 우선 UX**: Vite 기반 SPA, 입력 debounce 300ms, 상태 단순화. 타이핑이 끊기지 않는 에디터.
- **점진적 복잡도**: 로컬 → AI 보조 → 원격 동기화 → 협업 순으로 기능을 쌓는다. 초기에 백엔드 없이도 완결된 제품.
- **AI 네이티브**: `@google/genai`를 통한 요약·제목 제안·문서 재구성 등을 UI 1급 시민으로.

## 사용 시나리오 (예시)

1. 사용자가 앱을 처음 연다 → "Welcome to Wiki Workspace" 문서가 자동 생성되어 샘플 마크다운이 표시된다.
2. 사이드바의 `+ New Document`로 새 문서를 만든다.
3. 에디터에서 제목과 본문을 작성 (타이핑은 300ms debounce로 로컬에 저장).
4. 상단 토글로 **Edit / Split / Preview** 를 전환해 렌더 결과를 확인한다.
5. (Phase 2) 오른쪽 AI 패널에서 "이 문서 요약해줘 / 제목 제안해줘"를 요청.
6. (Phase 3) 로그인 후 클라우드 동기화 토글을 켜면 다른 기기에서도 같은 문서가 보인다.
7. (Phase 4) 특정 문서를 팀원에게 공유·동시 편집.

## 현재 레포와의 관계

| 현재 자산 | 프로젝트에서의 역할 |
|---|---|
| [`frontend/src/App.tsx`](../frontend/src/App.tsx) | 앱 진입점 · 문서 목록·활성 문서 상태 관리 |
| [`frontend/src/components/Sidebar.tsx`](../frontend/src/components/Sidebar.tsx) | 문서 목록·생성·삭제·제목 검색 UI |
| [`frontend/src/components/Editor.tsx`](../frontend/src/components/Editor.tsx) | 3-모드(Edit/Split/Preview) 마크다운 에디터 |
| [`frontend/src/hooks/useLocalStorage.ts`](../frontend/src/hooks/useLocalStorage.ts) | localStorage 퍼시스턴스 훅 |
| [`frontend/src/types.ts`](../frontend/src/types.ts) | `Document` 도메인 타입 (id/title/content/timestamps) |
| [`frontend/index.html`](../frontend/index.html), [`frontend/vite.config.ts`](../frontend/vite.config.ts), [`frontend/package.json`](../frontend/package.json) | Vite + React 19 + Tailwind 4 빌드 설정 |

즉, 현재 레포는 **프론트엔드 MVP 데모**이며, 본 문서는 이를 **완성형 위키 제품**으로 확장하는 설계를 담는다.
구체적인 확장 대상은 [03_components.md](03_components.md), [07_roadmap.md](07_roadmap.md) 참고.
