import { useEffect, useRef, useState } from "react";
import { createStepSocket } from "./../api/client";
import type { AgentStep } from "../api/client";

interface Props {
  taskId: string | null;
  status: string;
}

const NODE_META: Record<string, { color: string; bg: string; border: string; icon: React.ReactNode }> = {
  MEMORY_LOAD: {
    color: "#a78bfa", bg: "rgba(167, 139, 250, 0.12)", border: "rgba(167, 139, 250, 0.25)",
    icon: (
      <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
        <path d="M6 1a4.5 4.5 0 100 9A4.5 4.5 0 006 1z" stroke="currentColor" strokeWidth="1.3"/>
        <path d="M4 6h4M6 4v4" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
      </svg>
    ),
  },
  PLAN: {
    color: "#60a5fa", bg: "rgba(96, 165, 250, 0.12)", border: "rgba(96, 165, 250, 0.25)",
    icon: (
      <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
        <rect x="1" y="1" width="10" height="10" rx="2" stroke="currentColor" strokeWidth="1.3"/>
        <path d="M3.5 4.5h5M3.5 6.5h3.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
      </svg>
    ),
  },
  ROUTE: {
    color: "#fbbf24", bg: "rgba(251, 191, 36, 0.12)", border: "rgba(251, 191, 36, 0.25)",
    icon: (
      <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
        <path d="M2 6h8M7 3l3 3-3 3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
      </svg>
    ),
  },
  RESEARCHER: {
    color: "#34d399", bg: "rgba(52, 211, 153, 0.12)", border: "rgba(52, 211, 153, 0.25)",
    icon: (
      <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
        <circle cx="5.5" cy="5.5" r="3.5" stroke="currentColor" strokeWidth="1.3"/>
        <path d="M8.5 8.5l2.5 2.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
      </svg>
    ),
  },
  SUMMARISER: {
    color: "#22d3ee", bg: "rgba(34, 211, 238, 0.12)", border: "rgba(34, 211, 238, 0.25)",
    icon: (
      <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
        <path d="M1.5 3h9M1.5 6h6M1.5 9h7.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
      </svg>
    ),
  },
  WRITER: {
    color: "#c084fc", bg: "rgba(192, 132, 252, 0.12)", border: "rgba(192, 132, 252, 0.25)",
    icon: (
      <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
        <path d="M2 9l1.5-1.5L9 2l1.5 1.5L5 9 2 10l0-1z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round"/>
      </svg>
    ),
  },
  VALIDATE: {
    color: "#f87171", bg: "rgba(248, 113, 113, 0.12)", border: "rgba(248, 113, 113, 0.25)",
    icon: (
      <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
        <path d="M2.5 6.5L5 9l5-6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
      </svg>
    ),
  },
};

export default function AgentLog({ taskId }: Props) {
  const [steps, setSteps]       = useState<AgentStep[]>([]);
  const [wsStatus, setWsStatus] = useState<"idle" | "connected" | "closed">("idle");
  const wsRef     = useRef<WebSocket | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setSteps([]);
    if (!taskId) return;
    setWsStatus("connected");
    const ws = createStepSocket(taskId);
    wsRef.current = ws;
    ws.onmessage = event => {
      const msg = JSON.parse(event.data);
      if (msg.type === "step")                            setSteps(prev => [...prev, msg.data as AgentStep]);
      else if (msg.type === "complete" || msg.type === "error") { setWsStatus("closed"); ws.close(); }
    };
    ws.onerror = () => setWsStatus("closed");
    ws.onclose = () => setWsStatus("closed");
    return () => { ws.close(); wsRef.current = null; };
  }, [taskId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [steps]);

  if (!taskId) return null;

  const isLive     = wsStatus === "connected";
  const isDone     = wsStatus === "closed";

  return (
    <div className="card animate-fade-in" style={{ display: "flex", flexDirection: "column", overflow: "hidden", height: 560 }}>

      {/* Card header */}
      <div style={{
        padding: "18px 24px", borderBottom: "1px solid var(--color-border)",
        display: "flex", alignItems: "center", justifyContent: "space-between",
        background: "rgba(0, 0, 0, 0.1)",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{
            width: 34, height: 34, borderRadius: 10,
            background: "linear-gradient(135deg, var(--color-accent), var(--color-accent-2))",
            display: "flex", alignItems: "center", justifyContent: "center",
            boxShadow: "0 4px 12px rgba(99, 102, 241, 0.3)",
          }}>
            <svg width="16" height="16" viewBox="0 0 15 15" fill="none">
              <path d="M7.5 1L13 4V11L7.5 14L2 11V4L7.5 1Z" stroke="white" strokeWidth="1.4" strokeLinejoin="round"/>
              <circle cx="7.5" cy="7.5" r="2" fill="white"/>
            </svg>
          </div>
          <div>
            <div style={{ fontSize: 14, fontWeight: 800, color: "#fff", letterSpacing: "-0.2px" }}>Agent Pipeline</div>
            <div style={{ fontSize: 11, color: "var(--color-text-2)", marginTop: 1 }}>{steps.length} step{steps.length !== 1 ? "s" : ""}</div>
          </div>
        </div>

        {/* Status badge */}
        <div style={{
          display: "flex", alignItems: "center", gap: 6,
          padding: "5px 12px", borderRadius: 20,
          fontSize: 10, fontWeight: 700, letterSpacing: "0.05em",
          background: isLive ? "rgba(16, 185, 129, 0.08)" : isDone ? "rgba(99, 102, 241, 0.08)" : "rgba(0, 0, 0, 0.03)",
          color: isLive ? "var(--color-success)" : isDone ? "var(--color-accent)" : "var(--color-text-2)",
          border: `1px solid ${isLive ? "rgba(16, 185, 129, 0.2)" : isDone ? "rgba(99, 102, 241, 0.2)" : "var(--color-border)"}`,
        }}>
          {isLive ? (
            <><span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--color-success)", display: "inline-block", animation: "live-dot 1.6s ease-in-out infinite" }} /> LIVE</>
          ) : isDone ? (
            <><svg width="10" height="10" viewBox="0 0 10 10" fill="none" style={{ stroke: "currentColor", marginRight: 2 }}><path d="M2 5.5l2 2 4-4" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/></svg> DONE</>
          ) : (
            "IDLE"
          )}
        </div>
      </div>

      {/* Step list */}
      <div style={{ flex: 1, overflowY: "auto", padding: "16px 20px", position: "relative" }}>
        {/* Timeline connector line */}
        {steps.length > 0 && (
          <div style={{
            position: "absolute",
            left: 27,
            top: 24,
            bottom: 24,
            width: 2,
            background: "linear-gradient(to bottom, var(--color-accent) 0%, var(--color-accent-2) 100%)",
            opacity: 0.2,
            zIndex: 0,
          }} />
        )}

        {steps.length === 0 ? (
          <div style={{ padding: "36px 0", display: "flex", flexDirection: "column", gap: 10, alignItems: "center" }}>
            <div className="skeleton" style={{ width: 220, height: 12 }} />
            <div className="skeleton" style={{ width: 170, height: 12 }} />
            <div className="skeleton" style={{ width: 195, height: 12 }} />
            <p style={{ fontSize: 13, color: "var(--color-text-2)", marginTop: 12, fontWeight: 500 }}>Waiting for agent to start...</p>
          </div>
        ) : (
          steps.map((step, i) => {
            const meta  = NODE_META[step.node_name] || { color: "var(--color-text-2)", bg: "rgba(0,0,0,0.02)", border: "var(--color-border)", icon: "⚙" };
            const isNew = i === steps.length - 1 && isLive;
            return (
              <div
                key={i}
                className={isNew ? "animate-fade-in" : ""}
                style={{
                  display: "flex", alignItems: "flex-start", gap: 14,
                  padding: "10px 0", borderRadius: 9, marginBottom: 4,
                  position: "relative",
                  zIndex: 1,
                }}
              >
                {/* Timeline node dot — green when done, pulsing accent when live, outline otherwise */}
                <div style={{
                  width: 16, height: 16, borderRadius: "50%",
                  background: isNew
                    ? "var(--color-accent)"
                    : "var(--color-success)",
                  border: isNew
                    ? "3px solid rgba(99, 102, 241, 0.3)"
                    : "2px solid rgba(16, 185, 129, 0.4)",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  flexShrink: 0, marginTop: 4, zIndex: 2,
                  boxShadow: isNew ? "0 0 10px var(--color-accent)" : "0 0 6px rgba(16, 185, 129, 0.35)",
                  transition: "background 0.3s, box-shadow 0.3s",
                }} />

                {/* Node badge */}
                <span style={{
                  display: "inline-flex", alignItems: "center", gap: 4,
                  padding: "3px 10px", borderRadius: 8, flexShrink: 0,
                  fontSize: 10, fontWeight: 700, letterSpacing: "0.05em",
                  background: meta.bg, color: meta.color, border: `1px solid ${meta.border}`,
                  marginTop: 1,
                }}>
                  {meta.icon}
                  {step.node_name}
                </span>

                {/* Description */}
                <span style={{ flex: 1, fontSize: 13, color: isNew ? "var(--color-text)" : "var(--color-text-2)", lineHeight: 1.5, paddingTop: 2, transition: "color 0.2s" }}>
                  {step.description}
                </span>


              </div>
            );
          })
        )}
      </div>

      {/* Progress bar */}
      {isLive && (
        <div style={{ height: 2, background: "rgba(255,255,255,0.05)", overflow: "hidden", flexShrink: 0 }}>
          <div style={{
            height: "100%",
            background: "linear-gradient(90deg, var(--color-accent), var(--color-accent-2))",
            width: `${Math.min(steps.length * 14, 90)}%`,
            transition: "width 0.5s ease",
            borderRadius: 2,
            boxShadow: "0 0 8px var(--color-accent)",
          }} />
        </div>
      )}

      {isDone && steps.length > 0 && (
        <div style={{
          padding: "12px 24px", borderTop: "1px solid var(--color-border)",
          fontSize: 12, color: "var(--color-success)", fontWeight: 700,
          display: "flex", alignItems: "center", gap: 8, background: "rgba(16, 185, 129, 0.03)",
        }}>
          <svg width="14" height="14" viewBox="0 0 13 13" fill="none">
            <circle cx="6.5" cy="6.5" r="5.5" stroke="var(--color-success)" strokeWidth="1.3"/>
            <path d="M4 6.5l2 2 3.5-3.5" stroke="var(--color-success)" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
          All {steps.length} steps completed
        </div>
      )}
    </div>
  );
}
