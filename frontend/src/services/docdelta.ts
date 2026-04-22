/**
 * Client-side wrapper for `POST /api/ai/docdelta`.
 *
 * Responsibilities:
 *  - Map the uploaded file + Top-K known Documents into the reference-scheme request body.
 *  - Fetch the backend and return a typed `DocdeltaResponse`.
 *  - Surface backend error payloads and network failures as thrown `Error`s so
 *    that the caller (업로드 UI) can render them in local state only
 *    (local-first invariant — see _workspace/02_architect_decision.md).
 *
 * Mapping rules come from `_workspace/03_data_contract.md` §4. The markdown/txt
 * content is passed through verbatim; no HTML conversion happens here.
 */
import type { Document } from "../types";
import type {
  DocdeltaDocRef,
  DocdeltaErrorResponse,
  DocdeltaRequest,
  DocdeltaResponse,
} from "../types/docdelta";
import { DOCDELTA_INSTRUCTION } from "../types/docdelta";

// Empty default -> requests go to same origin as the page (`/api/...`). In dev
// the Vite server proxies `/api` to the FastAPI backend (see vite.config.ts);
// in other envs set VITE_API_BASE_URL to point elsewhere.
const DEFAULT_API_BASE_URL = "";

function resolveApiBaseUrl(): string {
  // Vite exposes env vars on `import.meta.env`. Fall back to localhost so the
  // feature works out of the box for local PoC development.
  const fromEnv = (
    import.meta as unknown as { env?: Record<string, string | undefined> }
  ).env?.VITE_API_BASE_URL;
  return fromEnv && fromEnv.trim().length > 0 ? fromEnv : DEFAULT_API_BASE_URL;
}

function generateSourceId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return Date.now().toString();
}

function generateUploadId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `upload-${crypto.randomUUID().replace(/-/g, "").slice(0, 8)}`;
  }
  return `upload-${Date.now().toString(16).slice(-8)}`;
}

/** Ephemeral 업로드 파일 객체. 분석 흐름 전용, Document 와 구분된다. */
export interface UploadedFile {
  /** ephemeral doc_id (`upload-<8hex>`). DocdeltaRequest.new_doc[0].doc_id 로 사용. */
  doc_id: string;
  /** 원본 파일명 (확장자 포함). AnalyzePanel 메타 표시용. */
  name: string;
  /** 업로드 파일 원문 (UTF-8 디코딩 결과). */
  content: string;
  /** 파일 크기 (bytes). 메타 표시용. */
  size: number;
}

function toDocRef(doc: Document): DocdeltaDocRef {
  return {
    doc_id: doc.id,
    context: doc.content,
  };
}

/**
 * 업로드 파일 객체 생성 헬퍼. (file.text() 디코딩은 호출부에서 수행.)
 */
export function makeUploadedFile(
  file: { name: string; size: number },
  content: string,
): UploadedFile {
  return {
    doc_id: generateUploadId(),
    name: file.name,
    content,
    size: file.size,
  };
}

/**
 * 업로드된 ephemeral 파일 + Top-K workspace Document 를 받아
 * `POST /api/ai/docdelta` 요청 바디를 생성한다.
 *
 * - `source_id`: 매 요청 랜덤 UUID (DEMO-* 분기 완전 제거).
 * - `known_docs`: Top-K 가 비어있으면 `[]` (빈 outer list). 1건 이상이면 단일 그룹
 *   `[topKDocs.map(toDocRef)]`. data contract §3.4 / §4.2.
 * - `new_doc`: `[{doc_id: uploaded.doc_id, context: uploaded.content}]`.
 * - `convert_doc`: `[]` 명시 전달 (Phase 2 PoC 에서는 사용 안 함).
 */
export function buildDocdeltaRequest(
  uploaded: UploadedFile,
  topKDocs: Document[],
): DocdeltaRequest {
  return {
    source_id: generateSourceId(),
    instruction: DOCDELTA_INSTRUCTION,
    known_docs: topKDocs.length > 0 ? [topKDocs.map(toDocRef)] : [],
    new_doc: [{ doc_id: uploaded.doc_id, context: uploaded.content }],
    convert_doc: [],
  };
}

/**
 * Call the mock (or real) backend docdelta endpoint.
 *
 * Throws an `Error` when:
 *  - the server responds with a non-2xx (message taken from the server's
 *    `{ error: { message } }` payload when available), or
 *  - the fetch itself rejects (network down, CORS, backend not running).
 *
 * The caller is expected to catch and render the message in a panel; the
 * error must NOT escape to a global boundary (local-first invariant).
 */
export async function analyzeDocdelta(
  uploaded: UploadedFile,
  topKDocs: Document[],
): Promise<DocdeltaResponse> {
  const baseUrl = resolveApiBaseUrl();
  const url = `${baseUrl.replace(/\/$/, "")}/api/ai/docdelta`;
  const body = buildDocdeltaRequest(uploaded, topKDocs);

  let response: Response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch (err) {
    // TypeError on network failure / CORS block / backend not listening.
    const detail = err instanceof Error ? err.message : String(err);
    throw new Error(`서버에 연결할 수 없습니다 (${detail})`);
  }

  if (!response.ok) {
    let serverMessage = response.statusText || `HTTP ${response.status}`;
    try {
      const payload = (await response.json()) as
        | DocdeltaErrorResponse
        | undefined;
      if (payload?.error?.message) {
        serverMessage = payload.error.message;
      }
    } catch {
      // Non-JSON error body — keep statusText.
    }
    throw new Error(`분석 요청 실패: ${serverMessage}`);
  }

  const json = (await response.json()) as DocdeltaResponse;
  return json;
}
