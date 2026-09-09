/**
 * Intent id → stable colour + display name. One muted 12-step palette, defined once (ui/DESIGN.md).
 * Order mirrors config/intents.yaml v1. Unknown ids (if the taxonomy changes again) get a deterministic
 * colour from the same palette and a title-cased name.
 */
import type { IntentId } from "./types";

export interface IntentMeta {
  id: IntentId;
  name: string;
  /** Short label for badges and axes. */
  short: string;
  color: string;
}

/** Ordered like config/intents.yaml (rare, escalation-critical intents first). */
export const INTENTS: readonly IntentMeta[] = [
  { id: "non_english", name: "Non-English message", short: "Non-English", color: "#C08BD6" },
  { id: "account_hacked_or_security", name: "Account security", short: "Security", color: "#E07A8B" },
  { id: "billing_or_charge", name: "Billing / charges / refunds", short: "Billing", color: "#E8955A" },
  { id: "login_or_password", name: "Login / password / account access", short: "Login", color: "#D4A868" },
  { id: "download_or_offline", name: "Downloads / offline mode", short: "Downloads", color: "#62C4B8" },
  { id: "metadata_or_artist_issue", name: "Wrong metadata / artist-side issue", short: "Metadata", color: "#B5C96A" },
  { id: "content_or_availability", name: "Missing content / greyed-out / region", short: "Content", color: "#7FCF8E" },
  { id: "playlist_or_library", name: "Playlists / saved music / personalisation", short: "Playlists", color: "#D9C25A" },
  { id: "playback_or_app_bug", name: "Playback / app malfunction", short: "Playback", color: "#7FB2E5" },
  { id: "subscription_or_plan", name: "Plans / eligibility / upgrade / cancel / Free-tier limits", short: "Plans", color: "#9C93E8" },
  { id: "feature_request_or_feedback", name: "Product feedback & suggestions", short: "Feedback", color: "#8FA3BF" },
  { id: "other", name: "Praise, thanks, unclear, spam, media-only, off-topic", short: "Other", color: "#9AA0A6" },
];

export const INTENT_IDS: readonly IntentId[] = INTENTS.map((i) => i.id);

const BY_ID: ReadonlyMap<IntentId, IntentMeta> = new Map(INTENTS.map((i) => [i.id, i]));

function hashString(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

function titleFromId(id: string): string {
  return id.replace(/_or_/g, " / ").replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

/** Metadata for any intent id; unknown ids get a stable palette colour and a title-cased name. */
export function intentMeta(id: IntentId): IntentMeta {
  const known = BY_ID.get(id);
  if (known) return known;
  const fallback = INTENTS[hashString(id) % INTENTS.length] ?? INTENTS[0]!;
  return { id, name: titleFromId(id), short: titleFromId(id), color: fallback.color };
}

export function intentColor(id: IntentId): string {
  return intentMeta(id).color;
}

export function intentName(id: IntentId): string {
  return intentMeta(id).name;
}

export function intentShort(id: IntentId): string {
  return intentMeta(id).short;
}
