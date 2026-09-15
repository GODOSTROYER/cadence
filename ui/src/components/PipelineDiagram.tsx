/** Inline SVG of the pipeline (ui/DESIGN.md §8): message → rules → BM25 retrieval → Gemini → decision. Shared by the landing and Method pages. */
import { fixed } from "@/lib/format";
import { TOKENS } from "@/lib/palette";

interface Node {
  id: string;
  title: string;
  sub: string;
  accent: string;
}

/** Inline SVG: message → rules → BM25 retrieval → Gemini → decision, with the rules' forced-escalate shortcut. */
export function PipelineDiagram({ threshold, k = 6 }: { threshold: number; k?: number }) {
  const nodes: Node[] = [
    { id: "message", title: "Customer tweet", sub: "cleaned · handles → @user · links → <url>", accent: TOKENS.muted },
    { id: "rules", title: "Rules", sub: "regex flags · money / security / legal / churn / media-only", accent: TOKENS.amber },
    { id: "retrieve", title: "BM25 retrieval", sub: `top-${k} historical threads · own thread excluded`, accent: TOKENS.sky },
    { id: "llm", title: "Gemini", sub: "structured JSON · intent, sentiment, reply, decision", accent: TOKENS.violet },
    { id: "decide", title: "Decision", sub: `escalate if rules force it, the model says so, or confidence < ${fixed(threshold, 2)}`, accent: TOKENS.green },
  ];
  const w = 1040;
  const h = 250;
  const boxW = 176;
  const boxH = 74;
  const gap = (w - nodes.length * boxW) / (nodes.length - 1);
  const y = 96;
  const x = (i: number) => i * (boxW + gap);

  return (
    <div className="overflow-x-auto">
      <svg viewBox={`0 0 ${w} ${h}`} className="h-auto w-full min-w-[820px]" role="img" aria-label="Pipeline: a customer tweet passes through deterministic rules, BM25 retrieval over historical threads, a Gemini structured call, and a decision step. Rules can force escalation directly.">
        <defs>
          <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill={TOKENS.faint} />
          </marker>
          <marker id="arrow-amber" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill={TOKENS.amber} />
          </marker>
        </defs>

        {nodes.slice(0, -1).map((_, i) => (
          <line key={i} x1={x(i) + boxW} y1={y + boxH / 2} x2={x(i + 1) - 2} y2={y + boxH / 2} stroke={TOKENS.faint} strokeWidth={1.25} markerEnd="url(#arrow)" />
        ))}

        {/* Forced-escalate shortcut: rules → decision, above the main line. */}
        <path
          d={`M ${x(1) + boxW / 2} ${y} C ${x(1) + boxW / 2} ${y - 60}, ${x(4) + boxW / 2} ${y - 60}, ${x(4) + boxW / 2} ${y - 2}`}
          fill="none"
          stroke={TOKENS.amber}
          strokeWidth={1.25}
          strokeDasharray="4 4"
          markerEnd="url(#arrow-amber)"
        />
        <text x={(x(1) + x(4) + boxW) / 2} y={y - 50} textAnchor="middle" fontSize={12} fontFamily="var(--font-mono)" fill={TOKENS.amber}>
          rule fires → escalate, model cannot override
        </text>

        {/* Evidence feeding the prompt. */}
        <text x={x(3) + boxW / 2} y={y + boxH + 34} textAnchor="middle" fontSize={12} fontFamily="var(--font-mono)" fill={TOKENS.faint}>
          prompt = brand voice notes + taxonomy + policy + {k} threads with their replies
        </text>
        <line x1={x(3) + boxW / 2} y1={y + boxH} x2={x(3) + boxW / 2} y2={y + boxH + 20} stroke={TOKENS.border} strokeWidth={1} />

        {nodes.map((n, i) => (
          <g key={n.id}>
            <rect x={x(i)} y={y} width={boxW} height={boxH} rx={8} fill={TOKENS.surface} stroke={TOKENS.borderStrong} />
            <rect x={x(i)} y={y + 14} width={2} height={boxH - 28} rx={1} fill={n.accent} />
            <text x={x(i) + 16} y={y + 30} fontSize={15} fontFamily="var(--font-display)" fill={TOKENS.text}>
              {n.title}
            </text>
            <foreignObject x={x(i) + 16} y={y + 38} width={boxW - 26} height={boxH - 42}>
              <p style={{ margin: 0, fontSize: 11, lineHeight: 1.35, color: TOKENS.muted, fontFamily: "var(--font-mono)" }}>{n.sub}</p>
            </foreignObject>
          </g>
        ))}

        <text x={0} y={h - 12} fontSize={12} fontFamily="var(--font-sans)" fill={TOKENS.faint}>
          Output: intent + confidence, sentiment, a ≤280-char reply signed /AI, cited thread ids, decision + one-sentence reason, rule flags, latency.
        </text>
      </svg>
    </div>
  );
}
