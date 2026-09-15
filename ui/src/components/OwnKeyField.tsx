import { KeyRound } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

import { Chip } from "@/components/Chip";
import { agentErrorKind } from "@/lib/api";
import { cx } from "@/lib/cx";
import { looksLikeGeminiKey, useOwnKey } from "@/lib/ownKey";

const AI_STUDIO = "https://aistudio.google.com/apikey";

export interface OwnKeyFieldProps {
  /** The last agent error, if any: a quota (429) or invalid-key (502) failure adds an inline note. */
  error?: unknown;
  /** Tighter spacing for the landing-page mini demo. */
  compact?: boolean;
  className?: string;
}

/** What the last failure means for the key in use, in one line. */
function errorNote(error: unknown, hasKey: boolean): { text: string; tone: "amber" | "rose" } | null {
  const kind = agentErrorKind(error);
  if (kind === "quota") {
    return hasKey
      ? { text: "Your key is out of quota (the free tier resets daily). Try another, or clear it to go back to the pooled keys.", tone: "amber" }
      : { text: "The pooled demo keys are out of quota for today. Paste your own free key to keep going.", tone: "amber" };
  }
  if (kind === "invalid-key") {
    return hasKey
      ? { text: "Gemini rejected your key as invalid. Check it in AI Studio, or clear it to go back to the pooled keys.", tone: "rose" }
      : { text: "Gemini rejected the deployment's key. That one is on us; try again later, or paste your own.", tone: "rose" };
  }
  return null;
}

/**
 * A collapsed one-liner under the composer ("Using pooled demo keys · use your own key") that opens into a
 * password field for the visitor's own Gemini key. The key stays in sessionStorage (see lib/ownKey.ts).
 */
export function OwnKeyField({ error, compact = false, className }: OwnKeyFieldProps) {
  const { hasKey, save, clear } = useOwnKey();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [warning, setWarning] = useState<string | null>(null);
  const input = useRef<HTMLInputElement | null>(null);
  const panelId = useId();
  const note = errorNote(error, hasKey);

  // A quota failure on the pooled keys is exactly the moment to show the field.
  useEffect(() => {
    if (agentErrorKind(error) === "quota" && !hasKey) setOpen(true);
  }, [error, hasKey]);

  useEffect(() => {
    if (open) input.current?.focus();
  }, [open]);

  const close = () => {
    setOpen(false);
    setDraft("");
    setWarning(null);
  };

  // Not a nested <form>: the field sits inside the composer's form, so Enter and Save are handled by hand.
  const submit = () => {
    const v = draft.trim();
    if (!v) return;
    if (!looksLikeGeminiKey(v) && warning === null) {
      setWarning("That does not look like a Gemini key (they start with AIza). Save anyway?");
      return;
    }
    save(v);
    close();
  };

  const clearKey = () => {
    clear();
    close();
  };

  return (
    <div className={cx("flex flex-col", compact ? "gap-2" : "gap-3", className)}>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[12px] leading-5">
        <KeyRound className="size-3.5 shrink-0 text-faint" aria-hidden="true" />
        {hasKey ? (
          <>
            <Chip size="sm" tone="green" dot mono title="Your own Gemini key is sent with each run">
              your key
            </Chip>
            <span className="text-faint">this tab only, sent with your requests</span>
            {/* Separators travel with their links so a wrap never strands a lone dot. */}
            {!open && (
              <span className="whitespace-nowrap">
                <span className="text-faint" aria-hidden="true">
                  ·{" "}
                </span>
                <button type="button" className="link text-muted" onClick={() => setOpen(true)} aria-expanded={open} aria-controls={panelId}>
                  change
                </button>
              </span>
            )}
            <span className="whitespace-nowrap">
              <span className="text-faint" aria-hidden="true">
                ·{" "}
              </span>
              <button type="button" className="link text-muted" onClick={clearKey}>
                clear
              </button>
            </span>
          </>
        ) : (
          <>
            <span className="text-faint">Using pooled demo keys</span>
            <span className="whitespace-nowrap">
              <span className="text-faint" aria-hidden="true">
                ·{" "}
              </span>
              <button
                type="button"
                className="link text-muted"
                onClick={() => (open ? close() : setOpen(true))}
                aria-expanded={open}
                aria-controls={panelId}
              >
                use your own key
              </button>
            </span>
          </>
        )}
      </div>

      {note && (
        <p role="alert" className={cx("text-[12px] leading-5", note.tone === "rose" ? "text-rose" : "text-amber")}>
          {note.text}
        </p>
      )}

      {open && (
        <div id={panelId} className={cx("flex flex-col rounded-md border border-border bg-bg", compact ? "gap-2.5 px-3 py-3" : "gap-3 px-4 py-4")}>
          <p className={cx("text-[12px] leading-relaxed text-muted", !compact && "max-w-[64ch]")}>
            This demo runs on five free-tier Gemini keys pooled together (yes, five: the free tier is about twenty thinking-model calls a day per key,
            which is why the evaluation ran on Flash-Lite). If they run dry, or you would rather not share, paste your own free key from{" "}
            <a href={AI_STUDIO} target="_blank" rel="noreferrer" className="link">
              AI Studio
            </a>
            . It stays in this browser tab and is sent only with your requests; it is never stored server-side.
          </p>
          <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Your Gemini key">
            <label htmlFor={`${panelId}-key`} className="sr-only">
              Gemini API key
            </label>
            <input
              id={`${panelId}-key`}
              ref={input}
              type="password"
              autoComplete="off"
              spellCheck={false}
              value={draft}
              onChange={(e) => {
                setDraft(e.target.value);
                setWarning(null);
              }}
              onKeyDown={(e) => {
                if (e.key === "Escape") close();
                if (e.key === "Enter") {
                  e.preventDefault();
                  submit();
                }
              }}
              placeholder={hasKey ? "paste a different key (AIza…)" : "AIza…"}
              className="t-mono h-9 min-w-0 flex-1 basis-[220px] rounded-md border border-border-strong bg-surface px-3 text-[13px] text-text placeholder:text-faint"
            />
            <div className="flex items-center gap-1.5">
              <button type="button" className="btn btn-sm btn-primary" onClick={submit} disabled={!draft.trim()}>
                {warning ? "Save anyway" : "Save"}
              </button>
              <button type="button" className="btn btn-sm btn-ghost" onClick={close}>
                Cancel
              </button>
            </div>
          </div>
          {warning && <p className="text-[12px] leading-5 text-amber">{warning}</p>}
        </div>
      )}
    </div>
  );
}
