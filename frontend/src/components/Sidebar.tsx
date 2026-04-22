import { useState } from "react";
import { FileText, Plus, Trash2 } from "lucide-react";
import { Document } from "../types";

interface SidebarProps {
  documents: Document[];
  activeDocumentId: string | null;
  onSelectDocument: (id: string) => void;
  onCreateDocument: () => void;
  onDeleteDocument: (id: string) => void;
}

export function Sidebar({
  documents,
  activeDocumentId,
  onSelectDocument,
  onCreateDocument,
  onDeleteDocument,
}: SidebarProps) {
  const [query, setQuery] = useState("");

  const normalizedQuery = query.trim().toLowerCase();
  const filteredDocuments =
    normalizedQuery === ""
      ? documents
      : documents.filter((doc) =>
          doc.title.toLowerCase().includes(normalizedQuery),
        );

  return (
    <aside className="w-64 bg-white border-r border-slate-200 flex flex-col shrink-0 h-full">
      <div className="p-6 flex items-center gap-3">
        <div className="w-8 h-8 bg-indigo-600 rounded-lg flex items-center justify-center text-white font-bold text-sm">W</div>
        <span className="font-semibold tracking-tight text-slate-800 uppercase text-xs">Personal Wiki</span>
      </div>

      <nav className="flex-1 overflow-y-auto px-4 space-y-1 custom-scrollbar">
        <div className="px-3 py-2 text-xs font-medium text-slate-400 uppercase tracking-wider">Workspace</div>
        <div className="px-3 pb-2">
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search titles…"
            aria-label="Filter documents by title"
            className="w-full px-3 py-1.5 text-sm bg-slate-50 border border-slate-200 rounded-md text-slate-700 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
          />
        </div>
        {filteredDocuments.length === 0 ? (
          <div className="px-3 py-2 text-xs text-slate-400 italic">No documents match</div>
        ) : (
          filteredDocuments.map((doc) => (
            <div
              key={doc.id}
              onClick={() => onSelectDocument(doc.id)}
              className={`group flex items-center justify-between px-3 py-2 cursor-pointer rounded-lg text-sm transition-colors ${
                activeDocumentId === doc.id
                  ? "bg-slate-100 font-medium text-indigo-700"
                  : "text-slate-600 hover:bg-slate-50"
              }`}
            >
              <div className="flex items-center gap-3 truncate pr-2">
                <FileText className="w-4 h-4 shrink-0" />
                <span className="truncate">{doc.title || "Untitled Document"}</span>
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onDeleteDocument(doc.id);
                }}
                className="opacity-0 group-hover:opacity-100 p-1 hover:bg-slate-200 rounded text-slate-500 transition-opacity shrink-0"
                title="Delete document"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
          ))
        )}
      </nav>

      <div className="p-4 border-t border-slate-100 mt-2 shrink-0">
        <button
          onClick={onCreateDocument}
          className="w-full flex items-center justify-center gap-2 py-2 px-4 bg-slate-900 text-white rounded-lg text-xs font-semibold hover:bg-slate-800 transition-colors"
        >
          <Plus className="w-4 h-4" />
          <span>New Document</span>
        </button>
      </div>
    </aside>
  );
}
