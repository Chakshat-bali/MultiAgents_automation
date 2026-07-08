import axios from "axios";

const BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export const api = axios.create({
  baseURL: BASE_URL,
  headers: { "Content-Type": "application/json" },
});

export interface TaskSubmitRequest {
  task: string;
  output_format?: "markdown" | "json" | "bullet" | "text";
  context?: string;
}

export interface AgentStep {
  step_number: number;
  node_name: string;
  description: string;
  timestamp: string;
  duration_ms?: number;
}

export interface TaskStatusResponse {
  task_id: string;
  status: "pending" | "running" | "completed" | "failed";
  task: string;
  result?: { output?: string };
  agent_steps: AgentStep[];
  confidence_score?: number;
  total_tokens_used?: number;
  duration_seconds?: number;
  error?: string;
}

export const submitTask = async (req: TaskSubmitRequest) => {
  const res = await api.post("/run-task", req);
  return res.data as { task_id: string; status: string; message: string };
};

export const getTaskStatus = async (taskId: string) => {
  const res = await api.get(`/status/${taskId}`);
  return res.data as TaskStatusResponse;
};

export const createStepSocket = (taskId: string) => {
  const wsUrl = BASE_URL.replace("http", "ws");
  return new WebSocket(`${wsUrl}/ws/${taskId}`);
};

// ── Competitive Intelligence API ─────────────────────────────────────────────

export interface Company {
  id: string;
  name: string;
  domain: string | null;
  category: string | null;
  description: string | null;
  active: boolean;
  report_count: number;
}

export interface IntelReport {
  id: string;
  company_id: string;
  company_name: string;
  task_id: string | null;
  report_text: string | null;
  signal_level: "high" | "medium" | "low";
  confidence: number | null;
  slack_sent: boolean;
  created_at: string;
}

export interface AddCompanyRequest {
  name: string;
  domain?: string;
  category?: string;
  description?: string;
}

export const getCompanies = async (): Promise<Company[]> => {
  const res = await api.get("/ci/companies");
  return res.data;
};

export const addCompany = async (req: AddCompanyRequest): Promise<Company> => {
  const res = await api.post("/ci/companies", req);
  return res.data;
};

export const deactivateCompany = async (id: string): Promise<void> => {
  await api.delete(`/ci/companies/${id}`);
};

export const getCompanyReports = async (id: string): Promise<IntelReport[]> => {
  const res = await api.get(`/ci/companies/${id}/reports`);
  return res.data;
};

export const getAllReports = async (signalLevel?: string): Promise<IntelReport[]> => {
  const params = signalLevel ? `?signal_level=${signalLevel}` : "";
  const res = await api.get(`/ci/reports${params}`);
  return res.data;
};

export const triggerScanNow = async (companyId?: string): Promise<void> => {
  const params = companyId ? `?company_id=${companyId}` : "";
  await api.post(`/ci/scan-now${params}`);
};

export const deleteAllReports = async (): Promise<{ count: number }> => {
  const res = await api.delete("/ci/reports/all");
  return res.data;
};

export interface SystemStatus {
  primary: { model: string; health: { status: string; message: string } };
  fallback: { model: string; health: { status: string; message: string } };
  timestamp: number;
}

export const getSystemStatus = async (): Promise<SystemStatus> => {
  const res = await api.get("/system/status");
  return res.data;
};
