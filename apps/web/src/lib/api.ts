const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `API error ${res.status}`);
  }
  return res.json();
}

export interface Project {
  id: string;
  name: string;
  location?: string;
  description?: string;
  contracting_authority?: string;
  tender_date?: string;
  created_at: string;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface OrchestratorResponse {
  schema_version: string;
  status: string;
  trace_id: string;
  assistant_message: string;
  ui_actions: { type: string; payload: Record<string, unknown> }[];
  agent_called?: string;
  questions_to_user: string[];
}

export interface UploadedFile {
  id: string;
  project_id: string;
  module: string;
  filename: string;
  file_hash: string;
  ingest_status: string;
}

// Projects
export const api = {
  projects: {
    list: () => apiFetch<Project[]>("/api/v1/projects/"),
    get: (id: string) => apiFetch<Project>(`/api/v1/projects/${id}`),
    create: (data: Partial<Project>) =>
      apiFetch<Project>("/api/v1/projects/", {
        method: "POST",
        body: JSON.stringify(data),
      }),
    delete: (id: string) =>
      fetch(`${API_URL}/api/v1/projects/${id}`, { method: "DELETE" }),
  },
  files: {
    upload: async (project_id: string, module: string, file: File): Promise<UploadedFile> => {
      const form = new FormData();
      form.append("module", module);
      form.append("file", file);
      const res = await fetch(`${API_URL}/api/v1/files/${project_id}/upload`, {
        method: "POST",
        body: form,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || `Upload error ${res.status}`);
      }
      return res.json();
    },
    list: (project_id: string, module?: string) => {
      const qs = module ? `?module=${module}` : "";
      return apiFetch<UploadedFile[]>(`/api/v1/files/${project_id}/files${qs}`);
    },
  },
  agents: {
    chat: (project_id: string, message: string, history: ChatMessage[]) =>
      apiFetch<OrchestratorResponse>("/api/v1/agents/chat", {
        method: "POST",
        body: JSON.stringify({ project_id, message, history }),
      }),
  },
  export: {
    docx: async (project_id: string) => {
      const res = await fetch(`${API_URL}/api/v1/export/${project_id}/docx`);
      if (!res.ok) throw new Error("Export failed");
      return res.blob();
    },
  },
};
