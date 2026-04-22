# Wiki Workspace — 프로젝트 문서

마크다운 기반의 개인·팀 위키(Notion-clone). 문서를 만들고, **Edit / Split / Preview** 3-모드 에디터로 편집하며,
로컬부터 시작해 점진적으로 **AI 보조 · 동기화 · 협업**으로 확장해 나가는 워크스페이스.

현재 [`frontend/src/`](../frontend/src)에 있는 React 19 + Vite + Tailwind 데모를 **기준점(source of truth)** 으로 삼아,
이를 프로덕션 수준의 제품으로 발전시키기 위한 설계 문서 모음입니다.

## 문서 목록

| 문서 | 내용 |
|---|---|
| [01_overview.md](01_overview.md) | 프로젝트 개요 · 문제 정의 · 핵심 가치 |
| [02_architecture.md](02_architecture.md) | 시스템 아키텍처 · 레이어 구성 · 데이터 흐름 |
| [03_components.md](03_components.md) | 컴포넌트별 상세 설계 (Sidebar / Editor / Hooks / 확장 계획) |
| [04_api.md](04_api.md) | API 계약 (Phase 2+ 동기화 · AI 프록시) |
| [05_data_schema.md](05_data_schema.md) | `Document` 스키마 · localStorage · 서버 스키마 |
| [06_tech_stack.md](06_tech_stack.md) | 기술 스택 선택과 근거 |
| [07_roadmap.md](07_roadmap.md) | 단계별 로드맵 (Phase 0 → 4) |
| [08_tradeoffs.md](08_tradeoffs.md) | 주요 트레이드오프와 의사결정 기록 |

## 빠르게 읽고 싶다면

1. [01_overview.md](01_overview.md) — 무엇을 만드는지
2. [02_architecture.md](02_architecture.md) — 어떻게 만드는지
3. [03_components.md](03_components.md) — 데모 코드가 어떤 구조인지
4. [07_roadmap.md](07_roadmap.md) — 어떤 순서로 확장할지
