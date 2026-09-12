/**
 * Data layer (ui/DESIGN.md "Data layer", CONTRACT §10).
 *
 * Static mode (`VITE_STATIC === "1"`) reads `${BASE_URL}data/<name>.json`; live mode calls `/api/*`.
 * GET responses are cached in memory for the session. Errors are typed: `ApiError` carries the HTTP
 * status and server `detail`; `StaticModeError` marks features that need the live server.
 */
import type {
  AgentResponse,
  DecisionEntry,
  EscalationPolicy,
  EvalSummary,
  FailureMode,
  HandleMode,
  Health,
  IntentDefinition,
  MergedGoldenExample,
  ProcessedThread,
  RatingQueueItem,
  RatingRecord,
  RatingSubmission,
  UiMode,
} from "./types";

export const IS_STATIC: boolean = import.meta.env.VITE_STATIC === "1";
/**
 * Hybrid deployment (Vercel): evaluation data comes from the static JSON export, but the agent itself is live
 * behind `/api/agent/handle` (a serverless function with the Gemini keys). Set `VITE_LIVE_HANDLE=1`.
 */
export const LIVE_AGENT: boolean = IS_STATIC && import.meta.env.VITE_LIVE_HANDLE === "1";

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;
  readonly url: string;

  constructor(url: string, status: number, detail: string) {
    super(`${status} from ${url}: ${detail}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.url = url;
  }
}

export class StaticModeError extends Error {
  readonly feature: string;

  constructor(feature: string, message?: string) {
    super(message ?? `${feature} needs the live API server; this build reads recorded results only.`);
    this.name = "StaticModeError";
    this.feature = feature;
  }
}

export function isApiError(e: unknown): e is ApiError {
  return e instanceof ApiError;
}

export function isStaticModeError(e: unknown): e is StaticModeError {
  return e instanceof StaticModeError;
}

/** Human-readable message for any error thrown by this module. */
export function describeError(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 0) return "The API server is not reachable. Start it with `make serve` and reload.";
    return e.detail;
  }
  if (e instanceof Error) return e.message;
  return "Something went wrong.";
}

// ---------------------------------------------------------------------------- fetch + cache

const cache = new Map<string, Promise<unknown>>();

function staticUrl(name: string): string {
  return `${import.meta.env.BASE_URL}data/${name}.json`;
}

async function parseError(res: Response, url: string): Promise<ApiError> {
  let detail = res.statusText || `HTTP ${res.status}`;
  try {
    const body = (await res.json()) as { detail?: unknown };
    if (typeof body.detail === "string") detail = body.detail;
  } catch {
    /* non-JSON error body: keep the status text */
  }
  return new ApiError(url, res.status, detail);
}

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(url, init);
  } catch (e) {
    throw new ApiError(url, 0, e instanceof Error ? e.message : "network error");
  }
  if (!res.ok) throw await parseError(res, url);
  return (await res.json()) as T;
}

/** GET with a session-scoped in-memory cache; a failed request is evicted so it can be retried. */
function cachedGet<T>(url: string): Promise<T> {
  const hit = cache.get(url);
  if (hit) return hit as Promise<T>;
  const p = fetchJson<T>(url).catch((e: unknown) => {
    cache.delete(url);
    throw e;
  });
  cache.set(url, p);
  return p;
}

/** Drop cached GETs (all, or those whose URL contains `match`). */
export function invalidate(match?: string): void {
  if (!match) {
    cache.clear();
    return;
  }
  for (const key of [...cache.keys()]) if (key.includes(match)) cache.delete(key);
}

function normaliseText(text: string): string {
  return text.replace(/\s+/g, " ").trim();
}

// ---------------------------------------------------------------------------- public API

export function getHealth(): Promise<Health> {
  return cachedGet<Health>(IS_STATIC && !LIVE_AGENT ? staticUrl("health") : "/api/health");
}

export function getResults(): Promise<EvalSummary> {
  return cachedGet<EvalSummary>(IS_STATIC ? staticUrl("eval_summary") : "/api/results");
}

export function getFailures(): Promise<FailureMode[]> {
  return cachedGet<FailureMode[]>(IS_STATIC ? staticUrl("failure_modes") : "/api/failures");
}

export function getGolden(): Promise<MergedGoldenExample[]> {
  return cachedGet<MergedGoldenExample[]>(IS_STATIC ? staticUrl("golden_merged") : "/api/golden");
}

export async function getGoldenById(id: string): Promise<MergedGoldenExample> {
  if (IS_STATIC) {
    const rows = await getGolden();
    const row = rows.find((r) => r.id === id);
    if (!row) throw new ApiError(staticUrl("golden_merged"), 404, `No golden example with id ${id}.`);
    return row;
  }
  return cachedGet<MergedGoldenExample>(`/api/golden/${encodeURIComponent(id)}`);
}

/**
 * Run the agent on a message. In static mode this replays the recorded agent run for a golden
 * message (exact text match after whitespace normalisation) and throws `StaticModeError` otherwise.
 */
export async function handle(text: string, mode?: HandleMode): Promise<AgentResponse> {
  if (IS_STATIC && !LIVE_AGENT) {
    const wanted = normaliseText(text);
    const rows = await getGolden();
    const row = rows.find((r) => normaliseText(r.text) === wanted);
    const recorded = row?.predictions.agent;
    if (!recorded) {
      throw new StaticModeError(
        "Free-text agent runs",
        "This build has no live agent. Pick one of the recorded messages, or run the API server for free text.",
      );
    }
    return recorded;
  }
  const body: { text: string; mode?: HandleMode } = mode ? { text, mode } : { text };
  return fetchJson<AgentResponse>("/api/agent/handle", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function getRatingQueue(): Promise<RatingQueueItem[]> {
  if (IS_STATIC) return Promise.reject(new StaticModeError("Human rating"));
  return fetchJson<RatingQueueItem[]>("/api/rating-queue");
}

export function getRatings(): Promise<RatingRecord[]> {
  if (IS_STATIC) return Promise.reject(new StaticModeError("Human rating"));
  return fetchJson<RatingRecord[]>("/api/ratings");
}

export async function postRating(rating: RatingSubmission): Promise<RatingRecord> {
  if (IS_STATIC) throw new StaticModeError("Human rating");
  const saved = await fetchJson<RatingRecord>("/api/ratings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(rating),
  });
  invalidate("/api/rating");
  return saved;
}

export function getDecisions(): Promise<DecisionEntry[]> {
  return cachedGet<DecisionEntry[]>(IS_STATIC ? staticUrl("decisions") : "/api/decisions");
}

/** Processed thread (§3). Static mode rebuilds a thread view from the golden example's recorded turns. */
export async function getThread(threadId: string): Promise<ProcessedThread> {
  if (IS_STATIC) {
    const rows = await getGolden();
    const row = rows.find((r) => r.thread_id === threadId);
    if (!row) throw new ApiError(staticUrl("golden_merged"), 404, `No recorded thread ${threadId}.`);
    const brand = row.historical_thread.filter((t) => t.role === "brand");
    const first = brand[0];
    return {
      thread_id: row.thread_id,
      opener_tweet_id: row.historical_thread[0]?.tweet_id ?? 0,
      created_at: row.created_at,
      customer_author_id: "customer",
      customer_text_raw: row.text_raw,
      customer_text: row.text,
      has_link: row.text.includes("<url>"),
      n_words: row.text.split(/\s+/).filter(Boolean).length,
      language: row.gold.intent === "non_english" ? "other" : "en",
      brand_replies: brand.map((t) => ({
        tweet_id: t.tweet_id,
        created_at: t.created_at,
        text_raw: t.text,
        text: t.text,
        agent_sig: t.agent_sig ?? null,
        links: [],
        resolved_links: [],
        asks_dm: /\b(dm|direct message|dms)\b/i.test(t.text),
      })),
      turns: row.historical_thread,
      n_brand_replies: brand.length,
      n_turns: row.historical_thread.length,
      first_reply_text: first?.text ?? row.historical_brand_reply,
      first_reply_asks_dm: first ? /\b(dm|direct message|dms)\b/i.test(first.text) : false,
    };
  }
  return cachedGet<ProcessedThread>(`/api/threads/${encodeURIComponent(threadId)}`);
}

/** Intent taxonomy (always static: derived from config/intents.yaml at export time). */
export function getIntents(): Promise<IntentDefinition[]> {
  return cachedGet<IntentDefinition[]>(staticUrl("intents"));
}

/** Escalation policy (always static: derived from config/escalation.yaml at export time). */
export function getPolicy(): Promise<EscalationPolicy> {
  return cachedGet<EscalationPolicy>(staticUrl("escalation"));
}

/** Resolve the UI mode shown in the sidebar status chips. */
export function uiMode(health: Health | null): UiMode {
  if (IS_STATIC) return "static";
  if (health?.has_api_key && !health.cache_only) return "live";
  return "cache-only";
}
