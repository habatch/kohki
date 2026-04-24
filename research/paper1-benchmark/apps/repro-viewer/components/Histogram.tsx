'use client';

/**
 * シンプルな水平 bar 表示の度数分布。Recharts などを入れずに stdlib React + SVG で。
 */
export function Histogram({
  title,
  counts,
}: {
  title: string;
  counts: Record<string, number>;
}) {
  const entries = Object.entries(counts);
  const total = entries.reduce((a, [, v]) => a + v, 0);
  const sorted = entries.sort((a, b) => b[1] - a[1]);
  const max = Math.max(...entries.map(([, v]) => v), 1);
  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h3 className="mb-2 text-[12px] font-semibold tracking-wider uppercase text-depth-200">
        {title}
      </h3>
      <p className="mb-3 text-[11px] text-muted-foreground">
        ユニーク値 {sorted.length} 種 / 合計 {total} 試行
      </p>
      <div className="space-y-1.5">
        {sorted.map(([k, v]) => (
          <div key={k} className="flex items-center gap-2 text-[11px] font-mono">
            <span className="w-32 shrink-0 truncate" title={k}>{k}</span>
            <div className="relative h-4 flex-1 rounded bg-ink-800/60">
              <div
                className="absolute inset-y-0 left-0 rounded bg-depth-400/70"
                style={{ width: `${(v / max) * 100}%` }}
              />
            </div>
            <span className="w-16 shrink-0 text-right tabular-nums text-muted-foreground">
              {v} <span className="opacity-60">({((v / total) * 100).toFixed(1)}%)</span>
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
