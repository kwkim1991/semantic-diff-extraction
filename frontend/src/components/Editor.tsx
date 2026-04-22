import { useState, useEffect } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Document } from "../types";
import { Edit2, LayoutTemplate, Eye } from "lucide-react";

interface EditorProps {
  document: Document;
  onChange: (updatedDoc: Document) => void;
}

type EditorMode = "edit" | "preview" | "split";

export function Editor({ document, onChange }: EditorProps) {
  const [mode, setMode] = useState<EditorMode>("preview");

  const [localTitle, setLocalTitle] = useState(document.title);
  const [localContent, setLocalContent] = useState(document.content);

  // Sync state if a new document is selected
  useEffect(() => {
    setLocalTitle(document.title);
    setLocalContent(document.content);
  }, [document.id]);

  // Push changes upward with a short debounce to improve typing feel
  useEffect(() => {
    const timeout = setTimeout(() => {
      onChange({ ...document, title: localTitle, content: localContent, updatedAt: Date.now() });
    }, 300);
    return () => clearTimeout(timeout);
  }, [localTitle, localContent]);

  const renderPreview = () => (
    <div className="prose prose-slate prose-p:leading-relaxed prose-headings:font-semibold prose-h1:text-4xl prose-h1:tracking-tight prose-h1:text-slate-900 prose-h2:text-2xl prose-h2:mt-10 prose-h2:mb-4 prose-h2:border-b prose-h2:border-slate-100 prose-h2:pb-2 prose-h3:text-xl prose-li:my-0.5 prose-blockquote:border-l-4 prose-blockquote:border-slate-200 prose-blockquote:text-slate-600 prose-blockquote:not-italic prose-blockquote:bg-slate-50 prose-blockquote:py-2 prose-blockquote:px-4 prose-blockquote:rounded-r prose-code:bg-slate-100 prose-code:text-rose-600 prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded-md prose-code:before:content-none prose-code:after:content-none max-w-none text-slate-700">
      {localContent ? (
        <Markdown remarkPlugins={[remarkGfm]}>{localContent}</Markdown>
      ) : (
        <p className="text-slate-400 italic font-light">Press 'Edit' and start typing...</p>
      )}
    </div>
  );

  return (
    <div className="flex-1 flex flex-col h-full bg-white relative">
      {/* Top Header / Mode Toggles */}
      <div className="h-14 border-b border-slate-100 flex items-center justify-end px-6 shrink-0 gap-2">
        <div className="flex items-center bg-slate-100 p-1 rounded-lg">
          <button
            onClick={() => setMode("edit")}
            className={`p-1.5 rounded-md flex items-center justify-center text-slate-600 transition-all duration-200 ${
              mode === "edit" ? "bg-white shadow-sm text-slate-900 font-medium" : "hover:text-slate-900 hover:bg-slate-200/50"
            }`}
            title="Edit mode"
          >
            <Edit2 className="w-4 h-4" />
          </button>
          <button
            onClick={() => setMode("split")}
            className={`p-1.5 rounded-md flex items-center justify-center text-slate-600 transition-all duration-200 ${
              mode === "split" ? "bg-white shadow-sm text-slate-900 font-medium" : "hover:text-slate-900 hover:bg-slate-200/50"
            }`}
            title="Split mode"
          >
            <LayoutTemplate className="w-4 h-4" />
          </button>
          <button
            onClick={() => setMode("preview")}
            className={`p-1.5 rounded-md flex items-center justify-center text-slate-600 transition-all duration-200 ${
              mode === "preview" ? "bg-white shadow-sm text-slate-900 font-medium" : "hover:text-slate-900 hover:bg-slate-200/50"
            }`}
            title="Preview mode"
          >
            <Eye className="w-4 h-4" />
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-hidden flex flex-col md:flex-row w-full bg-white">
        {/* Editor Area */}
        {mode !== "preview" && (
          <div className={`flex-1 flex flex-col overflow-y-auto px-12 py-16 custom-scrollbar border-r border-transparent ${mode === 'split' ? 'md:border-slate-100 bg-slate-50/30' : ''}`}>
            <div className="max-w-3xl w-full mx-auto flex flex-col flex-1">
              <input
                type="text"
                value={localTitle}
                onChange={(e) => setLocalTitle(e.target.value)}
                placeholder="Untitled"
                className="w-full text-4xl sm:text-5xl font-bold text-slate-900 bg-transparent border-none outline-none mb-8 placeholder:text-slate-200 tracking-tight"
              />
              <textarea
                value={localContent}
                onChange={(e) => setLocalContent(e.target.value)}
                placeholder="Start writing..."
                className="flex-1 w-full auto-rows-auto resize-none text-slate-700 bg-transparent border-none outline-none text-[17px] leading-relaxed font-sans placeholder:text-slate-300"
              />
            </div>
          </div>
        )}

        {/* Preview Area */}
        {mode !== "edit" && (
          <div className="flex-1 overflow-y-auto px-12 py-16 bg-white custom-scrollbar">
            <div className="max-w-3xl w-full mx-auto">
              <h1 className="text-4xl sm:text-5xl font-bold text-slate-900 mb-10 tracking-tight">{localTitle || "Untitled"}</h1>
              {renderPreview()}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
