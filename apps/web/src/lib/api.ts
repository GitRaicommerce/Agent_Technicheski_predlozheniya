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
    cache: "no-store",
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

export interface LegislationRefreshResponse {
  status: string;
  checked: number;
  changed: number;
  unchanged: number;
  skipped_fresh: number;
  refreshed: Array<Record<string, string>>;
  errors: Array<Record<string, string>>;
}

export interface LegislationStatusResponse {
  status: "ok" | "partial" | "missing" | string;
  automatic_source: string;
  configured_acts: number;
  loaded_acts: number;
  missing_acts: string[];
  chunk_count: number;
  latest_fetched_at?: string | null;
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
  job_id?: string;
  job_status?: string;
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
  ingest_quality_status?: string | null;
  ingest_report_json?: Record<string, unknown> | null;
}

export interface TpOutlineSection {
  uid?: string;
  title: string;
  required?: boolean;
  requirements?: string[];
  requirement_ids?: string[];
  requirement_checklist_items?: RequirementChecklistItem[];
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

export interface RequirementChecklistItem {
  id: string;
  text: string;
  category: string;
  category_label: string;
  topic: string;
  importance: "mandatory" | "scored" | "optional" | "scope" | string;
  suggested_section: string;
  coverage_question: string;
  source_chunk_id: string;
  source_page?: number | null;
  source_section_path?: string | null;
  source_file?: string | null;
  source_excerpt: string;
  evidence_cues: string[];
}

export interface RequirementChecklist {
  project_id: string;
  total: number;
  importance_counts: Record<string, number>;
  category_counts: Record<string, number>;
  items: RequirementChecklistItem[];
}

export interface RequirementCoverageItem {
  id: string;
  text?: string | null;
  importance?: string | null;
  status?: "covered" | "missing" | string;
  matched_terms?: string[];
  missing_terms?: string[];
  required_match_count?: number;
}

export interface RequirementCoverage {
  total?: number;
  covered?: number;
  missing?: number;
  covered_ids?: string[];
  missing_ids?: string[];
  critical_missing_ids?: string[];
  items?: RequirementCoverageItem[];
}

export interface Generation {
  id: string;
  section_uid: string;
  variant: number | string;
  text: string;
  evidence_map_json?: Record<string, unknown> | null;
  used_sources_json?: Record<string, unknown> | null;
  flags_json?: (Record<string, unknown> & {
    requirement_coverage?: RequirementCoverage;
  }) | null;
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

export interface GenerationJob {
  id: string;
  project_id: string;
  job_type: string;
  status: "queued" | "processing" | "done" | "error" | string;
  total_sections: number;
  completed_sections: number;
  skipped_sections: number;
  current_section_uid?: string | null;
  current_section_title?: string | null;
  error?: string | null;
  result_json?: Record<string, unknown> | null;
  trace_id?: string | null;
  created_at: string;
  updated_at: string;
  completed_at?: string | null;
}

export interface ExportReadiness {
  project_id: string;
  ready: boolean;
  status: "ready" | "blocked" | string;
  message?: string;
  selected_generation_count?: number;
  selected_section_count?: number;
  blocker_count?: number;
  blockers?: Array<{ code: string; count: number; message: string }>;
  duplicate_selected_sections?: unknown[];
  duplicate_selected_count?: number;
  stale_sections?: string[];
  stale_section_count?: number;
  missing_requirement_sections?: unknown[];
  missing_requirement_count?: number;
  quality_sections?: unknown[];
  quality_section_count?: number;
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
    refreshLegislation: (id: string, force = false) =>
      apiFetch<LegislationRefreshResponse>(
        `/api/v1/projects/${id}/legislation/refresh?force=${String(force)}`,
        { method: "POST" },
      ),
    legislationStatus: (id: string) =>
      apiFetch<LegislationStatusResponse>(
        `/api/v1/projects/${id}/legislation/status`,
      ),
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
    getRequirementChecklist: (projectId: string) =>
      apiFetch<RequirementChecklist>(
        `/api/v1/agents/${projectId}/requirements-checklist`,
      ),
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
    latestGenerationJob: (projectId: string) =>
      apiFetch<GenerationJob | null>(
        `/api/v1/agents/${projectId}/generation-jobs/latest`,
      ),
    getGenerationJob: (projectId: string, jobId: string) =>
      apiFetch<GenerationJob>(
        `/api/v1/agents/${projectId}/generation-jobs/${jobId}`,
      ),
    retryGenerationJob: (projectId: string) =>
      apiFetch<GenerationJob>(
        `/api/v1/agents/${projectId}/generation-jobs/retry`,
        { method: "POST" },
      ),
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
    readiness: (projectId: string) =>
      apiFetch<ExportReadiness>(`/api/v1/export/${projectId}/readiness`),
    docx: async (projectId: string) => {
      const response = await fetch(buildUrl(`/api/v1/export/${projectId}/docx`));
      await ensureOk(response);
      return response.blob();
    },
  },
};
