import { useEffect, useRef, useState } from "react";
import { getTaskStatus } from "../api/client";
import type { TaskStatusResponse } from "../api/client";

interface Props {
  taskId: string | null;
  onStatusChange: (status: string) => void;
}

// ── Markdown renderer ─────────────────────────────────────────────────────────
function renderMarkdown(text: string): string {
  if (!text) return "";

  // Strip suppressed fields
  let md = text
    .replace(/Signal level: (HIGH|MEDIUM|LOW)/gi, "")
    .replace(/OVERALL SIGNAL:.*$/gm, "");

  const lines = md.split("\n");
  const out: string[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // Horizontal rule
    if (/^---+$/.test(line.trim())) {
      out.push('<hr style="border:none;border-top:1px solid var(--color-border);margin:1.25rem 0;" />');
      i++; continue;
    }

    // Table: detect header row followed by separator
    if (line.includes("|") && i + 1 < lines.length && /^\|[-| :]+\|$/.test(lines[i + 1].trim())) {
      const headers = line.split("|").map(c => c.trim()).filter(Boolean);
      i += 2; // skip separator
      const rows: string[][] = [];
      while (i < lines.length && lines[i].includes("|")) {
        rows.push(lines[i].split("|").map(c => c.trim()).filter(Boolean));
        i++;
      }
      const thCells = headers.map(h => `<th style="padding:7px 12px;text-align:left;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;color:var(--color-text-2);white-space:nowrap;">${applyInline(h)}</th>`).join("");
      const trRows = rows.map(row => {
        const cells = headers.map((_, ci) => `<td style="padding:7px 12px;font-size:13px;color:var(--color-text);border-top:1px solid var(--color-border);">${applyInline(row[ci] || "")}</td>`).join("");
        return `<tr>${cells}</tr>`;
      }).join("");
      out.push(`<div style="overflow-x:auto;margin:.75rem 0 1rem;border-radius:8px;border:1px solid var(--color-border);"><table style="width:100%;border-collapse:collapse;"><thead><tr style="background:rgba(99,102,241,0.07);">${thCells}</tr></thead><tbody>${trRows}</tbody></table></div>`);
      continue;
    }

    // H1
    if (/^# (.+)/.test(line)) {
      out.push(`<h1 style="font-size:1.15rem;font-weight:800;color:var(--color-text);margin:1.5rem 0 .4rem;padding-bottom:.4rem;border-bottom:1px solid var(--color-border);">${applyInline(line.replace(/^# /, ""))}</h1>`);
      i++; continue;
    }
    // H2
    if (/^## (.+)/.test(line)) {
      out.push(`<h2 style="font-size:1rem;font-weight:700;color:var(--color-text);margin:1.25rem 0 .35rem;">${applyInline(line.replace(/^## /, ""))}</h2>`);
      i++; continue;
    }
    // H3
    if (/^### (.+)/.test(line)) {
      out.push(`<h3 style="font-size:.9rem;font-weight:700;color:var(--color-text-2);margin:.9rem 0 .25rem;">${applyInline(line.replace(/^### /, ""))}</h3>`);
      i++; continue;
    }

    // Ordered list item
    if (/^\d+\. (.+)/.test(line)) {
      const listItems: string[] = [];
      while (i < lines.length && /^\d+\. (.+)/.test(lines[i])) {
        listItems.push(`<li style="margin:.3rem 0;color:var(--color-text-2);font-size:13.5px;line-height:1.65;">${applyInline(lines[i].replace(/^\d+\. /, ""))}</li>`);
        i++;
      }
      out.push(`<ol style="margin:.5rem 0;padding-left:1.4rem;">${listItems.join("")}</ol>`);
      continue;
    }

    // Unordered list item
    if (/^[-*] (.+)/.test(line)) {
      const listItems: string[] = [];
      while (i < lines.length && /^[-*] (.+)/.test(lines[i])) {
        listItems.push(`<li style="margin:.3rem 0;color:var(--color-text-2);font-size:13.5px;line-height:1.65;">${applyInline(lines[i].replace(/^[-*] /, ""))}</li>`);
        i++;
      }
      out.push(`<ul style="margin:.5rem 0;padding-left:1.4rem;list-style:disc;">${listItems.join("")}</ul>`);
      continue;
    }

    // Non-empty paragraph
    if (line.trim()) {
      out.push(`<p style="margin:.5rem 0;color:var(--color-text-2);font-size:13.5px;line-height:1.7;">${applyInline(line)}</p>`);
    }

    i++;
  }

  return out.join("\n");
}

function applyInline(text: string): string {
  return text
    .replace(/\*\*(.+?)\*\*/g, "<strong style=\"color:var(--color-text);font-weight:700;\">$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(/`(.+?)`/g, `<code style="background:rgba(99,102,241,0.13);border:1px solid rgba(99,102,241,0.22);padding:.1em .4em;border-radius:4px;font-size:.85em;color:#a5b4fc;font-family:monospace;">$1</code>`);
}


// ── Status config ─────────────────────────────────────────────────────────────
const STATUS_CONFIG: Record<string, { icon: React.ReactNode; label: string; bg: string; color: string; border: string }> = {
  pending: {
    label: "Pending",
    bg: "rgba(245, 158, 11, 0.08)", color: "#fbbf24", border: "rgba(245, 158, 11, 0.2)",
    icon: (
      <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
        <circle cx="7" cy="7" r="5.5" stroke="currentColor" strokeWidth="1.4"/>
        <path d="M7 4.5V7l2 1.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
      </svg>
    ),
  },
  running: {
    label: "Running",
    bg: "rgba(99, 102, 241, 0.08)", color: "#818cf8", border: "rgba(99, 102, 241, 0.2)",
    icon: (
      <svg width="14" height="14" viewBox="0 0 14 14" fill="none" style={{ animation: "spin 1.5s linear infinite" }}>
        <path d="M12 7a5 5 0 11-2.5-4.33" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
      </svg>
    ),
  },
  completed: {
    label: "Completed",
    bg: "rgba(16, 185, 129, 0.08)", color: "var(--color-success)", border: "rgba(16, 185, 129, 0.2)",
    icon: (
      <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
        <circle cx="7" cy="7" r="5.5" stroke="currentColor" strokeWidth="1.4"/>
        <path d="M4.5 7l2 2 3.5-3.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
      </svg>
    ),
  },
  failed: {
    label: "Failed",
    bg: "rgba(239, 68, 68, 0.08)", color: "#f87171", border: "rgba(239, 68, 68, 0.2)",
    icon: (
      <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
        <circle cx="7" cy="7" r="5.5" stroke="currentColor" strokeWidth="1.4"/>
        <path d="M5 5l4 4M9 5l-4 4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/>
      </svg>
    ),
  },
};



// ── Main component ────────────────────────────────────────────────────────────
export default function ResultPanel({ taskId, onStatusChange }: Props) {
  const [data, setData]         = useState<TaskStatusResponse | null>(null);
  const [copied, setCopied]     = useState(false);
  const intervalRef             = useRef<number | null>(null);

  useEffect(() => {
    if (!taskId) return;
    setData(null);
    const poll = async () => {
      try {
        const res = await getTaskStatus(taskId);
        setData(res);
        onStatusChange(res.status);
        if (res.status === "completed" || res.status === "failed") {
          if (intervalRef.current) clearInterval(intervalRef.current);
        }
      } catch { /* keep polling */ }
    };
    poll();
    intervalRef.current = setInterval(poll, 3000);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [taskId]);

  if (!taskId || !data) return null;

  const cfg    = STATUS_CONFIG[data.status] || STATUS_CONFIG.pending;
  const output = data.result?.output;
  const isMarkdown = output && (output.includes("##") || output.includes("**") || output.includes("[PRODUCT]") || output.includes("- "));

  const handleCopy = () => {
    if (!output) return;
    navigator.clipboard.writeText(output);
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  };

  return (
    <div className="card animate-fade-in" style={{ display: "flex", flexDirection: "column", overflow: "hidden", height: 560 }}>

      {/* Status header */}
      <div style={{
        padding: "16px 24px", background: cfg.bg,
        borderBottom: `1px solid ${cfg.border}`,
        display: "flex", alignItems: "center", justifyContent: "space-between",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, color: cfg.color }}>
          {cfg.icon}
          <span style={{ fontSize: 13, fontWeight: 800, textTransform: "uppercase", letterSpacing: "0.05em" }}>{cfg.label}</span>
          {data.status === "running" && (
            <span style={{ width: 6, height: 6, borderRadius: "50%", background: cfg.color, display: "inline-block", animation: "live-dot 1.2s ease-in-out infinite" }} />
          )}
        </div>
        <span style={{ fontSize: 11, color: "var(--color-text-3)", fontFamily: "var(--font-mono)" }}>
          ID: {data.task_id.slice(0, 8)}…
        </span>
      </div>



      <div style={{ padding: "20px 24px", flex: 1, overflowY: "auto" }}>

        {/* Task echo */}
        <div style={{
          fontSize: 12.5, color: "var(--color-text-2)", padding: "10px 14px",
          background: "rgba(0, 0, 0, 0.03)", borderRadius: 10, marginBottom: 16,
          borderLeft: "3.5px solid var(--color-accent)", lineHeight: 1.5,
        }}>
          <span style={{ color: "var(--color-text-3)", marginRight: 6, fontWeight: 700, textTransform: "uppercase", fontSize: 10, letterSpacing: "0.03em" }}>Task:</span>
          {data.task}
        </div>

        {/* Error */}
        {data.status === "failed" && data.error && (
          <div style={{
            padding: "12px 16px", borderRadius: 10, marginBottom: 16,
            background: "rgba(239, 68, 68, 0.08)", border: "1px solid rgba(239, 68, 68, 0.2)",
            color: "#f87171", fontSize: 13, lineHeight: 1.5,
          }}>
            <strong style={{ color: "#fff" }}>Error: </strong>{data.error}
          </div>
        )}

        {/* Running skeleton */}
        {data.status === "running" && !output && (
          <div style={{ padding: "20px 0" }}>
            <div className="skeleton" style={{ height: 12, width: "85%", marginBottom: 12 }} />
            <div className="skeleton" style={{ height: 12, width: "70%", marginBottom: 12 }} />
            <div className="skeleton" style={{ height: 12, width: "78%", marginBottom: 12 }} />
            <div className="skeleton" style={{ height: 12, width: "60%", marginBottom: 24 }} />
            <p style={{ fontSize: 12, color: "var(--color-text-3)", textAlign: "center", fontWeight: 500 }}>
              Agent is working... watch the pipeline on the left ↑
            </p>
          </div>
        )}

        {/* Output */}
        {output && (
          <div style={{ borderRadius: 12, border: "1px solid var(--color-border)", overflow: "hidden" }}>
            {/* Output toolbar */}
            <div style={{
              padding: "10px 16px",
              display: "flex", alignItems: "center", justifyContent: "space-between",
              background: "rgba(0,0,0,0.02)", borderBottom: "1px solid var(--color-border)",
            }}>
              <span style={{ fontSize: 11, fontWeight: 700, color: "var(--color-text-2)", letterSpacing: "0.05em", textTransform: "uppercase" }}>
                Final Output Report
              </span>
              <button
                onClick={handleCopy}
                style={{
                  display: "flex", alignItems: "center", gap: 5,
                  padding: "5px 12px", borderRadius: 8,
                  border: "1px solid var(--color-border)", background: "rgba(0, 0, 0, 0.02)",
                  fontSize: 11, fontWeight: 700, color: copied ? "var(--color-success)" : "var(--color-text-2)",
                  cursor: "pointer", transition: "all 0.15s",
                }}
                onMouseEnter={e => {
                  if (!copied) {
                    (e.currentTarget as HTMLElement).style.borderColor = "var(--color-accent)";
                    (e.currentTarget as HTMLElement).style.color = "var(--color-accent)";
                  }
                }}
                onMouseLeave={e => {
                  if (!copied) {
                    (e.currentTarget as HTMLElement).style.borderColor = "var(--color-border)";
                    (e.currentTarget as HTMLElement).style.color = "var(--color-text-2)";
                  }
                }}
              >
                {copied ? (
                  <><svg width="11" height="11" viewBox="0 0 11 11" fill="none" style={{ stroke: "currentColor", marginRight: 2 }}><path d="M2 5.5l2 2 5-5" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/></svg> Copied</>
                ) : (
                  <><svg width="11" height="11" viewBox="0 0 11 11" fill="none"><rect x="1" y="3.5" width="6.5" height="7" rx="1.2" stroke="currentColor" strokeWidth="1.2"/><path d="M3.5 3.5V2.5a1 1 0 011-1h4.5a1 1 0 011 1v6.5a1 1 0 01-1 1H8" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/></svg> Copy</>
                )}
              </button>
            </div>

            {isMarkdown ? (
              <div
                className="report-content"
                style={{ padding: "18px 22px" }}
                dangerouslySetInnerHTML={{ __html: renderMarkdown(output) }}
              />
            ) : (
              <pre style={{
                padding: "18px 22px", margin: 0, fontSize: 13, lineHeight: 1.7,
                color: "var(--color-text)", whiteSpace: "pre-wrap", fontFamily: "var(--font-mono)",
                background: "#f8fafc",
              }}>
                {output}
              </pre>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
