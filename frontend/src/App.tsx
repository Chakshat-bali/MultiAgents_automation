import { useState } from "react";
import TaskInput from "./components/TaskInput";
import AgentLog from "./components/AgentLog";
import ResultPanel from "./components/ResultPanel";
import CompetitiveDashboard from "./components/CompetitiveDashboard";

const HEADER_TEXT = {
  automator: {
    title: "AI Research Automator",
    subtitle: "Agents · LangGraph · FAISS",
    desc: "Describe any research task. The agent pipeline breaks it down, gathers evidence, and delivers a polished report.",
  },
  competitive: {
    title: "Competitive Intelligence Platform",
    subtitle: "Automated Tracking · Market Scans · Competitor Signals",
    desc: "Track target competitors, monitor market events, and analyze detailed business, product, and funding changes.",
  }
};

export default function App() {
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
  const [taskStatus, setTaskStatus]     = useState<string>("idle");
  const [activeTab, setActiveTab]       = useState<"automator" | "competitive">("automator");

  const handleTaskSubmitted = (taskId: string) => {
    setActiveTaskId(taskId);
    setTaskStatus("pending");
  };

  const currentHeader = HEADER_TEXT[activeTab];

  return (
    <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column", fontFamily: "'Inter', sans-serif" }}>

      {/* ── Main Content Area ── */}
      <main style={{
        flex: 1,
        minHeight: "100vh",
        padding: "48px 24px 80px",
      }}>
        <div style={{ maxWidth: 1320, margin: "0 auto", display: "flex", flexDirection: "column", gap: 28 }}>

          {/* Page title */}
          <div style={{ textAlign: "center", marginBottom: 8 }}>
            <h1 style={{
              fontSize: 36, fontWeight: 900,
              background: "linear-gradient(to right, #0f172a, #334155, #475569)",
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
              margin: "0 0 8px", letterSpacing: "-0.03em",
            }}>
              {currentHeader.title}
            </h1>
            <div style={{
              fontSize: 11.5, fontWeight: 700,
              color: "var(--color-accent)", textTransform: "uppercase",
              letterSpacing: "0.15em", margin: "0 0 14px",
            }}>
              {currentHeader.subtitle}
            </div>
            <p style={{
              fontSize: 14.5, color: "var(--color-text-2)",
              margin: "0 auto", lineHeight: 1.65, maxWidth: 720,
            }}>
              {currentHeader.desc}
            </p>

            {/* Centered Segmented Tabs */}
            <div style={{
              display: "inline-flex",
              background: "rgba(0, 0, 0, 0.03)",
              border: "1px solid var(--color-border)",
              borderRadius: 14,
              padding: "4px",
              marginTop: 40,
            }}>
              <button
                onClick={() => setActiveTab("automator")}
                style={{
                  display: "flex", alignItems: "center", gap: 8,
                  padding: "10px 24px", borderRadius: 10,
                  border: "none", fontSize: 13.5, fontWeight: activeTab === "automator" ? 700 : 500,
                  background: activeTab === "automator" ? "var(--color-surface)" : "transparent",
                  color: activeTab === "automator" ? "var(--color-accent)" : "var(--color-text-2)",
                  boxShadow: activeTab === "automator" ? "var(--shadow-sm)" : "none",
                  cursor: "pointer", transition: "all 0.2s ease",
                }}
              >
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="m21.64 3.64-1.28-1.28a1.21 1.21 0 0 0-1.72 0L2.36 18.64a1.21 1.21 0 0 0 0 1.72l1.28 1.28a1.21 1.21 0 0 0 1.72 0L21.64 5.36a1.21 1.21 0 0 0 0-1.72Z"/>
                  <path d="m14 7 3 3"/>
                </svg>
                Research Automator
              </button>

              <button
                onClick={() => setActiveTab("competitive")}
                style={{
                  display: "flex", alignItems: "center", gap: 8,
                  padding: "10px 24px", borderRadius: 10,
                  border: "none", fontSize: 13.5, fontWeight: activeTab === "competitive" ? 700 : 500,
                  background: activeTab === "competitive" ? "var(--color-surface)" : "transparent",
                  color: activeTab === "competitive" ? "var(--color-accent)" : "var(--color-text-2)",
                  boxShadow: activeTab === "competitive" ? "var(--shadow-sm)" : "none",
                  cursor: "pointer", transition: "all 0.2s ease",
                }}
              >
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M3 3v18h18"/>
                  <path d="m19 9-5 5-4-4-3 3"/>
                </svg>
                Competitive Intelligence
              </button>
            </div>
          </div>

          {activeTab === "automator" ? (
            <>
              <TaskInput onTaskSubmitted={handleTaskSubmitted} />

              {activeTaskId && (
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24, alignItems: "stretch" }}>
                  <AgentLog taskId={activeTaskId} status={taskStatus} />
                  <ResultPanel taskId={activeTaskId} onStatusChange={setTaskStatus} />
                </div>
              )}

              {activeTaskId && (taskStatus === "completed" || taskStatus === "failed") && (
                <div style={{ textAlign: "center", paddingTop: 8 }}>
                  <button
                    onClick={() => { setActiveTaskId(null); setTaskStatus("idle"); }}
                    style={{
                      padding: "10px 24px", borderRadius: 10, fontSize: 13, fontWeight: 600,
                      border: "1px solid var(--color-border)", background: "rgba(255, 255, 255, 0.03)",
                      color: "var(--color-text)", cursor: "pointer", transition: "all 0.2s",
                      boxShadow: "var(--shadow-sm)",
                    }}
                    onMouseEnter={e => { (e.target as HTMLElement).style.borderColor = "var(--color-accent)"; (e.target as HTMLElement).style.background = "rgba(99, 102, 241, 0.08)"; }}
                    onMouseLeave={e => { (e.target as HTMLElement).style.borderColor = "var(--color-border)"; (e.target as HTMLElement).style.background = "rgba(255, 255, 255, 0.03)"; }}
                  >
                    ← Run Another Task
                  </button>
                </div>
              )}
            </>
          ) : (
            <div className="animate-fade-in">
              <CompetitiveDashboard />
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
