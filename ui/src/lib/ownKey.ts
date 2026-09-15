/**
 * "Bring your own Gemini key". The visitor's key lives in `sessionStorage` (this tab only, gone when it
 * closes) and is sent as the `X-Gemini-Key` header on live agent calls. It is never logged and never
 * written anywhere else; the serverless function uses it for that request only.
 */
import { useCallback, useSyncExternalStore } from "react";

const STORAGE_KEY = "cadence.geminiKey";
const listeners = new Set<() => void>();

function notify(): void {
  for (const l of listeners) l();
}

export function getOwnKey(): string | null {
  try {
    const v = window.sessionStorage.getItem(STORAGE_KEY);
    return v && v.trim() ? v.trim() : null;
  } catch {
    return null;
  }
}

export function setOwnKey(key: string): void {
  const v = key.trim();
  if (!v) {
    clearOwnKey();
    return;
  }
  try {
    window.sessionStorage.setItem(STORAGE_KEY, v);
  } catch {
    /* storage blocked (private mode, quota): the key simply is not remembered */
  }
  notify();
}

export function clearOwnKey(): void {
  try {
    window.sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    /* nothing to clear */
  }
  notify();
}

/** Loose shape check so an obvious paste mistake is caught before a round trip. Gemini keys start with `AIza`. */
export function looksLikeGeminiKey(key: string): boolean {
  return /^AIza[\w-]{20,}$/.test(key.trim());
}

function subscribe(cb: () => void): () => void {
  listeners.add(cb);
  const onStorage = (e: StorageEvent) => {
    if (e.key === null || e.key === STORAGE_KEY) cb();
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(cb);
    window.removeEventListener("storage", onStorage);
  };
}

export interface OwnKey {
  /** The stored key, or null when the pooled demo keys are in use. */
  key: string | null;
  hasKey: boolean;
  save: (key: string) => void;
  clear: () => void;
}

/** Reactive view of the stored key; every subscriber re-renders when it is saved or cleared. */
export function useOwnKey(): OwnKey {
  const key = useSyncExternalStore(subscribe, getOwnKey, () => null);
  const save = useCallback((k: string) => setOwnKey(k), []);
  const clear = useCallback(() => clearOwnKey(), []);
  return { key, hasKey: key !== null, save, clear };
}
