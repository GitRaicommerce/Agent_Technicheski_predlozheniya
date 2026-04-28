// Empty string = use relative URLs proxied through Next.js (works in Codespaces + local)
const API_URL = "";

type JsonObject = Record<string, unknown>;

export class ApiError extends Error {
  status: number;
  detail?: unknown;

  constructor(message: string, status: number, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export class RateLimitError extends ApiError {
  retryAfter: number;

  constructor(message: string, retryAfter: number, detail?: unknown) {
    super(message, 429, detail);
    this.name = "RateLimitError";
    this.retryAfter = retryAfter;
  }
}

function buildUrl(path: string): string {
  return `${API_URL}${path}`;
}

async function readErrorPayload(response: Response): Promise<unknown> {
  const contentType = response.headers.get("content-type") ?? "";

  if (contentType.includes("application/json")) {
    return response.json().catch(() => null);
  }

  const text = await response.text().catch(() => "");
  return text || null;
}

function stringifyDetail(detail: unknown): string | null {
  if (!detail) return null;
  if (typeof detail === "string") return detail;

  if (typeof detail === "object") {
    const detailRecord = detail as JsonObject;

    const nestedDetail = stringifyDetail(detailRecord.detail);
    if (nestedDetail) {
      return nestedDetail;
    }

    if (typeof detailRecord.message === "string") {
      return detailRecord.message;
    }
  }

  return null;
}

async function ensureOk(response: Response): Promise<void> {
  if (response.ok) return;

  const detail = await readErrorPayload(response);
  const retryAfterHeader = response.headers.get("retry-after");
  const retryAfter =
    retryAfterHeader && /^\d+$/.test(retryAfterHeader)
      ? Number(retryAfterHeader)
      : 60;
  const message =
    stringifyDetail(detail) ??
    (response.status === 429
      ? "Too many requests."
      : `API error ${response.status}`);

  if (response.status === 429) {
    throw new RateLimitError(message, retryAfter, detail);
  }

  throw new ApiError(message, response.status, detail);
}

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(buildUrl(path), {
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
    ...options,
  });

  await ensureOk(response);
  return response.json() as Promise<T>;
}

async function apiNoContent(path: string, options?: RequestInit): Promise<void> {
  const response = await fetch(buildUrl(path), options);
  await ensureOk(response);
}

export interface Project {
  id: string;
  name: string;
  location?: string | null;
  description?: string | null;
  contracting_authority?: string | null;
  tender_date?: string | null;
  created_at: string;
  updated_at?: string | null;
}

export interface ProjectStat {
  files: number;
  outline_locked: boolean;
  sections_generated: number;
  sections_selected: number;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface GenerationVariant {
  text: string;
  evidence_map?: Record<string, string | null>;
}

export interface VerificationResult {
  verdict?: string;
  score?: number;
  summary?: string;
  hallucinations?: Array<Record<string, unknown>>;
  gaps?: Array<Record<string, unknown>>;
  conflicts?: Array<Record<string, unknown>>;
}

export interface OrchestratorAgentResult {
  variant_1?: GenerationVariant;
  variant_2?: GenerationVariant;
  generation_ids?: Record<string, string>;
  verification?: VerificationResult;
}

export interface OrchestratorResponse {
  schema_version: string;
  status: string;
  trace_id: string;
  assistant_message: string;
  ui_actions: { type: string; payload: JsonObject }[];
  agent_called?: string | null;
  questions_to_user: string[];
  agent_result?: OrchestratorAgentResult;
}

export interface UploadedFile {
  id: string;
  project_id: string;
  module: string;
  filename: string;
  file_hash: string;
  ingest_status: string;
  ingest_error?: string | null;
}

export interface TpOutlineSection {
  uid?: string;
  title: string;
  required?: boolean;
  requirements?: string[];
  subsections?: TpOutlineSection[];
  children?: TpOutlineSection[];
}

export interface TpOutline {
  id: string;
  outline_json: {
    sections?: TpOutlineSection[];
    outline?: TpOutlineSection[];
    [key: string]: unknown;
  };
  status_locked: boolean;
  version: number;
}

export interface ScheduleTask {
  uid: string;
  wbs?: string | null;
  name: string;
  duration_days?: number | null;
}

export interface ScheduleResource {
  id?: string;
  name?: string;
  [key: string]: unknown;
}

export interface ScheduleInfo {
  id: string;
  schedule_json: {
    tasks?: ScheduleTask[];
    resources?: ScheduleResource[];
    error?: string;
    [key: string]: unknown;
  };
  status_locked: boolean;
  version: number;
}

export interface Generation {
  id: string;
  section_uid: string;
  variant: number | string;
  text: string;
  evidence_map_json?: Record<string, unknown> | null;
  used_sources_json?: Record<string, unknown> | null;
  flags_json?: Record<string, unknown> | null;
  evidence_status: string;
  selected: boolean;
  created_at: string;
  trace_id?: string | null;
}

export interface SectionGenerations {
  section_uid: string;
  section_title?: string | null;
  variants: Generation[];
}

export interface RegenerateResponse {
  generation_ids: Record<string, string>;
  trace_id: string;
}

export const api = {
  projects: {
    list: (limit = 20, offset = 0) =>
      apiFetch<Project[]>(`/api/v1/projects?limit=${limit}&offset=${offset}`),
    stats: () => apiFetch<Record<string, ProjectStat>>("/api/v1/projects/stats"),
    get: (id: string) => apiFetch<Project>(`/api/v1/projects/${id}`),
    create: (data: Partial<Project>) =>
      apiFetch<Project>("/api/v1/projects", {
        method: "POST",
        body: JSON.stringify(data),
      }),
    update: (id: string, data: Partial<Project>) =>
      apiFetch<Project>(`/api/v1/projects/${id}`, {
        method: "PUT",
        body: JSON.stringify(data),
      }),
    delete: (id: string) =>
      apiNoContent(`/api/v1/projects/${id}`, { method: "DELETE" }),
  },
  files: {
    upload: async (
      projectId: string,
      module: string,
      file: File,
    ): Promise<UploadedFile> => {
      const form = new FormData();
      form.append("module", module);
      form.append("file", file);

      const response = await fetch(buildUrl(`/api/v1/files/${projectId}/upload`), {
        method: "POST",
        body: form,
      });

      await ensureOk(response);
      return response.json() as Promise<UploadedFile>;
    },
    list: (projectId: string, module?: string) => {
      const qs = module ? `?module=${encodeURIComponent(module)}` : "";
      return apiFetch<UploadedFile[]>(`/api/v1/files/${projectId}/files${qs}`);
    },
    getStatus: (projectId: string, fileId: string) =>
      apiFetch<UploadedFile>(`/api/v1/files/${projectId}/files/${fileId}/status`),
    delete: (projectId: string, fileId: string) =>
      apiNoContent(`/api/v1/files/${projectId}/files/${fileId}`, {
        method: "DELETE",
      }),
  },
  agents: {
    chat: (projectId: string, message: string, history: ChatMessage[]) =>
      apiFetch<OrchestratorResponse>("/api/v1/agents/chat", {
        method: "POST",
        body: JSON.stringify({ project_id: projectId, message, history }),
      }),
    getOutline: (projectId: string) =>
      apiFetch<TpOutline | null>(`/api/v1/agents/${projectId}/outline`),
    lockOutline: (projectId: string, outlineId: string) =>
      apiFetch<{ status: string; outline_id: string }>(
        `/api/v1/agents/${projectId}/outline/lock?outline_id=${encodeURIComponent(outlineId)}`,
        { method: "POST" },
      ),
    unlockOutline: (projectId: string, outlineId: string) =>
      apiFetch<{ status: string; outline_id: string }>(
        `/api/v1/agents/${projectId}/outline/unlock?outline_id=${encodeURIComponent(outlineId)}`,
        { method: "POST" },
      ),
    deleteOutline: (projectId: string) =>
      apiNoContent(`/api/v1/agents/${projectId}/outline`, { method: "DELETE" }),
    getSchedule: (projectId: string) =>
      apiFetch<ScheduleInfo | null>(`/api/v1/agents/${projectId}/schedule`),
    lockSchedule: (projectId: string, scheduleId: string) =>
      apiFetch<{ status: string; schedule_id: string }>(
        `/api/v1/agents/${projectId}/schedule/lock?schedule_id=${encodeURIComponent(scheduleId)}`,
        { method: "POST" },
      ),
    unlockSchedule: (projectId: string, scheduleId: string) =>
      apiFetch<{ status: string; schedule_id: string }>(
        `/api/v1/agents/${projectId}/schedule/unlock?schedule_id=${encodeURIComponent(scheduleId)}`,
        { method: "POST" },
      ),
    listGenerations: (projectId: string) =>
      apiFetch<SectionGenerations[]>(`/api/v1/agents/${projectId}/generations`),
    selectGeneration: (projectId: string, generationId: string) =>
      apiFetch<{ status: string; generation_id: string }>(
        `/api/v1/agents/${projectId}/generations/${generationId}/select`,
        { method: "POST" },
      ),
    regenerateSection: (projectId: string, sectionUid: string) =>
      apiFetch<RegenerateResponse>(
        `/api/v1/agents/${projectId}/sections/${encodeURIComponent(sectionUid)}/regenerate`,
        { method: "POST" },
      ),
  },
  export: {
    docx: async (projectId: string) => {
      const response = await fetch(buildUrl(`/api/v1/export/${projectId}/docx`));
      await ensureOk(response);
      return response.blob();
    },
  },
};
