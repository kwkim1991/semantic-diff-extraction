# 05. 데이터 스키마

## 1. `Document` — 도메인 타입 (현재 · source of truth)

위치: [`frontend/src/types.ts`](../frontend/src/types.ts)

```ts
export interface Document {
  id: string;         // UUID (crypto.randomUUID() 또는 Date.now() fallback)
  title: string;      // 빈 문자열 허용 → UI에서 "Untitled"로 표시
  content: string;    // 마크다운 원문 (CommonMark + GFM)
  createdAt: number;  // epoch ms
  updatedAt: number;  // epoch ms — 편집 시마다 갱신(debounce 후)
}
```

### 설계 원칙
- **플랫한 필드**: 중첩 없이 메타를 얕게 유지 → JSON 직렬화·diff·마이그레이션 단순.
- **마크다운 원문 보관**: 파싱된 AST가 아니라 문자열 그대로. 타 툴로 이동성 확보.
- **타임스탬프는 숫자**: ISO 문자열보다 비교·정렬·직렬화가 저렴. 서버도 동일 포맷 유지.

---

## 2. localStorage Schema (Phase 1)

| Key | Value | 용도 |
|---|---|---|
| `wiki-docs` | `Document[]` JSON | 전체 문서 컬렉션 |
| (Phase 2) `wiki-settings` | `{ theme, aiEnabled, ... }` | 사용자 설정 |
| (Phase 2) `wiki-ui` | `{ lastActiveId, sidebarCollapsed, ... }` | UI 상태 |

### 주의
- localStorage 용량 한도(≈5MB). 문서 수가 많아지면 Phase 3에서 IndexedDB로 이관.
- 파싱 실패 시 `useLocalStorage` 훅이 `console.warn` 후 initialValue 반환 (데이터 손실 위험은 Phase 3에서 export 자동 백업으로 보완).

---

## 3. 확장 필드 로드맵

현재 5개 필드만으로 시작하되, 아래 항목들은 **도입 시점이 오기 전까지 추가하지 않는다** (YAGNI).

| 필드 | 타입 | 도입 Phase | 목적 |
|---|---|---|---|
| `parentId` | `string \| null` | 2 | 폴더 트리 |
| `icon` | `string` | 2 | 이모지/lucide 아이콘 |
| `tags` | `string[]` | 2 | 태그 필터 |
| `archivedAt` | `number \| null` | 2 | 아카이브(삭제와 구분) |
| `pinned` | `boolean` | 2 | 즐겨찾기 |
| `version` | `number` | 3 | 서버 낙관적 동시성 |
| `ownerId` | `string` | 3 | 사용자 귀속 |
| `sharedWith` | `{ userId, role }[]` | 4 | 협업 권한 |
| `lockedBy` | `string \| null` | 4 | 편집 잠금 (CRDT 대안) |

---

## 4. Postgres 스키마 (Phase 3 이후 제안)

### `users`
| 컬럼 | 타입 |
|---|---|
| `user_id` | uuid PK |
| `email` | text UNIQUE |
| `name` | text |
| `created_at` | timestamptz |

### `documents`
| 컬럼 | 타입 | 설명 |
|---|---|---|
| `id` | uuid PK | 클라이언트 발급 UUID와 동일 |
| `owner_id` | uuid FK → users | |
| `parent_id` | uuid nullable FK → documents | 폴더 트리 |
| `title` | text | |
| `content` | text | 마크다운 원문 |
| `icon` | text nullable | |
| `tags` | text[] | |
| `version` | int | 낙관적 락용(매 PUT 시 +1) |
| `archived_at` | timestamptz nullable | |
| `created_at` | timestamptz | |
| `updated_at` | timestamptz | |

인덱스: `(owner_id, updated_at DESC)`, `(owner_id, parent_id)`, `tags GIN`.

### `document_versions` (Phase 4)
| 컬럼 | 타입 |
|---|---|
| `version_id` | uuid PK |
| `document_id` | uuid FK |
| `version` | int |
| `content` | text |
| `edited_by` | uuid |
| `created_at` | timestamptz |

전체 스냅샷 보존은 비용이 크므로 **JSON Patch 델타**로 저장하는 방안도 후보 — 도입 시 결정.

### `shares` (Phase 4)
| 컬럼 | 타입 |
|---|---|
| `share_id` | uuid PK |
| `document_id` | uuid FK |
| `grantee_id` | uuid nullable FK (이메일 초대 대기 시 null) |
| `grantee_email` | text nullable |
| `role` | text (`viewer`/`commenter`/`editor`) |
| `created_at` | timestamptz |

---

## 5. 서버 ↔ 클라이언트 매핑 규약

- 서버 DB 컬럼은 `snake_case`, API 응답 필드는 **클라이언트와 동일한 `camelCase`** 로 직렬화(DB와 API 사이에서 매핑).
- 타임스탬프는 DB는 `timestamptz`, API는 **epoch ms 숫자**. 클라이언트 코드에서는 `Document` 타입 그대로 쓰도록.
- `content`는 **항상 마크다운 원문**. 서버가 HTML을 렌더해서 저장/반환하는 경로는 만들지 않는다 (렌더는 클라 전담).

### docdelta 매핑 (Phase 2a PoC, 2026-04-22)

`Document` 타입은 **변경 없음** (§1 그대로). `reference/doc_scheme.json` 기반 `DocdeltaRequest`/`DocdeltaResponse`와의 매핑은 프론트 서비스 계층([`frontend/src/services/docdelta.ts`](../frontend/src/services/docdelta.ts))에서만 수행하며 `Document`는 그대로 보존된다.

- `Document.id` ↔ `DocdeltaDocRef.doc_id`
- `Document.content` ↔ `DocdeltaDocRef.context` (마크다운 원문 그대로, HTML 변환 없음)
- 활성 문서 → `new_doc` (단일 원소 배열), 나머지 문서 → `known_docs[0]` (단일 그룹의 2D 배열)
- 응답 `output.new[]`·`output.conflict[]`는 `AnalyzePanel` 로컬 state에만 존재 — `Document`·localStorage에 persist 금지 (T3 하위 호환).

상세 계약: [`_workspace/03_data_contract.md`](../_workspace/03_data_contract.md).

---

## 6. 마이그레이션 / 데이터 이동성

### Phase 1 → 3 승격
- 사용자가 로그인하면, 로컬 `wiki-docs`를 서버로 일괄 업로드(merge upsert, id 충돌 시 서버가 우선).
- 이후엔 로컬은 **캐시**, 서버는 **정본**.

### Export / Import (전 Phase 지원)
- **Export**: 전체 문서를 `.zip` 혹은 단일 JSON 파일로 다운로드. 문서별 `.md` 파일로 분해 옵션 제공.
- **Import**: `.md` / `.zip` / JSON 업로드 → 서버가(또는 클라가) `Document[]` 로 변환.
- Markdown 표준 준수의 목적은 바로 이 **이동성**이다.
