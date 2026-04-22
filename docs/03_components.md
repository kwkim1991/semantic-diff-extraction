# 03. 컴포넌트 상세 설계

현재 데모에 존재하는 컴포넌트는 **실체가 있는 것**, Phase 2+ 계획은 **확장 계획**으로 구분해 적는다.

---

## 1. `App` — 최상위 컨테이너

위치: [`frontend/src/App.tsx`](../frontend/src/App.tsx)

### 책임
- 문서 컬렉션 보관 (`documents: Document[]`) — `useLocalStorage("wiki-docs", [])`
- 활성 문서 ID 관리 (`activeDocumentId: string | null`) — `useState`
- CRUD 핸들러 3종:
  - `handleCreateDocument`: 새 빈 문서를 배열 앞에 추가하고 활성화
  - `handleDeleteDocument`: 확인 후 삭제, 활성 문서 삭제 시 다음 문서로 이동
  - `handleUpdateDocument`: id 매칭으로 배열 내 교체
- 초기 부트스트랩: 컬렉션이 비어 있으면 "Welcome to Wiki Workspace" 문서 시드

### 레이아웃
- 전체 화면 `flex` 좌우 분할: `<Sidebar>` (폭 `w-64`) + `<main>` (flex-1)
- `<main>` 은 상단 헤더(제목·아바타 스택·동기 시각) + 본문(에디터 카드)

### 설계 메모
- `documents.length`와 `activeDocumentId`를 dep로 쓰는 `useEffect`는 **한 번만** 초기 시드를 걸기 위한 장치.
  루프 위험을 피하기 위해 Phase 2에 들어가면 초기화 로직을 별도 훅(`useBootstrapDocuments`)으로 분리 권장.
- 상태 규모가 커지면 (폴더 · 태그 · 검색 · 공유 등) App의 useState를 Zustand 스토어로 이관.

---

## 2. `Sidebar`

위치: [`frontend/src/components/Sidebar.tsx`](../frontend/src/components/Sidebar.tsx)

### Props
```ts
interface SidebarProps {
  documents: Document[];
  activeDocumentId: string | null;
  onSelectDocument: (id: string) => void;
  onCreateDocument: () => void;
  onDeleteDocument: (id: string) => void;
}
```

> 2026-04-22 변경 이력: 같은 날 오전에 도입했던 `onLoadDemoScenarios: () => void` prop 은 같은 날 오후 데모 시나리오 로더(B+C) 철회와 함께 제거됨 — 상세: [08_tradeoffs.md](08_tradeoffs.md) 의사결정 변경 이력 2026-04-22 행.

### UI 구성
- 상단: 브랜드 배지 (`W` 블록) + "Personal Wiki" 라벨
- 중단 상단: 제목 검색 `<input type="search">` (PoC, 2026-04-22 도입)
- 중단: 문서 목록 (각 항목: 파일 아이콘 + 제목, hover 시 휴지통 버튼). 필터 결과 0건이면 "No documents match" 빈 상태 메시지
- 하단: `+ New Document` CTA 버튼 (단독)

### 상호작용 규칙
- 목록 항목 클릭 → `onSelectDocument(doc.id)`
- 휴지통 클릭은 `e.stopPropagation()` 으로 선택 이벤트와 분리
- 제목이 비어 있으면 `"Untitled Document"` 플레이스홀더
- 검색 입력 타이핑 → Sidebar 내부 `useState` 의 `query` 상태 즉시 갱신. `documents`를 `Array.filter` 로 `title.toLowerCase().includes(query.toLowerCase())` 매칭. debounce 없음, 본문 검색 없음(제목 전용 PoC).
- 활성 문서(`activeDocumentId`)가 필터 결과에서 숨겨져도 Editor 는 영향 없음(App 레벨 상태 불변).

### 확장 계획 (Phase 2+)
- 폴더 트리(무한 depth) — `documents`에 `parentId` 필드 추가 필요 ([05_data_schema.md](05_data_schema.md) 참조)
- 드래그 앤 드롭으로 순서 변경 → `dnd-kit` 검토
- 우측 상단 검색 입력 → 제목/본문 풀텍스트 필터 — **제목 필터 구현 완료(PoC, 2026-04-22) / 본문 필터 대기**. 본문 검색 합류 시 200ms debounce 와 인덱싱 라이브러리(Fuse.js 등) 도입 여부 재검토.
- 즐겨찾기 / 최근 방문 / 태그 섹션 분리

---

## 3. `Editor`

위치: [`frontend/src/components/Editor.tsx`](../frontend/src/components/Editor.tsx)

### Props
```ts
interface EditorProps {
  document: Document;
  onChange: (updatedDoc: Document) => void;
}
```

### 내부 상태
- `mode: "edit" | "split" | "preview"` — 상단 토글로 전환
- `localTitle`, `localContent` — 입력 즉시 반영용 로컬 state (부모 state로의 전파는 debounce)

### 동작 규칙
- **문서 전환 시 로컬 state 동기화**: `useEffect([document.id])` 에서 `localTitle/Content` 리셋.
  `document.title`이 아닌 `document.id`를 dep로 둬야 사용자가 방금 입력한 내용이 외부 푸시로 덮이지 않는다.
- **debounce 300ms**: 입력 직후마다 부모 `onChange` 호출 시 불필요한 렌더가 많아 `setTimeout` + `clearTimeout` 패턴.
- **모드별 레이아웃**:
  - `edit`: 에디터 단독
  - `preview`: 렌더된 마크다운 단독
  - `split`: 반응형 좌우 분할 (`md:` 브레이크포인트 이상에서만 좌우, 이하에선 상하)

### Markdown 렌더링
- `react-markdown` + `remark-gfm` 으로 GitHub Flavored Markdown(표·체크리스트·strikethrough) 지원.
- `prose` 클래스 계열로 Tailwind typography 적용.
- 인라인 코드는 `text-rose-600 bg-slate-100` 로 시각적 강조.

### 확장 계획 (Phase 2+)
- **AI 보조**: 상단에 "Summarize / Suggest title / Rewrite selection" 액션 버튼 → AI Panel 열기
- **툴바**: 헤딩/리스트/링크/이미지 삽입 단축 (현재 단축키 없음)
- **슬래시 커맨드**: `/` 입력 시 블록 삽입 메뉴 — Phase 2 후반
- **코드 하이라이팅**: `rehype-highlight` 또는 `shiki` 도입
- **수식**: `remark-math` + `rehype-katex` (선택)
- **첨부**: 드래그 드롭으로 이미지 붙여넣기 → Phase 3(Object Storage)

---

## 4. `AnalyzePanel` (Phase 2, 2026-04-22 재작성 — txt 업로드 기반 동적 흐름)

위치: [`frontend/src/components/AnalyzePanel.tsx`](../frontend/src/components/AnalyzePanel.tsx)

> 2026-04-22 변경 이력: 초기 PoC 는 "활성 문서 vs 나머지 문서" 를 비교하는 `Analyze Delta` 버튼 구조였으나, 같은 날 오후 "업로드 txt → TF-IDF Top-3 → docdelta" 동적 흐름으로 **전면 재작성**. 기존 Props `{activeDocument, otherDocuments}` 와 "Analyze Delta" 버튼은 제거. 상세 배경: [08_tradeoffs.md](08_tradeoffs.md) 의사결정 변경 이력 2026-04-22 행.

### Props
```ts
interface AnalyzePanelProps {
  documents: Document[];                                  // 전체 workspace 컬렉션 — TF-IDF 코퍼스
  onSaveUploadAsDocument: (uploaded: UploadedFile) => void; // 승격 콜백 (App 이 Document 로 변환하여 setDocuments)
}
```

- `UploadedFile` 은 `frontend/src/services/docdelta.ts` 에서 export 되는 **로컬 ephemeral 타입** (`types.ts` 의 `Document` 와는 별개). 5필드 불변(R4) + T3(단일 Document 플랫 타입) 유지.

### 내부 상태
- `phase: "idle" | "parsing" | "analyzing" | "result" | "error"` — 단순 상태머신
- `uploaded: UploadedFile | null` — 가장 최근 업로드 ephemeral 객체
- `topDocs: {id, score}[]` — TF-IDF Top-3 결과
- `analysis: DocdeltaResponse | null` — 서버 응답
- `errorMessage: string | null` — 사용자 노출 문구
- `isDragging: boolean` + `dragDepthRef` — drag-drop overlay 플리커 방지
- `savedUploadId: string | null` — 같은 업로드 중복 저장 방지 가드

외부 상태 라이브러리 미도입 (T11). 분석 결과·업로드 객체는 `Document`/localStorage 에 **자동 persist 하지 않는다** — 사용자가 "워크스페이스에 저장" 을 명시 클릭해야 Document 로 승격.

### 동작 규칙
- 업로드 진입점은 **두 개 병행**:
  1. 패널 헤더의 **"분석할 문서 업로드"** 버튼 (`Upload` 아이콘). 내부적으로 숨겨진 `<input type="file" accept=".txt,.md,text/plain,text/markdown">` 을 ref 로 클릭.
  2. 패널 루트의 **drag-drop zone** — `onDragEnter/Over/Leave/Drop` 바인딩, `dragDepthRef` 로 자식 요소 진출입 플리커 방지. 드래그 중 반투명 indigo 오버레이 + "분석할 .txt 파일을 놓으세요 (최대 100KB, UTF-8)" 라벨.
- `handleFile(file)` 파이프라인:
  1. **크기 검증**: `file.size > 100 * 1024` 면 `phase="error"` + "파일이 너무 큽니다 ({X.X}KB > 100KB)" 메시지.
  2. **UTF-8 디코딩**: `file.text()`. 결과에 U+FFFD 2개 이상이면 "UTF-8 인코딩이 아닌 파일은 지원하지 않습니다..." 에러.
  3. **ephemeral 생성**: `makeUploadedFile(file, text)` → `UploadedFile { doc_id: "upload-<8hex>", fileName, fileSize, content, uploadedAt }`.
  4. **TF-IDF Top-K**: [`utils/tfidf.ts`](../frontend/src/utils/tfidf.ts) 의 `selectTopK(uploaded.content, documents.map(d => ({id, content})), 3)` 호출. 빈 코퍼스면 `[]`.
  5. **분석 호출**: `analyzeDocdelta(uploaded, topDocs)` → `phase="result"` + `analysis` 저장. 네트워크/422/비정상 응답은 `phase="error"`.
- 결과 렌더:
  - **메타 섹션**: "업로드 문서: {fileName} ({X.X}KB)" + "비교 대상 (Top-N 유사도)" 목록 — 각 후보의 `title` + `score.toFixed(2)`. 빈 코퍼스에서는 "비교 대상 없음 (workspace 가 비어있습니다)" 표시.
  - **New** (`Plus` 아이콘): `analysis.output.new[]` bullet 리스트. 0개면 "No new detected".
  - **Conflicts** (`AlertTriangle` 아이콘): `analysis.output.conflict[]` 카드 리스트 — `doc_id`(mono), severity 뱃지(low=emerald / medium=amber / high=rose), `known_text`/`new_text` 2열 `<dl>`, `reason`(italic). 0개면 "No conflicts detected".
  - **"워크스페이스에 저장"** 버튼(결과 하단): 클릭 시 `onSaveUploadAsDocument(uploaded)` 호출 → App 이 `Document { id: UUID, title: fileName.replace(/\.(txt|md)$/i, ""), content, createdAt, updatedAt }` 로 승격. 같은 업로드 중복 저장 방지로 "저장됨" 상태 disabled (다음 업로드에서 리셋).
- **에러 UI**: `role="alert"` 빨간 박스(rose-50/200). 전역 에러 바운더리까지 튀지 않음 (T1 local-first).
- `activeDocument` 와 독립으로 렌더 — 활성 문서 없어도 업로드 가능.

### 레이아웃 배치
- Editor 카드 위 인라인 배치 유지 (드로어/모달 아님). `shrink-0` + 상태별 높이 가변. dropzone 오버레이는 패널 루트에만 바인딩되어 Editor 영역을 침범하지 않음.
- `activeDocument` 존재 여부와 **독립**: seed 만 있고 활성 문서가 없어도 업로드 entry 는 열려 있음.

### 접근성
- 버튼 `title` + `aria-label`, 포커스 링(`focus:ring-indigo-400`), 에러 박스 `role="alert"`, 아이콘 모두 `aria-hidden`. 숨겨진 `<input type="file">` 에도 `aria-hidden` + label 연결.

### 서비스 계층
- [`frontend/src/services/docdelta.ts`](../frontend/src/services/docdelta.ts) — `UploadedFile + Document[]` → `DocdeltaRequest` 매핑. `new_doc[0] = {doc_id: uploaded.doc_id, context: uploaded.content}`, `known_docs = topK.length>0 ? [topK.map(toDocRef)] : []` (빈 코퍼스는 빈 outer list `[]`), `convert_doc: []`, `instruction` 상수, `source_id = crypto.randomUUID()`. 네트워크/HTTP 실패를 `Error` 로 throw, 컴포넌트가 catch.
- [`frontend/src/utils/tfidf.ts`](../frontend/src/utils/tfidf.ts) — 의존성 0 순수 JS. 공백+어절 토큰화(NFKC + lowercase + 유니코드 구두점 split + 길이≥2), sklearn smoothed IDF `log((N+1)/(df+1))+1`, cosine similarity, 동점은 `id` 사전순 결정론적 타이브레이크.
- [`frontend/src/types/docdelta.ts`](../frontend/src/types/docdelta.ts) — `DocdeltaRequest`, `DocdeltaResponse`, `DocdeltaDocRef`, `DocdeltaConflict`, `DOCDELTA_INSTRUCTION`. 백엔드와 **수동 중복** (packages/shared 미도입, T12).

## 4a. 업로드 흐름 (AnalyzePanel 내부)

새 데모(2026-04-22)는 "사용자가 외부 txt 요약본을 업로드 → 시스템이 유사 문서 자동 선정 → 모델 분석 → 결과 렌더 → 선택적 승격" 이라는 실제 제품 동선을 그대로 재현한다.

### 진입점
- **패널 헤더 버튼** (주 CTA): 단축키 없음, 클릭 시 파일 선택 다이얼로그.
- **패널 루트 drag-drop zone** (부 CTA): Editor 영역 상단에 위치해 사용자가 파일을 자연스럽게 드롭 가능. 드롭 시 헤더 버튼과 동일 핸들러 (`handleFile`) 실행.
- 두 진입점은 **같은 파이프라인**(크기 검증 → UTF-8 디코딩 → ephemeral 생성 → TF-IDF → 분석 호출)을 공유 — UX 중복이 아니라 **접근 경로 다양성**.

### 제약 (엄격)
- **확장자**: `<input accept=".txt,.md,text/plain,text/markdown">` 로 선택 단계 1차 차단. 드래그드롭 우회 시 UTF-8 체크가 2차 방어.
- **크기 상한**: 100KB (= 102,400 bytes). 초과 시 즉시 거부, fetch 미발생.
- **인코딩**: UTF-8 강제. `file.text()` 결과에 U+FFFD(replacement char) 2개 이상이면 cp949/UTF-16 등으로 간주하고 거부.
- **빈 코퍼스 수용**: TF-IDF 토큰 0개(공백·구두점만) 이거나 workspace 에 Document 0건인 경우 — 전자는 "분석할 내용이 없습니다" 에러, 후자는 `known_docs: []` 로 요청 (backend mock 이 new 1건 + conflict 0건 반환).

### 승격 (선택적, Document 생성)
- 업로드본은 기본적으로 **일회성 분석 전용** — localStorage 자동 저장 없음.
- 사용자가 "워크스페이스에 저장" 클릭 시에만 Document 로 승격:
  - `id`: `crypto.randomUUID()` (seed 의 `seed-doc-N` 과 달리 영구 Document 는 UUID — 같은 파일을 여러 번 저장해도 별개 Document).
  - `title`: `fileName.replace(/\.(txt|md)$/i, "")` (확장자 제거).
  - `content`: 업로드 원문 그대로 (trim/변환 금지, R3 마크다운 원문 보존).
  - `createdAt` = `updatedAt` = `Date.now()`.
- 승격된 Document 는 seed 와 **동등 취급** — Sidebar/Editor/TF-IDF 코퍼스 어디서도 구분 없음 (`seeded`/`uploaded` 플래그 미도입, T3 유지).

---

## 5. `useLocalStorage` (Hook)

위치: [`frontend/src/hooks/useLocalStorage.ts`](../frontend/src/hooks/useLocalStorage.ts)

### 시그니처
```ts
export function useLocalStorage<T>(key: string, initialValue: T): readonly [T, (value: T | ((val: T) => T)) => void];
```

### 구현 포인트
- 초기값 lazy init: `useState(() => { ... })` 로 마운트 시 1회만 JSON 파싱
- 서버 사이드 렌더 안전: `typeof window === "undefined"` 가드
- `setValue`는 함수형 업데이트 지원 (`(prev) => next`)
- 직렬화 실패/파싱 실패는 `console.warn` + fallback

### 확장 계획
- Phase 2: 여러 탭 간 동기화 → `storage` 이벤트 구독
- Phase 3: 로컬 캐시 어댑터로 승격 (IndexedDB 백엔드로 교체 가능한 인터페이스)

---

## 6. (Phase 2+) 신규 컴포넌트 계획

| 컴포넌트 | 책임 | 도입 Phase |
|---|---|---|
| `CommandPalette` | `⌘K` 로 문서 검색/이동/액션 | 2 |
| `SearchBar` | 사이드바 상단 제목·본문 필터 | 2 |
| `AIPanel` | 우측 드로어. 요약/제안/재작성 — `AnalyzePanel`(docdelta PoC, 2026-04-22 구현) 을 탭으로 흡수 후보 | 2 |
| `Toolbar` | 에디터 상단 블록 서식 버튼 | 2 |
| `ShareDialog` | 링크 공유 · 권한 설정 | 3 |
| `PresenceAvatars` | 실시간 동시 편집 중인 사용자 표시 | 4 |
| `VersionHistory` | 문서 변경 히스토리 타임라인 | 4 |
| `SettingsModal` | 테마·동기·AI 키·단축키 | 2~3 |

---

## 7. 상태 관리 전략 (Phase별)

| Phase | 전략 | 근거 |
|---|---|---|
| 1 (현재) | `useState` + `useLocalStorage` | 컴포넌트 3개면 충분. 전역 스토어는 과잉. |
| 2 | **Zustand** 도입 | AI 패널·커맨드 팔레트가 멀리 떨어진 UI 곳곳에서 문서 상태 필요. |
| 3 | + **TanStack Query** | 서버 상태(동기화 · 낙관적 업데이트 · 무효화)가 등장. |
| 4 | + **Y.js**(선택) | CRDT 기반 실시간 협업 시. 도입은 비용이 크므로 "필요해질 때". |

---

## 8. 접근성/반응형 고려 (전체 컴포넌트 공통)

- **접근성**: 버튼의 `title`/`aria-label` 유지 · 포커스 링 유지 · 키보드 네비게이션.
- **반응형**: 사이드바는 `md:` 미만에서는 드로어로 변경(Phase 2). 에디터 split은 `md:` 이상에서만.
- **테마**: 현재 라이트 단독. 다크 모드는 Phase 2에서 `prefers-color-scheme` + 토글.
