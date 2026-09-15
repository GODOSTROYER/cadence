import { lazy, type ComponentType } from "react";

/**
 * `React.lazy` that survives a redeploy.
 *
 * Chunks are content-hashed and deployments are immutable, so a tab that loaded the previous `index.html`
 * asks for chunk files that no longer exist when it first visits a lazy route ("Failed to fetch dynamically
 * imported module"). The fix is a single hard reload, which fetches the current shell; a sessionStorage flag
 * makes sure a genuinely broken chunk does not reload forever.
 */
export function lazyRetry<T extends ComponentType<unknown>>(
  factory: () => Promise<{ default: T }>,
  key: string,
) {
  const flag = `cadence.chunk-reload:${key}`;
  return lazy(async () => {
    try {
      const mod = await factory();
      try {
        sessionStorage.removeItem(flag);
      } catch {
        /* storage may be unavailable */
      }
      return mod;
    } catch (error) {
      let alreadyReloaded = false;
      try {
        alreadyReloaded = sessionStorage.getItem(flag) === "1";
        if (!alreadyReloaded) sessionStorage.setItem(flag, "1");
      } catch {
        /* storage may be unavailable */
      }
      if (!alreadyReloaded && isChunkLoadError(error)) {
        window.location.reload();
        return new Promise<{ default: T }>(() => {}); // the reload takes over
      }
      throw error;
    }
  });
}

function isChunkLoadError(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error);
  return /dynamically imported module|Loading chunk|Importing a module script failed|error loading dynamically/i.test(
    message,
  );
}
