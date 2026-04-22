/**
 * TF-IDF 유사도 유틸 (의존성 0, 순수 JS).
 *
 * - 업로드 문서(query)와 workspace Document 코퍼스 간 cosine similarity 계산.
 * - architect decision §5 + data contract §3 스펙 준수.
 *   - 토큰화: NFKC + lowercase + 구두점·공백 split + 길이 ≥ 2.
 *   - IDF: log((N+1)/(df+1)) + 1 (sklearn smoothed).
 *   - TF: raw count (정규화 없이 cosine 이 길이 효과를 흡수).
 *   - Top-K 선정, 동점은 Document.id 사전순.
 *   - 빈 코퍼스: 빈 배열 반환.
 */

/**
 * 텍스트를 토큰 배열로 변환한다.
 *
 * 1. NFKC 정규화 (한글 자소 분리·전각/반각 통일).
 * 2. 소문자화 (영문만 영향).
 * 3. 유니코드 구두점·기호·공백으로 split.
 * 4. 길이 2자 이상 토큰만 유지.
 */
export function tokenize(text: string): string[] {
  const normalized = text.normalize("NFKC").toLowerCase();
  // \p{P} = punctuation, \p{S} = symbol, \s = whitespace. u 플래그 필수.
  const rawTokens = normalized.split(/[\s\p{P}\p{S}]+/u);
  return rawTokens.filter((tok) => tok.length >= 2);
}

interface CorpusEntry {
  id: string;
  content: string;
}

interface Scored {
  id: string;
  score: number;
}

/**
 * query 문서와 corpus 간 cosine similarity 를 계산해 Top-K 를 반환한다.
 *
 * @param query 비교 질의 텍스트 (업로드 파일 원문).
 * @param corpus IDF·점수 대상이 될 문서 집합 (workspace Document).
 *               query 자체는 포함하지 말 것 (IDF 왜곡 방지).
 * @param k 상위 K 개.
 * @returns `{id, score}[]` cosine similarity 내림차순. 동점은 id 사전순.
 *          corpus 가 비었으면 빈 배열.
 */
export function selectTopK(
  query: string,
  corpus: CorpusEntry[],
  k: number,
): Scored[] {
  if (corpus.length === 0 || k <= 0) return [];

  // 1) 각 document 의 raw TF 계산.
  const docTfs: Map<string, Map<string, number>> = new Map();
  for (const entry of corpus) {
    const counts = new Map<string, number>();
    for (const tok of tokenize(entry.content)) {
      counts.set(tok, (counts.get(tok) ?? 0) + 1);
    }
    docTfs.set(entry.id, counts);
  }

  const queryTf = new Map<string, number>();
  for (const tok of tokenize(query)) {
    queryTf.set(tok, (queryTf.get(tok) ?? 0) + 1);
  }
  if (queryTf.size === 0) return [];

  // 2) IDF 계산 (corpus 기반).
  const n = corpus.length;
  const df = new Map<string, number>();
  for (const counts of docTfs.values()) {
    for (const tok of counts.keys()) {
      df.set(tok, (df.get(tok) ?? 0) + 1);
    }
  }

  const idf = new Map<string, number>();
  // query 에만 나오는 토큰은 df=0 으로 smoothed IDF 계산 (sklearn 스타일)
  const tokensOfInterest = new Set<string>([...df.keys(), ...queryTf.keys()]);
  for (const tok of tokensOfInterest) {
    const dfi = df.get(tok) ?? 0;
    idf.set(tok, Math.log((n + 1) / (dfi + 1)) + 1);
  }

  // 3) query vector (tf * idf).
  const queryVec = new Map<string, number>();
  let queryNormSq = 0;
  for (const [tok, tf] of queryTf) {
    const w = tf * (idf.get(tok) ?? 0);
    if (w !== 0) {
      queryVec.set(tok, w);
      queryNormSq += w * w;
    }
  }
  const queryNorm = Math.sqrt(queryNormSq);
  if (queryNorm === 0) return [];

  // 4) 각 document vector 와 cosine similarity.
  const scored: Scored[] = [];
  for (const entry of corpus) {
    const docTf = docTfs.get(entry.id)!;
    let dot = 0;
    let docNormSq = 0;
    for (const [tok, tf] of docTf) {
      const w = tf * (idf.get(tok) ?? 0);
      if (w === 0) continue;
      docNormSq += w * w;
      const qw = queryVec.get(tok);
      if (qw !== undefined) {
        dot += qw * w;
      }
    }
    const docNorm = Math.sqrt(docNormSq);
    const score = docNorm === 0 ? 0 : dot / (queryNorm * docNorm);
    scored.push({ id: entry.id, score });
  }

  // 5) 정렬: score 내림차순, 동점은 id 사전순.
  scored.sort((a, b) => {
    if (b.score !== a.score) return b.score - a.score;
    return a.id < b.id ? -1 : a.id > b.id ? 1 : 0;
  });

  return scored.slice(0, k);
}
