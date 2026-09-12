/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** "1" enables static mode (reads public/data/*.json, disables the live agent). */
  readonly VITE_STATIC?: string;
  readonly VITE_LIVE_HANDLE?: string;
  readonly VITE_BASE?: string;
}
