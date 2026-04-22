import { useState, useEffect } from "react";
import { Sidebar } from "./components/Sidebar";
import { Editor } from "./components/Editor";
import { AnalyzePanel } from "./components/AnalyzePanel";
import { useLocalStorage } from "./hooks/useLocalStorage";
import { Document } from "./types";
import { loadSeedDocuments } from "./utils/loadSeedDocuments";
import type { UploadedFile } from "./services/docdelta";
import { FileText } from "lucide-react";

function generateDocumentId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return Date.now().toString();
}

export default function App() {
  const [documents, setDocuments] = useLocalStorage<Document[]>("wiki-docs", []);
  const [activeDocumentId, setActiveDocumentId] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<"editor" | "analyze">("editor");

  // 데이터 강제 초기화 (Demo 데이터 대체)
  useEffect(() => {
    const DATA_VERSION = "2026-04-22-v2"; // 버전을 올려서 다시 초기화 유도
    const currentVersion = localStorage.getItem("wiki-docs-version");

    if (currentVersion !== DATA_VERSION) {
      const seeded = loadSeedDocuments();
      setDocuments(seeded);
      if (seeded.length > 0) {
        setActiveDocumentId(seeded[0].id);
      }
      localStorage.setItem("wiki-docs-version", DATA_VERSION);
    }
  }, []);

  // 문서 목록이 있는데 활성 문서가 없는 경우 첫 번째 문서 선택
  useEffect(() => {
    if (documents.length > 0 && !activeDocumentId) {
      setActiveDocumentId(documents[0].id);
    }
  }, [documents, activeDocumentId]);

  const activeDocument =
    documents.find((doc) => doc.id === activeDocumentId) || null;

  const handleCreateDocument = () => {
    // 새 문서 버튼 클릭 시 업로드/분석 페이지로 이동
    setViewMode("analyze");
  };

  const handleSelectDocument = (id: string) => {
    setActiveDocumentId(id);
    setViewMode("editor"); // 문서 선택 시 에디터로 복귀
  };

  const handleDeleteDocument = (id: string) => {
    if (!window.confirm("Are you sure you want to delete this document?"))
      return;
    setDocuments((prev) => prev.filter((doc) => doc.id !== id));
    if (activeDocumentId === id) {
      const remaining = documents.filter((doc) => doc.id !== id);
      setActiveDocumentId(remaining.length > 0 ? remaining[0].id : null);
    }
  };

  const handleUpdateDocument = (updatedDoc: Document) => {
    setDocuments((prev) =>
      prev.map((doc) => (doc.id === updatedDoc.id ? updatedDoc : doc)),
    );
  };

  const handleSaveUploadAsDocument = (uploaded: UploadedFile) => {
    const now = Date.now();
    const newDoc: Document = {
      id: generateDocumentId(),
      title: uploaded.name.replace(/\.(txt|md)$/i, ""),
      content: uploaded.content,
      createdAt: now,
      updatedAt: now,
    };
    setDocuments((prev) => [newDoc, ...prev]);
    setActiveDocumentId(newDoc.id);
    setViewMode("editor"); // 저장 후 에디터로 전환
  };

  return (
    <div className="flex h-screen w-screen overflow-hidden text-slate-900 bg-slate-50 font-sans">
      <Sidebar
        documents={documents}
        activeDocumentId={activeDocumentId}
        onSelectDocument={handleSelectDocument}
        onCreateDocument={handleCreateDocument}
        onDeleteDocument={handleDeleteDocument}
      />

      <main className="flex-1 p-8 flex flex-col gap-6 overflow-hidden">
        <header className="flex items-end justify-between shrink-0">
          <div>
            <h1 className="text-3xl font-bold text-slate-900 tracking-tight">
              Knowledge Base
            </h1>
            <p className="text-slate-500 text-sm mt-1">
              Organize your thoughts, reports, and team collaborations.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex -space-x-2">
              <div
                className="w-8 h-8 rounded-full border-2 border-white bg-indigo-200"
                title="You"
              ></div>
              <div
                className="w-8 h-8 rounded-full border-2 border-white bg-rose-200"
                title="Sarah"
              ></div>
              <div
                className="w-8 h-8 rounded-full border-2 border-white bg-slate-200"
                title="Alex"
              ></div>
            </div>
            <span className="text-xs font-medium text-slate-400">
              Last synced: Just now
            </span>
          </div>
        </header>

        <div className="flex-1 bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden flex flex-col min-h-0 relative">
          {viewMode === "analyze" ? (
            <AnalyzePanel
              documents={documents}
              onSaveUploadAsDocument={handleSaveUploadAsDocument}
              onCancel={() => setViewMode("editor")}
            />
          ) : activeDocument ? (
            <Editor document={activeDocument} onChange={handleUpdateDocument} />
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center bg-white text-slate-500 p-6">
              <div className="w-20 h-20 bg-slate-50 rounded-2xl border border-slate-200 flex items-center justify-center text-4xl mb-6 shadow-sm">
                <FileText className="w-8 h-8 text-slate-400" />
              </div>
              <p className="mb-4 text-sm font-medium text-slate-600">
                Select a document or create a new one.
              </p>
              <button
                onClick={handleCreateDocument}
                className="flex items-center justify-center gap-2 py-2 px-4 bg-slate-900 text-white rounded-lg text-xs font-semibold hover:bg-slate-800 transition-colors shadow-sm"
              >
                + New Document
              </button>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
