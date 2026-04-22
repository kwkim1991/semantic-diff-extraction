/**
 * DocDelta API contract (frontend side).
 *
 * Authoritative source: `reference/doc_scheme.json`.
 * Shared with backend as a hand-maintained copy at `backend/src/types/docdelta.ts`
 * (no packages/shared until Phase 3 — see T12, _workspace/02_architect_decision.md §5).
 *
 * These types are a separate module from `src/types.ts` (the `Document` type).
 * `Document` is NOT modified — analysis results live only in component state,
 * never persisted into `Document` (hub T3: backward compatibility).
 */

/** A reference to a document passed to/through the docdelta endpoint. */
export interface DocdeltaDocRef {
  /** Maps from `Document.id`. */
  doc_id: string;
  /** Maps from `Document.content` (raw markdown, not HTML). */
  context: string;
}

/** Request body for `POST /api/ai/docdelta`. */
export interface DocdeltaRequest {
  /** Client-generated ad-hoc id per request. Format: `"S-" + crypto.randomUUID().slice(0, 8)`. */
  source_id: string;
  /** Fixed instruction string; server never overwrites. See `DOCDELTA_INSTRUCTION`. */
  instruction: string;
  /** 2D array of known-document groups. Phase 2 PoC always uses a single group: `[nonActiveDocs]`. */
  known_docs: DocdeltaDocRef[][];
  /** Exactly one element: the currently active document. */
  new_doc: DocdeltaDocRef[];
  /** Learning-schema compatibility field. PoC always sends `[]`; server tolerates it. */
  convert_doc: DocdeltaDocRef[];
}

/** Single conflict item from the response `output.conflict[]`. */
export interface DocdeltaConflict {
  /** Matches a `doc_id` from `known_docs` (any group). */
  doc_id: string;
  /** The conflicting passage as it exists in the known doc. */
  known_text: string;
  /** The conflicting passage as it appears in the new doc. */
  new_text: string;
  /** Human-readable rationale of the conflict. */
  reason: string;
  /** Normalized to one of three levels. */
  severity: "low" | "medium" | "high";
}

/** Response body for `POST /api/ai/docdelta` (200 OK, JSON mode). */
export interface DocdeltaResponse {
  /** Echoed from the request. */
  source_id: string;
  output: {
    /** New facts not present in any known doc. */
    new: string[];
    /** Conflicts between new_doc and known_docs. */
    conflict: DocdeltaConflict[];
  };
}

/** Error payload shape shared with the rest of the API (`docs/04_api.md` common format). */
export interface DocdeltaErrorResponse {
  error: {
    /** e.g. `"VALIDATION"`, `"AI_UPSTREAM"`, `"TIMEOUT"`. */
    code: string;
    message: string;
  };
}

/**
 * Fixed instruction string. Verbatim copy from `reference/doc_scheme.json`.
 * Must not be edited client-side in the PoC; user-editable instruction UI is a separate task.
 */
export const DOCDELTA_INSTRUCTION =
  "기존 시나리오/설정 문서들(known_docs)을 기준으로 업로드된 신규 시나리오 요약본(new_doc)에서 차이점을 분석하세요. new: 기존 설정에 없는 새로운 설정이나 시나리오 전개. conflict: 기존 설정이나 과거 시나리오와 논리적으로 충돌하는 내용. 단순한 표현 차이나 이미 존재하는 내용은 무시하고, 의미 있는 변화와 모순만 추출하세요.";
