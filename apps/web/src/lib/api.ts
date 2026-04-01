// Empty string = use relative URLs proxied through Next.js (works in Codespaces + local)
const API_URL = "";

export class RateLimitError extends Error {
  retryAfter: number;
  constructor(retryAfter: number) {
    super(`Твърде много заявки. Изчакайте ${retryAfter} секунди.`);
    this.retryAfter = retryAfter;
    this.name = "RateLimitError";
  }
}

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    if (res.status === 429) {
      const retryAfter = parseInt(res.headers.get("Retry-After") ?? "60", 10);
      throw new RateLimitError(retryAfter);
    }
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    const detail = err.detail;
    const message =
      typeof detail === "string"
        ? detail
        : detail?.message ?? JSON.stringify(detail) ?? `API error ${res.status}`;
    throw new Error(message);
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
  updated_at?: string;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface GenerationVariant {
  text: string;
  evidence_map?: Record<string, string>;
}

export interface OrchestratorResponse {
  schema_version: string;
  status: string;
  trace_id: string;
  assistant_message: string;
  ui_actions: { type: string; payload: Record<string, unknown> }[];
  agent_called?: string;
  questions_to_user: string[];
  agent_result?: {
    variant_1?: GenerationVariant;
    variant_2?: GenerationVariant;
    generation_ids?: Record<string, string>;
    flags?: string[];
    verification?: { verdict?: string; flags?: string[] };
    [key: string]: unknown;
  };
}

export interface UploadedFile {
  id: string;
  project_id: string;
  module: string;
  filename: string;
  file_hash: string;
  ingest_status: string;
  ingest_error?: string;
}

export interface TpOutlineSection {
  uid?: string;
  title: string;
  required?: boolean;
  requirements?: string[];
  subsections?: TpOutlineSection[];
}

export interface TpOutline {
  id: string;
  outline_json: {
    sections?: TpOutlineSection[];
    outline?: TpOutlineSection[];
  };
  status_locked: boolean;
  version: number;
}

export interface ScheduleInfo {
  id: string;
  schedule_json: {
    tasks?: { uid: number; name: string; start?: string; finish?: string; duration_days?: number; wbs?: string }[];
    resources?: { uid: number; name: string; type?: string }[];
    error?: string;
  };
  status_locked: boolean;
  version: number;
}

export interface Generation {
  id: string;
  section_uid: string;
  variant: string;
  text: string;
  evidence_map_json?: Record<string, string>;
  used_sources_json?: Record<string, unknown>;
  flags_json?: Record<string, unknown>;
  evidence_status: string;
  selected: boolean;
  created_at: string;
  trace_id?: string;
}

export interface SectionGenerations {
  section_uid: string;
  section_title?: string;
  variants: Generation[];
}

export interface ProjectStat {
  files: number;
  outline_locked: boolean;
  sections_generated: number;
  sections_selected: number;
}

// Projects
export const api = {
  projects: {
    list: (limit = 20, offset = 0) => apiFetch<Project[]>(`/api/v1/projects?limit=${limit}&offset=${offset}`),
    stats: () => apiFetch<Record<string, ProjectStat>>("/api/v1/projects/stats"),
    get: (id: string) => apiFetch<Project>(`/api/v1/projects/${id}`),
    create: (data: Partial<Project>) =>
      apiFetch<Project>("/api/v1/projects", {
        method: "POST",
        body: JSON.stringify(data),
      }),
    update: (id: string, data: Partial<Omit<Project, "id" | "created_at" | "updated_at">>) =>
      apiFetch<Project>(`/api/v1/projects/${id}`, {
        method: "PUT",
        body: JSON.stringify(data),
      }),
    delete: (id: string) =>
      fetch(`${API_URL}/api/v1/projects/${id}`, { method: "DELETE" }),
  },
  files: {
    upload: async (
      project_id: string,
      module: string,
      file: File,
    ): Promise<UploadedFile> => {
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
    getStatus: (project_id: string, file_id: string) =>
      apiFetch<UploadedFile>(
        `/api/v1/files/${project_id}/files/${file_id}/status`,
      ),
    delete: (project_id: string, file_id: string) =>
      fetch(`${API_URL}/api/v1/files/${project_id}/files/${file_id}`, {
        method: "DELETE",
      }),
  },
  agents: {
    chat: (project_id: string, message: string, history: ChatMessage[]) =>
      apiFetch<OrchestratorResponse>("/api/v1/agents/chat", {
        method: "POST",
        body: JSON.stringify({ project_id, message, history }),
      }),
    getOutline: async (project_id: string): Promise<TpOutline | null> => {
      try {
        return await apiFetch<TpOutline>(`/api/v1/agents/${project_id}/outline`);
      } catch {
        return null;
      }
    },
    lockOutline: async (
      project_id: string,
      outline_id: string,
    ): Promise<void> => {
      const res = await fetch(
        `${API_URL}/api/v1/agents/${project_id}/outline/lock?outline_id=${encodeURIComponent(outline_id)}`,
        { method: "POST" },
      );
      if (!res.ok) throw new Error(`Одобрението не успя: ${res.status}`);
    },
    unlockOutline: async (
      project_id: string,
      outline_id: string,
    ): Promise<void> => {
      const res = await fetch(
        `${API_URL}/api/v1/agents/${project_id}/outline/unlock?outline_id=${encodeURIComponent(outline_id)}`,
        { method: "POST" },
      );
      if (!res.ok) throw new Error(`Отключването не успя: ${res.status}`);
    },
    deleteOutline: async (project_id: string): Promise<void> => {
      const res = await fetch(
        `${API_URL}/api/v1/agents/${project_id}/outline`,
        { method: "DELETE" },
      );
      if (!res.ok) throw new Error(`Изтриването не успя: ${res.status}`);
    },
    selectGeneration: (project_id: string, generation_id: string) =>
      apiFetch<{ status: string }>(
        `/api/v1/agents/${project_id}/generations/${generation_id}/select`,
        { method: "POST" },
      ),
    getSchedule: async (project_id: string): Promise<ScheduleInfo | null> => {
      try {
        return await apiFetch<ScheduleInfo>(`/api/v1/agents/${project_id}/schedule`);
      } catch {
        return null;
      }
    },
    lockSchedule: async (
      project_id: string,
      schedule_id: string,
    ): Promise<void> => {
      const res = await fetch(
        `${API_URL}/api/v1/agents/${project_id}/schedule/lock?schedule_id=${encodeURIComponent(schedule_id)}`,
        { method: "POST" },
      );
      if (!res.ok) throw new Error(`Одобрението не успя: ${res.status}`);
    },
    unlockSchedule: async (
      project_id: string,
      schedule_id: string,
    ): Promise<void> => {
      const res = await fetch(
        `${API_URL}/api/v1/agents/${project_id}/schedule/unlock?schedule_id=${encodeURIComponent(schedule_id)}`,
        { method: "POST" },
      );
      if (!res.ok) throw new Error(`Отключването не успя: ${res.status}`);
    },
    listGenerations: (project_id: string) =>
      apiFetch<SectionGenerations[]>(`/api/v1/agents/${project_id}/generations`),
    regenerateSection: (project_id: string, section_uid: string) =>
      apiFetch<{ generation_ids: Record<string, string>; trace_id: string }>(
        `/api/v1/agents/${project_id}/sections/${section_uid}/regenerate`,
        { method: "POST" },
      ),
  },
  export: {
    docx: async (project_id: string) => {
      const res = await fetch(`${API_URL}/api/v1/export/${project_id}/docx`);
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        const detail = err.detail;
        const message =
          typeof detail === "string"
            ? detail
            : detail?.message ?? `Export failed (${res.status})`;
        throw new Error(message);
      }
      return res.blob();
    },
  },
};
