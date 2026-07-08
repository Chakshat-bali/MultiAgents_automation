/**
 * CompetitiveDashboard.tsx — Professional light-mode redesign
 */
import React, { useEffect, useState } from "react";
import {
  type Company, type IntelReport,
  addCompany, deactivateCompany, getCompanies, getAllReports,
  getCompanyReports, triggerScanNow, deleteAllReports,
} from "../api/client";

// ── Helpers ───────────────────────────────────────────────────────────────────
function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-IN", {
    day: "numeric", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

function avatarColor(name: string) {
  return `hsl(${(name.charCodeAt(0) * 47) % 360}, 60%, 42%)`;
}

function renderReport(text: string): string {
  if (!text) return "";
  const clean = text.replace(/Signal level: (HIGH|MEDIUM|LOW)/gi, "");
  const TAG_RE = /(?:#+\s*)?(\[PRODUCT\]|\[FUNDING\]|\[HIRING\]|\[SENTIMENT\]|\[NEWS\]|OVERALL SIGNAL:|OVERALL SUMMARY:)/gi;
  const sections = clean.split(TAG_RE);
  let html = "";
  let tag = "";
  const COLORS: Record<string, { fg: string; bg: string }> = {
    PRODUCT:   { fg: "#4338ca", bg: "rgba(91,94,244,0.07)"  },
    FUNDING:   { fg: "#047857", bg: "rgba(5,150,105,0.07)"  },
    HIRING:    { fg: "#0369a1", bg: "rgba(3,105,161,0.07)"  },
    SENTIMENT: { fg: "#92400e", bg: "rgba(217,119,6,0.07)"  },
    NEWS:      { fg: "#b91c1c", bg: "rgba(220,38,38,0.06)"  },
  };
  sections.forEach(s => {
    s = s.trim();
    if (!s) return;
    const u = s.toUpperCase();
    if (u.match(/^\[(PRODUCT|FUNDING|HIRING|SENTIMENT|NEWS)\]$/)) { tag = u.slice(1,-1); return; }
    if (s.startsWith("OVERALL SIGNAL:") || s.startsWith("OVERALL SUMMARY:")) {
      tag = "OVERALL";
      return;
    }
    if (tag && tag !== "OVERALL") {
      const c = COLORS[tag] || { fg: "#475569", bg: "rgba(0,0,0,0.04)" };
      const badge = `<span style="display:inline-flex;align-items:center;padding:2px 10px;border-radius:20px;font-size:11px;font-weight:700;letter-spacing:.4px;background:${c.bg};color:${c.fg};border:1px solid ${c.fg}22;">${tag}</span>`;
      const items = s.split("\n").filter(l => l.trim() && l.trim() !== "###").map(l => {
        const line = l.trim().replace(/^[*#-]\s*/,"");
        return line ? `<li style="margin-bottom:.35rem;margin-left:1.25rem;line-height:1.65;color:#334155;list-style:disc;">${line}</li>` : "";
      }).filter(Boolean).join("");
      html += `<div style="margin-bottom:1rem;"><div style="margin-bottom:.4rem;">${badge}</div><ul style="margin:0;padding:0;">${items}</ul></div>`;
    } else if (tag === "OVERALL") {
      const line = s.trim().replace(/^(HIGH|MEDIUM|LOW)\s*[-—]\s*/i, "").replace(/^\*\*.*?\*\*\s*[-—]\s*/, "").replace(/^[-—]\s*/, "");
      html += `<div style="margin-top:1.25rem;padding:12px 16px;background:#f8fafc;border-left:4px solid #64748b;border-radius:0 8px 8px 0;font-size:12.5px;color:#475569;line-height:1.6;"><strong>Summary:</strong> ${line}</div>`;
    } else if (!tag) {
      html += `<p style="color:#64748b;font-style:italic;font-size:.85rem;margin-bottom:.75rem;">${s}</p>`;
    }
  });
  return html.replace(/\*\*(.+?)\*\*/g,"<strong>$1</strong>").replace(/\*(.+?)\*/g,"<em>$1</em>");
}

// ── StatCard ──────────────────────────────────────────────────────────────────
function StatCard({ value, label, icon }: { value: string|number; label: string; icon: React.ReactNode }) {
  return (
    <div style={{ background:"rgba(255,255,255,0.15)",backdropFilter:"blur(8px)",borderRadius:12,padding:"14px 20px",minWidth:110,border:"1px solid rgba(255,255,255,0.25)" }}>
      <div style={{ display:"flex",alignItems:"center",gap:6,marginBottom:4 }}>
        <span style={{ color:"rgba(255,255,255,0.7)",fontSize:13 }}>{icon}</span>
      </div>
      <div style={{ fontSize:24,fontWeight:800,color:"#fff",lineHeight:1 }}>{value}</div>
      <div style={{ fontSize:11,color:"rgba(255,255,255,0.7)",marginTop:3 }}>{label}</div>
    </div>
  );
}

// ── CompanyCard ───────────────────────────────────────────────────────────────
function CompanyCard({ company, onSelect, onDeactivate, onScanNow, isSelected, isScanning }: {
  company: Company; isSelected: boolean; isScanning: boolean;
  onSelect: (c: Company) => void; onDeactivate: (id: string) => void; onScanNow: (id: string) => void;
}) {
  const ac = avatarColor(company.name);
  return (
    <div
      className="company-card"
      onClick={() => onSelect(company)}
      style={{
        padding: "12px 14px", borderRadius: 12, cursor: "pointer", transition: "all .15s",
        background: isSelected ? "#f0f1fe" : "#fff",
        border: `1.5px solid ${isSelected ? "#5b5ef4" : "#e4e8f0"}`,
        boxShadow: isSelected ? "0 2px 10px rgba(91,94,244,0.1)" : "0 1px 3px rgba(15,23,42,0.05)",
      }}
    >
      <div style={{ display:"flex",alignItems:"flex-start",gap:10 }}>
        <div style={{ width:36,height:36,borderRadius:10,display:"flex",alignItems:"center",justifyContent:"center",fontWeight:900,fontSize:15,flexShrink:0,background:`${ac}14`,color:ac,border:`1.5px solid ${ac}2e` }}>
          {company.name[0].toUpperCase()}
        </div>
        <div style={{ flex:1,minWidth:0 }}>
          <div style={{ fontWeight:700,fontSize:13,color:"#0f172a",overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap" }}>{company.name}</div>
          {company.description && <div style={{ fontSize:11,color:"#94a3b8",marginTop:2,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap" }}>{company.description}</div>}
          <div style={{ fontSize:11,color:"#94a3b8",marginTop:3 }}>{company.report_count} report{company.report_count !== 1?"s":""}</div>
        </div>
        <div style={{ display:"flex",flexDirection:"column",gap:4,flexShrink:0 }}>
          <button onClick={e=>{e.stopPropagation();onScanNow(company.id);}} disabled={isScanning}
            style={{ padding:"4px 10px",borderRadius:7,fontSize:11,fontWeight:700,border:"none",cursor:isScanning?"not-allowed":"pointer",background:isScanning?"#e0e7ff":"#5b5ef4",color:"#fff",display:"flex",alignItems:"center",gap:4,transition:"background .15s" }}>
            {isScanning ? <><span style={{ width:9,height:9,border:"2px solid rgba(255,255,255,0.4)",borderTop:"2px solid #fff",borderRadius:"50%",display:"inline-block",animation:"spin .7s linear infinite" }} />Scanning</> : "⚡ Scan"}
          </button>
          <button onClick={e=>{e.stopPropagation();onDeactivate(company.id);}}
            style={{ padding:"4px 10px",borderRadius:7,fontSize:11,fontWeight:600,border:"1px solid #e4e8f0",cursor:"pointer",background:"#f7f8fc",color:"#94a3b8",transition:"all .15s" }}>
            ✕ Remove
          </button>
        </div>
      </div>
    </div>
  );
}

// ── ReportCard ────────────────────────────────────────────────────────────────
function ReportCard({ report }: { report: IntelReport }) {
  const [expanded, setExpanded] = useState(false);
  const isLong = !!(report.report_text && report.report_text.length > 450);
  const preview = isLong && !expanded ? report.report_text!.slice(0, 450) + "…" : report.report_text;

  return (
    <div className="animate-fade-in report-card" style={{ borderRadius:14,overflow:"hidden",border:"1.5px solid #e4e8f0",background:"#fff",boxShadow:"0 2px 8px rgba(15,23,42,0.06)",marginBottom:12 }}>
      <div style={{ padding:"12px 16px",display:"flex",alignItems:"center",justifyContent:"space-between",gap:12,background:"#f8fafc",borderBottom:"1.5px solid #e4e8f0" }}>
        <div style={{ display:"flex",alignItems:"center",gap:8,flexWrap:"wrap" }}>
          {report.company_name && <span style={{ fontWeight:700,fontSize:13,color:"#0f172a" }}>{report.company_name}</span>}
          {report.slack_sent && (
            <span style={{ fontSize:10,padding:"2px 8px",borderRadius:20,background:"rgba(5,150,105,0.09)",color:"#047857",border:"1px solid rgba(5,150,105,0.18)",fontWeight:700 }}>
              ✓ Slack
            </span>
          )}
        </div>
        <div style={{ textAlign:"right",flexShrink:0 }}>
          <div style={{ fontSize:11,color:"#64748b" }}>{formatDate(report.created_at)}</div>
        </div>
      </div>
      <div style={{ padding:"16px 18px" }}>
        {report.report_text ? (
          <div className="report-content" style={{ fontSize:13,lineHeight:1.75 }}
            dangerouslySetInnerHTML={{ __html: renderReport(preview || "") }} />
        ) : (
          <p style={{ fontSize:13,fontStyle:"italic",color:"#94a3b8",margin:0 }}>No report content yet.</p>
        )}
        {isLong && (
          <button onClick={() => setExpanded(!expanded)}
            style={{ marginTop:10,fontSize:12,fontWeight:700,color:"#5b5ef4",background:"none",border:"none",cursor:"pointer",padding:0,display:"flex",alignItems:"center",gap:4 }}>
            {expanded ? "↑ Show less" : "↓ Read full report"}
          </button>
        )}
      </div>
    </div>
  );
}


// ── AddCompanyForm ────────────────────────────────────────────────────────────
function AddCompanyForm({ onAdd }: { onAdd: () => void }) {
  const [form, setForm]       = useState({ name: "", description: "" });
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState("");

  const handleSubmit = async () => {
    if (!form.name.trim()) { setError("Company name is required"); return; }
    setLoading(true); setError("");
    try {
      await addCompany({ name: form.name.trim(), description: form.description.trim() || undefined });
      setForm({ name: "", description: "" });
      onAdd();
    } catch { setError("Failed to add company. Is the API running?"); }
    finally { setLoading(false); }
  };

  const inp: React.CSSProperties = { width:"100%",background:"#fafbfe",border:"1.5px solid #e4e8f0",borderRadius:9,padding:"9px 12px",fontSize:13,color:"#0f172a",outline:"none",fontFamily:"inherit",boxSizing:"border-box",transition:"border-color .15s" };

  return (
    <div style={{ background:"#fff",border:"1px solid #e4e8f0",borderRadius:14,padding:"16px 18px",boxShadow:"0 1px 4px rgba(15,23,42,0.05)" }}>
      <h3 style={{ fontSize:13,fontWeight:700,color:"#0f172a",margin:"0 0 12px",display:"flex",alignItems:"center",gap:6 }}>
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M7 2v10M2 7h10" stroke="#5b5ef4" strokeWidth="1.6" strokeLinecap="round"/></svg>
        Track New Competitor
      </h3>
      <div style={{ display:"flex",flexDirection:"column",gap:8 }}>
        <input style={inp} placeholder="Company name * (e.g. Salesforce)" value={form.name}
          onChange={e=>setForm(f=>({...f,name:e.target.value}))}
          onFocus={e=>(e.target.style.borderColor="#5b5ef4")} onBlur={e=>(e.target.style.borderColor="#e4e8f0")}
          onKeyDown={e=>e.key==="Enter"&&handleSubmit()} />
        <input style={inp} placeholder="Brief description (optional)" value={form.description}
          onChange={e=>setForm(f=>({...f,description:e.target.value}))}
          onFocus={e=>(e.target.style.borderColor="#5b5ef4")} onBlur={e=>(e.target.style.borderColor="#e4e8f0")}
          onKeyDown={e=>e.key==="Enter"&&handleSubmit()} />
        {error && <p style={{ fontSize:12,color:"#b91c1c",margin:0 }}>{error}</p>}
        <button onClick={handleSubmit} disabled={loading}
          style={{ padding:"10px",borderRadius:9,fontSize:13,fontWeight:700,border:"none",cursor:loading?"not-allowed":"pointer",background:loading?"#c7c9f9":"linear-gradient(135deg,#5b5ef4,#7c3aed)",color:"#fff",boxShadow:loading?"none":"0 2px 8px rgba(91,94,244,0.28)",transition:"all .15s" }}>
          {loading ? "Adding…" : "Add Company"}
        </button>
      </div>
    </div>
  );
}



// ── Main Component ────────────────────────────────────────────────────────────
export default function CompetitiveDashboard() {
  const [companies, setCompanies]           = useState<Company[]>([]);
  const [reports, setReports]               = useState<IntelReport[]>([]);
  const [selectedCompany, setSelected]      = useState<Company | null>(null);
  const [companyReports, setCompanyReports] = useState<IntelReport[]>([]);
  const [loading, setLoading]               = useState(true);   // only true on first load
  const [toast, setToast]                   = useState("");
  const [clearing, setClearing]             = useState(false);
  const [scanningId, setScanningId]         = useState<string | null>(null);
  const selectedRef                         = React.useRef<Company | null>(null);
  const showToast = (msg: string) => { setToast(msg); setTimeout(() => setToast(""), 3500); };

  // Keep a ref to the selected company so the polling closure always sees the latest value
  useEffect(() => { selectedRef.current = selectedCompany; }, [selectedCompany]);

  // Load companies + global reports. Pass silent=true to skip the skeleton flash on polls.
  const loadData = async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const [c, r] = await Promise.all([getCompanies(), getAllReports()]);
      setCompanies(c);
      setReports(r);
      // If a company is selected, silently refresh its specific reports too
      const sel = selectedRef.current;
      if (sel) {
        try {
          const cr = await getCompanyReports(sel.id);
          setCompanyReports(cr);
        } catch { /* non-critical, ignore */ }
      }
    } catch { if (!silent) showToast("Failed to load data"); }
    finally { if (!silent) setLoading(false); }
  };

  useEffect(() => {
    loadData();                                         // first load — show skeleton
    const t1 = setInterval(() => loadData(true), 6000); // background poll — silent, no skeleton
    return () => { clearInterval(t1); };
  }, []);

  const handleSelect = async (c: Company) => {
    setSelected(c);
    try { setCompanyReports(await getCompanyReports(c.id)); }
    catch { showToast("Could not load reports."); }
  };

  const handleDeactivate = async (id: string) => {
    if (!confirm("Stop tracking this company? Reports are preserved.")) return;
    try {
      await deactivateCompany(id);
      showToast("Company removed");
      if (selectedCompany?.id === id) { setSelected(null); selectedRef.current = null; }
      loadData(true);
    } catch { showToast("Failed to remove"); }
  };

  const handleScanNow = async (id: string) => {
    setScanningId(id);
    const company = companies.find(c => c.id === id);
    if (company) await handleSelect(company);
    
    // Track the report count before we start the scan
    const initialReportCount = company?.report_count || 0;

    try {
      await triggerScanNow(id);
      showToast("⚡ Scan triggered — report will appear automatically.");
      
      let polls = 0;
      const scanPoll = setInterval(async () => {
        polls++;
        
        try {
          // Check if scan has saved the new report to DB
          const freshCompanies = await getCompanies();
          const freshCompany = freshCompanies.find(c => c.id === id);
          if (freshCompany && freshCompany.report_count > initialReportCount) {
            clearInterval(scanPoll);
            setScanningId(null);
            await loadData(true);
            showToast("✅ Scan complete — report updated!");
            return;
          }
        } catch { /* silent retry */ }

        await loadData(true);
        if (polls >= 36) { clearInterval(scanPoll); setScanningId(null); }
      }, 5000);
    } catch { showToast("Failed to trigger scan"); setScanningId(null); }
  };

  const handleClearReports = async () => {
    if (!confirm("Delete ALL generated reports? Companies stay tracked.")) return;
    setClearing(true);
    try {
      const res = await deleteAllReports();
      showToast(`Cleared ${res.count} report(s).`);
      setReports([]); setCompanyReports([]); if (selectedCompany) setSelected(null); loadData();
    } catch { showToast("Failed to clear reports."); }
    finally { setClearing(false); }
  };

  const displayed  = selectedCompany ? companyReports : reports;

  return (
    <div style={{ fontFamily:"'Inter',sans-serif" }}>
      <style>{`@keyframes spin{to{transform:rotate(360deg)}} @keyframes fadeIn{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}} .animate-fade-in{animation:fadeIn .25s ease-out forwards}`}</style>

      {/* Toast */}
      {toast && (
        <div style={{ position:"fixed",top:20,right:20,zIndex:9999,padding:"12px 18px",borderRadius:12,background:"#1e293b",color:"#f8fafc",fontSize:13,fontWeight:500,boxShadow:"0 8px 24px rgba(0,0,0,0.18)",animation:"fadeIn .2s ease-out" }}>
          {toast}
        </div>
      )}

      {/* Hero header */}
      <div style={{ background:"linear-gradient(135deg,#5b5ef4 0%,#7c3aed 100%)",borderRadius:20,padding:"28px 32px",marginBottom:24,boxShadow:"0 8px 32px rgba(91,94,244,0.22)",position:"relative",overflow:"hidden" }}>
        <div style={{ position:"absolute",top:-50,right:-50,width:220,height:220,background:"rgba(255,255,255,0.05)",borderRadius:"50%",pointerEvents:"none" }} />
        <div style={{ position:"absolute",bottom:-70,left:"35%",width:180,height:180,background:"rgba(255,255,255,0.04)",borderRadius:"50%",pointerEvents:"none" }} />
        <div style={{ position:"relative" }}>
          <h2 style={{ fontSize:22,fontWeight:800,color:"#fff",margin:"0 0 6px",display:"flex",alignItems:"center",gap:8 }}>
            <svg width="22" height="22" viewBox="0 0 22 22" fill="none"><circle cx="10" cy="10" r="8" stroke="white" strokeWidth="1.8"/><path d="M16.5 16.5L21 21" stroke="white" strokeWidth="2" strokeLinecap="round"/></svg>
            Competitive Intelligence
          </h2>
          <p style={{ color:"rgba(255,255,255,0.75)",fontSize:13,margin:"0 0 20px",lineHeight:1.6 }}>
            Automated competitor monitoring — news, funding, reviews &amp; hiring signals.<br/>
            Runs every <strong style={{ color:"#e0e7ff" }}>Monday 8AM IST</strong> · delivers to Slack &amp; Email.
          </p>
          <div style={{ display:"flex",gap:10,flexWrap:"wrap" }}>
            <StatCard value={companies.length} label="tracked" icon={<svg width="13" height="13" viewBox="0 0 13 13" fill="none"><rect x="1" y="5" width="11" height="7" rx="1.5" stroke="white" strokeWidth="1.3"/><path d="M4 5V3.5a3 3 0 016 0V5" stroke="white" strokeWidth="1.3"/></svg>} />
            <StatCard value={reports.length} label="reports" icon={<svg width="13" height="13" viewBox="0 0 13 13" fill="none"><rect x="2" y="1" width="9" height="11" rx="1.5" stroke="white" strokeWidth="1.3"/><path d="M4 4.5h5M4 6.5h5M4 8.5h3" stroke="white" strokeWidth="1.2" strokeLinecap="round"/></svg>} />
          </div>
        </div>
      </div>

      {/* Main grid */}
      <div style={{ display:"grid",gridTemplateColumns:"300px 1fr",gap:20,alignItems:"start" }}>

        {/* Left column */}
        <div style={{ display:"flex",flexDirection:"column",gap:14 }}>
          <AddCompanyForm onAdd={loadData} />

          <div>
            <div style={{ display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:8 }}>
              <h3 style={{ fontSize:11,fontWeight:700,color:"#64748b",margin:0,textTransform:"uppercase",letterSpacing:".5px" }}>
                Tracked ({companies.length})
              </h3>
            </div>

            {loading ? (
              <div style={{ display:"flex",flexDirection:"column",gap:8 }}>
                {[1,2,3].map(i=><div key={i} className="skeleton" style={{ height:72,borderRadius:12 }} />)}
              </div>
            ) : companies.length === 0 ? (
              <div style={{ borderRadius:14,padding:"28px 16px",textAlign:"center",border:"1.5px dashed #e4e8f0",background:"#fff" }}>
                <div style={{ fontSize:28,marginBottom:8 }}>🏢</div>
                <p style={{ color:"#94a3b8",fontSize:13,margin:0 }}>No companies tracked yet.</p>
                <p style={{ color:"#c1c9d4",fontSize:12,marginTop:4 }}>Add one above to get started.</p>
              </div>
            ) : (
              <div style={{ display:"flex",flexDirection:"column",gap:6 }}>
                {companies.map(c => (
                  <CompanyCard key={c.id} company={c} isSelected={selectedCompany?.id===c.id}
                    isScanning={scanningId===c.id} onSelect={handleSelect}
                    onDeactivate={handleDeactivate} onScanNow={handleScanNow} />
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Right column */}
        <div style={{ display:"flex",flexDirection:"column",gap:14 }}>

          {/* Toolbar */}
          <div style={{ display:"flex",alignItems:"center",justifyContent:"space-between",flexWrap:"wrap",gap:10 }}>
            <h3 style={{ fontSize:13,fontWeight:700,color:"#0f172a",margin:0 }}>
              {selectedCompany ? (
                <>Reports for <span style={{ color:"#5b5ef4" }}>{selectedCompany.name}</span>
                  <button onClick={()=>setSelected(null)} style={{ marginLeft:8,fontSize:12,color:"#94a3b8",background:"none",border:"none",cursor:"pointer",fontWeight:400 }}>(clear)</button>
                </>
              ) : "All Reports"}
            </h3>

            <div style={{ display:"flex",alignItems:"center",gap:8,flexWrap:"wrap" }}>
              {reports.length > 0 && (
                <button onClick={handleClearReports} disabled={clearing}
                  style={{ padding:"6px 12px",borderRadius:9,fontSize:11,fontWeight:700,border:"1.5px solid #fecaca",cursor:clearing?"not-allowed":"pointer",background:clearing?"#fef2f2":"#fff",color:"#b91c1c",display:"flex",alignItems:"center",gap:5,transition:"all .15s" }}>
                  {clearing ? "Clearing…" : "🗑 Clear Reports"}
                </button>
              )}
            </div>
          </div>

          {/* Reports */}
          {loading ? (
            <div style={{ display:"flex",flexDirection:"column",gap:12 }}>
              {[1,2].map(i=><div key={i} className="skeleton" style={{ height:140,borderRadius:14 }} />)}
            </div>
          ) : displayed.length === 0 ? (
            <div style={{ borderRadius:14,padding:"48px 24px",textAlign:"center",border:"1.5px dashed #e4e8f0",background:"#fff" }}>
              <div style={{ fontSize:36,marginBottom:10 }}>📊</div>
              <p style={{ fontWeight:600,fontSize:14,color:"#94a3b8",margin:"0 0 6px" }}>No reports yet</p>
              <p style={{ fontSize:12,color:"#c1c9d4",margin:0,lineHeight:1.6 }}>
                {selectedCompany
                  ? <>Click <strong>⚡ Scan</strong> to generate the first report for <strong>{selectedCompany.name}</strong>.</>
                  : "Add companies and trigger a scan, or wait for Monday's automated run."}
              </p>
            </div>
          ) : (
            <div>{displayed.map(r=><ReportCard key={r.id} report={r} />)}</div>
          )}
        </div>
      </div>
    </div>
  );
}
