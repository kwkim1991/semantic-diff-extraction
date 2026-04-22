import { useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  FileText,
  Loader2,
  Plus,
  Save,
  Sparkles,
  Upload,
} from "lucide-react";
import type { Document } from "../types";
import type { DocdeltaConflict, DocdeltaResponse } from "../types/docdelta";
import {
  analyzeDocdelta,
  makeUploadedFile,
  type UploadedFile,
} from "../services/docdelta";
import { selectTopK } from "../utils/tfidf";

interface AnalyzePanelProps {
  documents: Document[];
  onSaveUploadAsDocument: (uploaded: UploadedFile) => void;
  onCancel: () => void;
}

type Phase = "idle" | "parsing" | "analyzing" | "result" | "error";

interface Candidate {
  doc: Document;
  score: number;
}

interface AnalysisState {
  uploaded: UploadedFile;
  candidates: Candidate[];
  result: DocdeltaResponse;
}

const MAX_FILE_BYTES = 100 * 1024; // 100KB (JEDEC)
const REPLACEMENT_CHAR = "\uFFFD"; // UTF-8 디코딩 실패 시 생성되는 대체 문자

const SEVERITY_STYLES: Record<DocdeltaConflict["severity"], string> = {
  low: "bg-emerald-50 text-emerald-700 border-emerald-200",
  medium: "bg-amber-50 text-amber-700 border-amber-200",
  high: "bg-rose-50 text-rose-700 border-rose-200",
};

function formatKB(bytes: number): string {
  return `${(bytes / 1024).toFixed(1)}KB`;
}

export function AnalyzePanel({
  documents,
  onSaveUploadAsDocument,
  onCancel,
}: AnalyzePanelProps) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<AnalysisState | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [saved, setSaved] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const dragDepthRef = useRef(0);

  const resetForNewUpload = () => {
    setError(null);
    setAnalysis(null);
    setSaved(false);
    setPhase("idle");
  };

  const handleFile = async (file: File) => {
    resetForNewUpload();

    if (file.size > MAX_FILE_BYTES) {
      setPhase("error");
      setError(
        `파일이 너무 큽니다 (${formatKB(file.size)} > 100KB). 더 작은 파일을 업로드해주세요.`,
      );
      return;
    }

    setPhase("parsing");

    let text: string;
    try {
      text = await file.text();
    } catch (err) {
      setPhase("error");
      const detail = err instanceof Error ? err.message : String(err);
      setError(`파일을 읽을 수 없습니다 (${detail})`);
      return;
    }

    // UTF-8 헬시체크
    const replacementCount = (text.match(new RegExp(REPLACEMENT_CHAR, "g")) ?? [])
      .length;
    if (replacementCount >= 2) {
      setPhase("error");
      setError(
        "UTF-8 인코딩이 아닌 파일은 지원하지 않습니다. 파일을 UTF-8 로 변환해 다시 업로드해주세요.",
      );
      return;
    }

    const uploaded = makeUploadedFile(file, text);

    // TF-IDF Top-3 선정
    const corpus = documents.map((d) => ({
      id: d.id,
      content: `${d.title}\n${d.content}`,
    }));
    const top3 = selectTopK(uploaded.content, corpus, 3);
    const candidates: Candidate[] = top3
      .map(({ id, score }) => {
        const doc = documents.find((d) => d.id === id);
        return doc ? { doc, score } : null;
      })
      .filter((c): c is Candidate => c !== null);
    const topDocs = candidates.map((c) => c.doc);

    setPhase("analyzing");
    try {
      const result = await analyzeDocdelta(uploaded, topDocs);
      setAnalysis({ uploaded, candidates, result });
      setPhase("result");
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "알 수 없는 오류가 발생했습니다";
      setPhase("error");
      setError(message);
    }
  };

  const onInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      void handleFile(file);
    }
    e.target.value = "";
  };

  const onDragEnter = (e: React.DragEvent<HTMLDivElement>) => {
    if (!e.dataTransfer.types.includes("Files")) return;
    e.preventDefault();
    dragDepthRef.current += 1;
    setIsDragging(true);
  };

  const onDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    if (!e.dataTransfer.types.includes("Files")) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "copy";
  };

  const onDragLeave = (e: React.DragEvent<HTMLDivElement>) => {
    if (!e.dataTransfer.types.includes("Files")) return;
    e.preventDefault();
    dragDepthRef.current = Math.max(0, dragDepthRef.current - 1);
    if (dragDepthRef.current === 0) setIsDragging(false);
  };

  const onDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    dragDepthRef.current = 0;
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) {
      void handleFile(file);
    }
  };

  const handleSave = () => {
    if (!analysis) return;
    onSaveUploadAsDocument(analysis.uploaded);
    setSaved(true);
  };

  const busy = phase === "parsing" || phase === "analyzing";

  return (
    <div
      className="flex-1 flex flex-col min-h-0 bg-white"
      onDragEnter={onDragEnter}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".txt,.md,text/plain,text/markdown"
        onChange={onInputChange}
        className="hidden"
      />

      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
        <div className="flex items-center gap-4">
          <button
            onClick={onCancel}
            className="p-2 hover:bg-slate-50 rounded-full transition-colors text-slate-500"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div>
            <h2 className="text-lg font-bold text-slate-900 flex items-center gap-2">
              <Sparkles className="w-5 h-5 text-indigo-500" />
              Scenario Analysis
            </h2>
            <p className="text-xs text-slate-500">
              Upload a scenario summary to compare with existing knowledge.
            </p>
          </div>
        </div>

        {phase === "result" && (
          <div className="flex items-center gap-2">
            <button
              onClick={resetForNewUpload}
              className="px-3 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-50 rounded-lg transition-colors border border-slate-200"
            >
              Analyze New File
            </button>
            <button
              onClick={handleSave}
              disabled={saved}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-700 disabled:bg-slate-300 transition-colors shadow-sm"
            >
              <Save className="w-3.5 h-3.5" />
              {saved ? "Saved" : "Save to Workspace"}
            </button>
          </div>
        )}
      </div>

      <div className="flex-1 overflow-y-auto custom-scrollbar relative">
        {isDragging && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-indigo-500/5 border-4 border-dashed border-indigo-500 m-4 rounded-2xl">
            <div className="flex flex-col items-center gap-3 text-indigo-700">
              <Upload className="w-12 h-12" />
              <span className="text-xl font-bold">Drop your file here</span>
            </div>
          </div>
        )}

        {phase === "idle" && (
          <div className="h-full flex flex-col items-center justify-center p-12 text-center">
            <div className="w-20 h-20 bg-indigo-50 rounded-3xl flex items-center justify-center mb-6 border border-indigo-100 shadow-sm">
              <Upload className="w-8 h-8 text-indigo-500" />
            </div>
            <h3 className="text-xl font-bold text-slate-900 mb-2">
              Upload Scenario Summary
            </h3>
            <p className="text-slate-500 max-w-sm mb-8 text-sm">
              Drag and drop your .txt or .md file to analyze its impact on existing scenarios.
            </p>
            <button
              onClick={() => inputRef.current?.click()}
              className="flex items-center gap-2 px-6 py-3 bg-slate-900 text-white rounded-xl font-semibold hover:bg-slate-800 transition-all shadow-md"
            >
              <Plus className="w-5 h-5" />
              Select File
            </button>
          </div>
        )}

        {busy && (
          <div className="h-full flex flex-col items-center justify-center p-12 text-center">
            <div className="w-16 h-16 border-4 border-slate-100 border-t-indigo-500 rounded-full animate-spin mb-6"></div>
            <h3 className="text-lg font-bold text-slate-900 mb-2">
              {phase === "parsing" ? "Parsing file..." : "Analyzing differences..."}
            </h3>
            <p className="text-slate-500 text-sm animate-pulse">
              Comparing with Top-3 similar documents in your knowledge base.
            </p>
          </div>
        )}

        {phase === "error" && (
          <div className="h-full flex flex-col items-center justify-center p-12 text-center">
            <div className="w-20 h-20 bg-rose-50 rounded-full flex items-center justify-center mb-6 border border-rose-100">
              <AlertTriangle className="w-8 h-8 text-rose-500" />
            </div>
            <h3 className="text-lg font-bold text-slate-900 mb-2">Error Occurred</h3>
            <p className="text-rose-600 bg-rose-50 px-4 py-2 rounded-lg text-sm mb-6 max-w-md">
              {error}
            </p>
            <button
              onClick={resetForNewUpload}
              className="px-4 py-2 bg-slate-900 text-white rounded-lg font-semibold"
            >
              Try Again
            </button>
          </div>
        )}

        {phase === "result" && analysis && (
          <div className="max-w-4xl mx-auto p-8 space-y-8">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="p-4 rounded-xl border border-slate-200 bg-slate-50">
                <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">
                  File Analyzed
                </div>
                <div className="font-bold text-slate-900 truncate text-sm">
                  {analysis.uploaded.name}
                </div>
                <div className="text-[10px] text-slate-400">
                  {formatKB(analysis.uploaded.size)}
                </div>
              </div>

              <div className="col-span-2 p-4 rounded-xl border border-indigo-100 bg-indigo-50/50">
                <div className="text-[10px] font-bold text-indigo-400 uppercase tracking-wider mb-2">
                  Similar Context Found (Top-3)
                </div>
                <div className="flex flex-wrap gap-2">
                  {analysis.candidates.map((c) => (
                    <div
                      key={c.doc.id}
                      className="px-2 py-1 bg-white border border-indigo-100 rounded-lg text-[11px] flex items-center gap-1.5"
                    >
                      <span className="font-medium text-slate-700 truncate max-w-[150px]">
                        {c.doc.title || "Untitled"}
                      </span>
                      <span className="text-indigo-500">
                        {(c.score * 100).toFixed(0)}%
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
              <section className="space-y-4">
                <h4 className="flex items-center gap-2 text-xs font-bold text-emerald-700 uppercase">
                  <Plus className="w-3 h-3" /> New Facts
                </h4>
                <div className="space-y-2">
                  {analysis.result.output.new.map((item, idx) => (
                    <div
                      key={idx}
                      className="p-4 rounded-xl border border-emerald-100 bg-emerald-50/20 text-sm text-slate-700 leading-relaxed"
                    >
                      {item}
                    </div>
                  ))}
                  {analysis.result.output.new.length === 0 && (
                    <div className="text-slate-400 text-xs italic">No new facts detected.</div>
                  )}
                </div>
              </section>

              <section className="space-y-4">
                <h4 className="flex items-center gap-2 text-xs font-bold text-amber-700 uppercase">
                  <AlertTriangle className="w-3 h-3" /> Potential Conflicts
                </h4>
                <div className="space-y-4">
                  {analysis.result.output.conflict.map((conflict, idx) => (
                    <div
                      key={idx}
                      className="p-4 rounded-xl border border-amber-200 bg-amber-50/20 space-y-3"
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-[9px] font-bold text-amber-600 bg-amber-100 px-1.5 py-0.5 rounded uppercase">
                          vs {analysis.candidates.find(c => c.doc.id === conflict.doc_id)?.doc.title || "Existing"}
                        </span>
                        <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded-full border uppercase ${SEVERITY_STYLES[conflict.severity]}`}>
                          {conflict.severity}
                        </span>
                      </div>
                      <div className="grid grid-cols-1 gap-2">
                        <div className="text-[10px] text-slate-400 font-bold uppercase">New Point</div>
                        <div className="text-xs text-slate-800 font-medium">{conflict.new_text}</div>
                        <div className="text-[10px] text-slate-400 font-bold uppercase mt-1">Existing Context</div>
                        <div className="text-xs text-slate-600">{conflict.known_text}</div>
                      </div>
                      <div className="pt-2 border-t border-amber-100 text-xs text-amber-800 italic">
                        💡 {conflict.reason}
                      </div>
                    </div>
                  ))}
                  {analysis.result.output.conflict.length === 0 && (
                    <div className="text-slate-400 text-xs italic">No logic conflicts detected.</div>
                  )}
                </div>
              </section>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
