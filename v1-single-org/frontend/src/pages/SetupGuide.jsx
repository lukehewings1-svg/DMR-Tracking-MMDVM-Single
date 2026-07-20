import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ArrowLeft, Download, BookOpen } from "lucide-react";

export default function SetupGuide() {
  const [markdown, setMarkdown] = useState("");
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const md = await fetch("/SETUP.md").then((r) =>
          r.ok ? r.text() : Promise.reject(r.status)
        );
        setMarkdown(md);
      } catch (e) {
        setErr(String(e));
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  return (
    <div className="min-h-screen bg-[#050505] text-neutral-100" data-testid="setup-guide-page">
      <header className="sticky top-0 z-10 flex items-center justify-between border-b border-[#2a2a2a] bg-[#050505]/95 px-4 py-3 backdrop-blur">
        <div className="flex items-center gap-3">
          <Link
            data-testid="setup-back"
            to="/"
            className="flex items-center gap-1 border border-[#2a2a2a] px-2 py-1 mono text-[11px] uppercase tracking-widest text-neutral-400 hover:border-[#00f0ff] hover:text-[#00f0ff]"
          >
            <ArrowLeft className="h-3 w-3" /> Dashboard
          </Link>
          <div>
            <div className="text-[10px] uppercase tracking-[0.3em] text-neutral-500">
              Documentation
            </div>
            <h1 className="flex items-center gap-2 text-lg font-semibold">
              <BookOpen className="h-4 w-4 text-[#00f0ff]" /> DMR Tracker · Setup Guide
            </h1>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <a
            data-testid="setup-download-md"
            href="/SETUP.md"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 border border-[#2a2a2a] px-2 py-1 mono text-[11px] uppercase tracking-widest text-neutral-400 hover:border-[#00f0ff] hover:text-[#00f0ff]"
          >
            <Download className="h-3 w-3" /> Raw
          </a>
        </div>
      </header>

      <main className="mx-auto max-w-4xl px-6 py-8">
        {loading && (
          <div className="mono text-xs text-neutral-500">loading setup guide…</div>
        )}
        {err && (
          <div className="border border-[#ff3b30]/40 bg-[#1a0505] px-3 py-2 mono text-xs text-[#ff3b30]">
            Failed to load setup guide: {err}
          </div>
        )}
        {!loading && !err && (
          <article className="setup-guide prose prose-invert max-w-none">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{markdown}</ReactMarkdown>
          </article>
        )}
      </main>
    </div>
  );
}
