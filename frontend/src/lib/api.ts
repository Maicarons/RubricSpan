/**
 * API 客户端 —— 封装后端全部接口（基于 contracts/openapi.yaml 与 routes.rs 契约）。
 *
 * 在线模式：请求 Rust 服务（默认 http://127.0.0.1:8080）。
 * 离线模式（M6）：由 WASM 在浏览器内完成评分，不走本客户端。
 */

export const DEFAULT_API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8080";

/** API 地址覆盖（管理后台「设置」页可运行时修改，localStorage 持久化）。 */
export const API_BASE_KEY = "rubricspan.apiBase";

export function getApiBase(): string {
  if (typeof window === "undefined") return DEFAULT_API_BASE;
  try {
    return localStorage.getItem(API_BASE_KEY)?.trim() || DEFAULT_API_BASE;
  } catch {
    return DEFAULT_API_BASE;
  }
}

/** 设置/清除 API 地址覆盖（传空字符串恢复默认）。 */
export function setApiBase(base: string): void {
  const v = base.trim();
  try {
    if (v) localStorage.setItem(API_BASE_KEY, v);
    else localStorage.removeItem(API_BASE_KEY);
  } catch {
    /* ignore */
  }
}

/** 运行模式：在线（Rust 服务）/ 离线（WASM 浏览器推理） */
export type RunMode = "online" | "offline";

/** 健康检查（模式切换时探测在线服务可用性） */
export async function checkHealth(): Promise<boolean> {
  try {
    const res = await fetch(`${getApiBase()}/api/health`, { cache: "no-store" });
    return res.ok;
  } catch {
    return false;
  }
}

// ---------------------------------------------------------------------------
// 领域类型（与 Rust 契约一致）
// ---------------------------------------------------------------------------

export type ConfigStatus = "none" | "pending_review" | "confirmed";

export interface Question {
  question_id: string;
  content: string;
  subject: string;
  total_score: number;
  standard_answer_text?: string | null;
  config_status: ConfigStatus;
}

export interface ScoringPoint {
  point_id: number;
  point_text: string;
  weight: number;
  aliases: string[];
}

export interface Thresholds {
  similarity_high: number;
  similarity_low: number;
}

export interface ScoringConfig {
  question_id: string;
  total_score: number;
  subject?: string | null;
  points: ScoringPoint[];
  thresholds?: Thresholds | null;
  meta?: unknown;
}

export interface ParseResponse {
  status: string;
  scoring_config: ScoringConfig;
  warnings: string[];
}

export interface AnswerSubmission {
  student_id?: string;
  class_name?: string;
  answer_text?: string;
  image?: string;
  source?: string;
}

export interface SubmitBody {
  question_id: string;
  submissions: AnswerSubmission[];
}

export interface SubmitResponse {
  accepted: number;
  answer_ids: string[];
}

export interface OcrLine {
  text: string;
  confidence: number;
  box?: number[];
}

export interface OcrResult {
  question_id: string;
  answer_text: string;
  confidence: number;
  lines: OcrLine[];
  low_confidence: boolean;
}

export type HitStatus = "hit_exact" | "hit_semantic" | "partial" | "miss";
export type ScoreSource = "mrc" | "similarity" | "option";
export type Rating = "excellent" | "good" | "pass" | "fail";

export interface PointDetail {
  point_id: number;
  hit_status: HitStatus;
  matched_alias?: string | null;
  extracted_span?: string | null;
  confidence?: number | null;
  similarity?: number | null;
  point_score: number;
  source: ScoreSource;
}

export interface ScoreResult {
  question_id: string;
  answer_id: string;
  student_id?: string | null;
  class_name?: string | null;
  total_score: number;
  max_score: number;
  rating: Rating;
  point_details: PointDetail[];
  ocr_confidence?: number | null;
  scored_at: string;
}

export interface ScoreResponse {
  question_id: string;
  results: ScoreResult[];
}

/** 落盘评分记录（与 ScoreResult 同构，rating 为字符串） */
export interface ScoreRecord {
  question_id: string;
  answer_id: string;
  student_id?: string | null;
  class_name?: string | null;
  total_score: number;
  max_score: number;
  rating: string;
  point_details: PointDetail[];
  ocr_confidence?: number | null;
}

export interface Answer {
  answer_id: string;
  question_id: string;
  student_id?: string | null;
  class_name?: string | null;
  answer_text?: string | null;
  source?: string | null;
  ocr_text?: string | null;
}

// ---------------------------------------------------------------------------
// 请求封装
// ---------------------------------------------------------------------------

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${getApiBase()}${path}`, {
    cache: "no-store",
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.message) msg = body.message;
    } catch {
      /* ignore */
    }
    throw new Error(msg);
  }
  return (await res.json()) as T;
}

// ---------------------------------------------------------------------------
// 接口方法
// ---------------------------------------------------------------------------

export function listQuestions(
  subject?: string,
): Promise<{ items: Question[]; total: number }> {
  const q = subject ? `?subject=${encodeURIComponent(subject)}` : "";
  return request(`/api/questions${q}`);
}

export interface CreateQuestionBody {
  question_id?: string;
  content: string;
  subject: string;
  total_score: number;
  standard_answer_text?: string;
}

export function createQuestion(body: CreateQuestionBody): Promise<Question> {
  return request<Question>("/api/questions", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function parseStandardAnswer(
  questionId: string,
  rawAnswerText: string,
  question?: string,
): Promise<ParseResponse> {
  return request<ParseResponse>("/api/standard-answer/parse", {
    method: "POST",
    body: JSON.stringify({
      question_id: questionId,
      raw_answer_text: rawAnswerText,
      question: question ?? "",
    }),
  });
}

export function getStandardAnswer(questionId: string): Promise<ScoringConfig> {
  return request<ScoringConfig>(
    `/api/standard-answer?question_id=${encodeURIComponent(questionId)}`,
  );
}

export function saveStandardAnswer(cfg: ScoringConfig): Promise<{
  question_id: string;
  saved_at: string;
}> {
  return request(`/api/standard-answer`, {
    method: "PUT",
    body: JSON.stringify(cfg),
  });
}

export function listAnswers(
  questionId: string,
): Promise<{ items: Answer[]; total: number }> {
  return request(`/api/answers?question_id=${encodeURIComponent(questionId)}`);
}

export function submitAnswers(body: SubmitBody): Promise<SubmitResponse> {
  return request<SubmitResponse>("/api/answers", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** OCR：直接发送图片二进制，需带 X-Question-Id 头。 */
export async function ocrImage(questionId: string, blob: Blob): Promise<OcrResult> {
  const res = await fetch(`${getApiBase()}/api/ocr`, {
    method: "POST",
    cache: "no-store",
    headers: { "X-Question-Id": questionId },
    body: blob,
  });
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`;
    try {
      const b = await res.json();
      if (b?.message) msg = b.message;
    } catch {
      /* ignore */
    }
    throw new Error(msg);
  }
  return (await res.json()) as OcrResult;
}

export function scoreAnswers(
  questionId: string,
  answerIds: string[],
): Promise<ScoreResponse> {
  return request<ScoreResponse>("/api/score", {
    method: "POST",
    body: JSON.stringify({ question_id: questionId, answer_ids: answerIds }),
  });
}

export function listResults(
  questionId?: string,
  className?: string,
): Promise<{ items: ScoreRecord[]; total: number }> {
  const params = new URLSearchParams();
  if (questionId) params.set("question_id", questionId);
  if (className) params.set("class_name", className);
  const q = params.toString();
  return request(`/api/results${q ? `?${q}` : ""}`);
}

// ---------------------------------------------------------------------------
// 管理后台（/api/admin/stats、/api/admin/config · CC-004 新增）
// ---------------------------------------------------------------------------

export interface AdminStats {
  questions: { total: number; by_config_status: Record<string, number> };
  answers: { total: number };
  scores: {
    total: number;
    average: number;
    max_score_average: number;
    by_rating: Record<string, number>;
    distribution: { label: string; count: number }[];
  };
  point_hits: { question_id: string; point_id: number; hit: number; total: number }[];
}

export interface AdminConfig {
  server_version: string;
  store_path: string;
  models: { mrc: boolean; similarity: boolean };
  llm: { configured: boolean; endpoints: { name: string; model: string }[] };
  ocr: { enabled: boolean; note?: string };
}

/** 全局评分参数（管理后台可调；题级 thresholds 优先覆盖高低阈值）。 */
export interface ScoringSettings {
  similarity_high: number;
  similarity_low: number;
  partial_credit: number;
  mrc_confidence_threshold: number;
}

export const DEFAULT_SCORING_SETTINGS: ScoringSettings = {
  similarity_high: 0.9,
  similarity_low: 0.75,
  partial_credit: 0.25,
  mrc_confidence_threshold: 0.5,
};

export function getAdminStats(): Promise<AdminStats> {
  return request<AdminStats>("/api/admin/stats");
}

export function getAdminConfig(): Promise<AdminConfig> {
  return request<AdminConfig>("/api/admin/config");
}

export function getScoringSettings(): Promise<ScoringSettings> {
  return request<ScoringSettings>("/api/admin/scoring-settings");
}

export function saveScoringSettings(settings: ScoringSettings): Promise<ScoringSettings> {
  return request<ScoringSettings>("/api/admin/scoring-settings", {
    method: "PUT",
    body: JSON.stringify(settings),
  });
}
