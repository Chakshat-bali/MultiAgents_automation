import { useState } from "react";
import { submitTask } from "../api/client";

interface Props {
  onTaskSubmitted: (taskId: string) => void;
}

const FORMAT_OPTIONS = [
  {
    value: "markdown", label: "Markdown", desc: "Headers, bold, lists",
    icon: (
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
        <path d="M2 4h12M2 8h8M2 12h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
      </svg>
    ),
  },
  {
    value: "text", label: "Plain Text", desc: "Clean prose output",
    icon: (
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
        <path d="M3 4h10M3 8h10M3 12h6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
      </svg>
    ),
  },
  {
    value: "bullet", label: "Bullet Points", desc: "Concise list format",
    icon: (
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
        <circle cx="3.5" cy="4.5" r="1.5" fill="currentColor"/>
        <circle cx="3.5" cy="8" r="1.5" fill="currentColor"/>
        <circle cx="3.5" cy="11.5" r="1.5" fill="currentColor"/>
        <path d="M7 4.5h7M7 8h7M7 11.5h7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
      </svg>
    ),
  },
  {
    value: "json", label: "JSON", desc: "Structured data output",
    icon: (
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
        <path d="M5 3C4 3 3 4 3 5v2c0 1-1 1-1 1s1 0 1 1v2c0 1 1 2 2 2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
        <path d="M11 3c1 0 2 1 2 2v2c0 1 1 1 1 1s-1 0-1 1v2c0 1-1 2-2 2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
      </svg>
    ),
  },
];

const EXAMPLE_TASKS = [
  "Research the top 3 AI startups in healthcare and summarize their funding and products",
  "Analyze the competitive landscape for B2B SaaS CRM tools in 2025",
  "Find recent news and funding rounds for Anthropic, Mistral, and Cohere",
];

export default function TaskInput({ onTaskSubmitted }: Props) {
  const [task, setTask]       = useState("");
  const [format, setFormat]   = useState<"markdown" | "json" | "bullet" | "text">("markdown");
  const [context, setContext] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState<string | null>(null);
  const [showExamples, setShowExamples] = useState(false);
  const [btnHover, setBtnHover]         = useState(false);
  const [hoverFormat, setHoverFormat]   = useState<string | null>(null);

  const handleSubmit = async () => {
    if (task.trim().length < 10) { setError("Please enter at least 10 characters."); return; }
    setError(null);
    setLoading(true);
    try {
      const res = await submitTask({ task: task.trim(), output_format: format, context: context.trim() || undefined });
      onTaskSubmitted(res.task_id);
    } catch (e: any) {
      setError(e?.response?.data?.detail?.reason || e?.message || "Submission failed. Is the backend running?");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="card animate-fade-in" style={{ maxWidth: 1000, margin: "0 auto", padding: "28px 32px" }}>

      {/* 3 Steps / Instructions */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 16, marginBottom: 28 }}>
        <div style={{
          display: "flex", flexDirection: "column", gap: 8,
          background: "linear-gradient(135deg, rgba(99, 102, 241, 0.06) 0%, rgba(139, 92, 246, 0.03) 100%)",
          border: "1px solid rgba(99, 102, 241, 0.12)", borderRadius: 14, padding: "16px 20px",
          boxShadow: "0 4px 15px rgba(99, 102, 241, 0.02)",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ display: "flex", alignItems: "center", justifyContent: "center", width: 22, height: 22, borderRadius: "50%", background: "linear-gradient(135deg, var(--color-accent) 0%, var(--color-accent-2) 100%)", color: "#fff", fontSize: 11, fontWeight: 700, boxShadow: "0 2px 6px rgba(99, 102, 241, 0.2)" }}>1</span>
            <span style={{ fontSize: 13, fontWeight: 700, color: "var(--color-text)" }}>Define Task</span>
          </div>
          <span style={{ fontSize: 12, color: "var(--color-text-2)", lineHeight: 1.45 }}>Enter your research topic and choose your preferred output format.</span>
        </div>
        <div style={{
          display: "flex", flexDirection: "column", gap: 8,
          background: "linear-gradient(135deg, rgba(99, 102, 241, 0.06) 0%, rgba(139, 92, 246, 0.03) 100%)",
          border: "1px solid rgba(99, 102, 241, 0.12)", borderRadius: 14, padding: "16px 20px",
          boxShadow: "0 4px 15px rgba(99, 102, 241, 0.02)",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ display: "flex", alignItems: "center", justifyContent: "center", width: 22, height: 22, borderRadius: "50%", background: "linear-gradient(135deg, var(--color-accent) 0%, var(--color-accent-2) 100%)", color: "#fff", fontSize: 11, fontWeight: 700, boxShadow: "0 2px 6px rgba(99, 102, 241, 0.2)" }}>2</span>
            <span style={{ fontSize: 13, fontWeight: 700, color: "var(--color-text)" }}>Run Pipeline</span>
          </div>
          <span style={{ fontSize: 12, color: "var(--color-text-2)", lineHeight: 1.45 }}>Specialist AI agents search, summarize, and write in parallel.</span>
        </div>
        <div style={{
          display: "flex", flexDirection: "column", gap: 8,
          background: "linear-gradient(135deg, rgba(99, 102, 241, 0.06) 0%, rgba(139, 92, 246, 0.03) 100%)",
          border: "1px solid rgba(99, 102, 241, 0.12)", borderRadius: 14, padding: "16px 20px",
          boxShadow: "0 4px 15px rgba(99, 102, 241, 0.02)",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ display: "flex", alignItems: "center", justifyContent: "center", width: 22, height: 22, borderRadius: "50%", background: "linear-gradient(135deg, var(--color-accent) 0%, var(--color-accent-2) 100%)", color: "#fff", fontSize: 11, fontWeight: 700, boxShadow: "0 2px 6px rgba(99, 102, 241, 0.2)" }}>3</span>
            <span style={{ fontSize: 13, fontWeight: 700, color: "var(--color-text)" }}>Get Report</span>
          </div>
          <span style={{ fontSize: 12, color: "var(--color-text-2)", lineHeight: 1.45 }}>Receive a polished, high-confidence report with PII safety checks.</span>
        </div>
      </div>

      {/* Example chips */}
      {showExamples && (
        <div style={{ marginBottom: 20, display: "flex", flexDirection: "column", gap: 6 }}>
          {EXAMPLE_TASKS.map((ex, i) => (
            <button
              key={i}
              onClick={() => { setTask(ex); setShowExamples(false); }}
              style={{
                textAlign: "left", padding: "11px 16px", borderRadius: 10,
                border: "1px solid var(--color-border)", background: "rgba(0, 0, 0, 0.02)",
                fontSize: 13, color: "var(--color-text-2)", cursor: "pointer",
                transition: "all 0.2s ease", lineHeight: 1.5,
              }}
              onMouseEnter={e => {
                (e.currentTarget as HTMLElement).style.borderColor = "var(--color-accent)";
                (e.currentTarget as HTMLElement).style.background = "rgba(99, 102, 241, 0.04)";
                (e.currentTarget as HTMLElement).style.color = "var(--color-accent)";
              }}
              onMouseLeave={e => {
                (e.currentTarget as HTMLElement).style.borderColor = "var(--color-border)";
                (e.currentTarget as HTMLElement).style.background = "rgba(0, 0, 0, 0.02)";
                (e.currentTarget as HTMLElement).style.color = "var(--color-text-2)";
              }}
            >
              <span style={{ color: "var(--color-accent)", marginRight: 8, fontSize: 11, fontWeight: 700 }}>#{i + 1}</span>
              {ex}
            </button>
          ))}
        </div>
      )}

      {/* Task textarea */}
      <div style={{ marginBottom: 20 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
          <label style={{ display: "block", fontSize: 11, fontWeight: 700, color: "var(--color-text-2)", letterSpacing: "0.06em", textTransform: "uppercase", margin: 0 }}>
            Task Description
          </label>
          <button
            onClick={() => setShowExamples(!showExamples)}
            style={{
              display: "flex", alignItems: "center", gap: 6,
              padding: "5px 12px", borderRadius: 8, border: "1px solid var(--color-border)",
              background: "rgba(0, 0, 0, 0.02)", color: "var(--color-accent)", fontSize: 11, fontWeight: 700,
              cursor: "pointer", transition: "all 0.15s",
            }}
            onMouseEnter={e => {
              (e.currentTarget as HTMLElement).style.borderColor = "var(--color-accent)";
              (e.currentTarget as HTMLElement).style.background = "rgba(99, 102, 241, 0.08)";
            }}
            onMouseLeave={e => {
              (e.currentTarget as HTMLElement).style.borderColor = "var(--color-border)";
              (e.currentTarget as HTMLElement).style.background = "rgba(0, 0, 0, 0.02)";
            }}
          >
            <svg width="12" height="12" viewBox="0 0 13 13" fill="none">
              <path d="M2 4.5h9M2 6.5h6M2 8.5h7" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/>
            </svg>
            Examples
          </button>
        </div>
        <textarea
          rows={4}
          placeholder="e.g. Research the top 3 insurtech startups in India and write a competitive analysis report..."
          value={task}
          onChange={e => setTask(e.target.value)}
          style={{
            width: "100%", padding: "14px 16px", fontSize: 14, color: "var(--color-text)",
            background: "rgba(255, 255, 255, 0.7)", border: "1px solid var(--color-border)", borderRadius: 12,
            outline: "none", resize: "vertical", minHeight: 110,
            fontFamily: "inherit", lineHeight: 1.6, transition: "all 0.2s ease",
            boxSizing: "border-box",
          }}
          onFocus={e => {
            e.target.style.borderColor = "var(--color-accent)";
            e.target.style.boxShadow = "0 0 10px rgba(99, 102, 241, 0.15)";
          }}
          onBlur={e => {
            e.target.style.borderColor = "var(--color-border)";
            e.target.style.boxShadow = "none";
          }}
        />
        <div style={{ textAlign: "right", fontSize: 11, color: task.length > 500 ? "#f59e0b" : "var(--color-text-3)", marginTop: 6 }}>
          {task.length} chars
        </div>
      </div>

      {/* Format selector */}
      <div style={{ marginBottom: 20 }}>
        <label style={{ display: "block", fontSize: 11, fontWeight: 700, color: "var(--color-text-2)", letterSpacing: "0.06em", textTransform: "uppercase", marginBottom: 10 }}>
          Output Format
        </label>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10 }}>
          {FORMAT_OPTIONS.map(opt => {
            const active = format === opt.value;
            const isHovered = hoverFormat === opt.value;
            return (
              <button
                key={opt.value}
                onClick={() => setFormat(opt.value as any)}
                onMouseEnter={() => setHoverFormat(opt.value)}
                onMouseLeave={() => setHoverFormat(null)}
                style={{
                  padding: "12px 14px", borderRadius: 12, textAlign: "left",
                  border: active ? "1.5px solid var(--color-accent)" : (isHovered ? "1.5px solid rgba(99, 102, 241, 0.3)" : "1.5px solid var(--color-border)"),
                  background: active ? "rgba(99, 102, 241, 0.05)" : (isHovered ? "rgba(99, 102, 241, 0.01)" : "rgba(0, 0, 0, 0.02)"),
                  color: active ? "var(--color-accent)" : "var(--color-text-2)",
                  cursor: "pointer",
                  transform: active ? "scale(1.01)" : (isHovered ? "translateY(-1px)" : "none"),
                  transition: "all 0.2s cubic-bezier(0.4, 0, 0.2, 1)",
                  display: "flex", flexDirection: "column", gap: 6,
                  boxShadow: active ? "0 4px 15px rgba(99, 102, 241, 0.08)" : (isHovered ? "0 2px 8px rgba(0,0,0,0.02)" : "none"),
                }}
              >
                <span style={{ color: active ? "var(--color-accent)" : "var(--color-text-3)", transition: "color 0.2s" }}>{opt.icon}</span>
                <span style={{ fontSize: 12, fontWeight: 750 }}>{opt.label}</span>
                <span style={{ fontSize: 11, opacity: 0.7, lineHeight: 1.3, color: "var(--color-text-2)" }}>{opt.desc}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Context input */}
      <div style={{ marginBottom: 24 }}>
        <label style={{ display: "block", fontSize: 11, fontWeight: 700, color: "var(--color-text-2)", letterSpacing: "0.06em", textTransform: "uppercase", marginBottom: 10 }}>
          Extra Context{" "}
          <span style={{ fontWeight: 400, textTransform: "none", letterSpacing: 0, color: "var(--color-text-3)", fontSize: 11 }}>(optional)</span>
        </label>
        <input
          placeholder="e.g. Focus on B2B SaaS companies with >$10M funding, India market only..."
          value={context}
          onChange={e => setContext(e.target.value)}
          style={{
            width: "100%", padding: "12px 16px", fontSize: 13, color: "var(--color-text)",
            background: "rgba(255, 255, 255, 0.7)", border: "1px solid var(--color-border)", borderRadius: 10,
            outline: "none", fontFamily: "inherit", transition: "all 0.2s ease",
            boxSizing: "border-box",
          }}
          onFocus={e => {
            e.target.style.borderColor = "var(--color-accent)";
            e.target.style.boxShadow = "0 0 10px rgba(99, 102, 241, 0.15)";
          }}
          onBlur={e => {
            e.target.style.borderColor = "var(--color-border)";
            e.target.style.boxShadow = "none";
          }}
        />
      </div>

      {/* Error */}
      {error && (
        <div style={{
          marginBottom: 18, padding: "12px 16px", borderRadius: 10, fontSize: 13,
          background: "rgba(239, 68, 68, 0.08)", border: "1px solid rgba(239, 68, 68, 0.2)", color: "#f87171",
          display: "flex", alignItems: "center", gap: 10,
        }}>
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" style={{ flexShrink: 0 }}>
            <circle cx="7" cy="7" r="6" stroke="#f87171" strokeWidth="1.4"/>
            <path d="M7 4.5v3" stroke="#f87171" strokeWidth="1.4" strokeLinecap="round"/>
            <circle cx="7" cy="9.5" r="0.8" fill="#f87171"/>
          </svg>
          {error}
        </div>
      )}

      {/* Submit */}
      <button
        onClick={handleSubmit}
        disabled={loading}
        onMouseEnter={() => setBtnHover(true)}
        onMouseLeave={() => setBtnHover(false)}
        style={{
          width: "100%", padding: "14px", borderRadius: 12, border: "none",
          fontSize: 14, fontWeight: 700, cursor: loading ? "not-allowed" : "pointer",
          background: loading
            ? "rgba(99, 102, 241, 0.3)"
            : "linear-gradient(135deg, var(--color-accent) 0%, var(--color-accent-2) 100%)",
          color: "#fff",
          boxShadow: loading ? "none" : btnHover ? "0 6px 24px rgba(99, 102, 241, 0.45)" : "0 4px 20px rgba(99, 102, 241, 0.35)",
          transform: loading ? "none" : btnHover ? "translateY(-1px) scale(1.005)" : "none",
          transition: "all 0.25s cubic-bezier(0.4, 0, 0.2, 1)",
          display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
        }}
      >
        {loading ? (
          <>
            <span style={{ width: 16, height: 16, border: "2px solid rgba(255,255,255,0.3)", borderTop: "2px solid #fff", borderRadius: "50%", display: "inline-block", animation: "spin 0.7s linear infinite" }} />
            Submitting task...
          </>
        ) : (
          <>
            Run Task
            <svg width="15" height="15" viewBox="0 0 15 15" fill="none">
              <path d="M3 7.5h9M8.5 4l3.5 3.5L8.5 11" stroke="white" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </>
        )}
      </button>

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
