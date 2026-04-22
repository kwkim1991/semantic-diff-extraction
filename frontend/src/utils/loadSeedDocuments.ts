/**
 * Seed 로더 — `frontend/src/data/*.json` 파일들을 Document[] 로 변환.
 *
 * - architect decision §3 + data contract §1 스펙 준수.
 * - Vite `import.meta.glob` 로 빌드 타임 eager 로딩.
 * - 파일명 숫자 기준 natural sort (1, 2, ..., N — 알파벳 정렬 회피).
 * - JSON 내의 title, content 필드를 직접 사용.
 * - id 는 `seed-doc-{N}` 결정론적 문자열 (crypto.randomUUID 미사용).
 */
import type { Document } from "../types";

/**
 * Seed Document 목록을 반환한다. App 최초 진입 시점에 한 번 호출.
 *
 * @returns Document[] — 파일명 숫자 오름차순(1→N).
 */
export function loadSeedDocuments(): Document[] {
  // Vite 의 정적 분석을 위해 import.meta.glob 을 직접 호출해야 함
  const modules = import.meta.glob("../data/*.json", {
    eager: true,
    import: "default",
  }) as Record<string, { title: string; content: string }>;

  const now = Date.now();
  const entries = Object.entries(modules)
    .map(([path, data]) => {
      const m = path.match(/(\d+)\.json$/);
      const n = m ? parseInt(m[1], 10) : Number.MAX_SAFE_INTEGER;
      return { n, data };
    })
    .filter((e) => e.n !== Number.MAX_SAFE_INTEGER)
    .sort((a, b) => a.n - b.n);

  return entries.map(({ n, data }) => ({
    id: `seed-doc-${n}`,
    title: data.title,
    content: data.content,
    createdAt: now,
    updatedAt: now,
  }));
}
