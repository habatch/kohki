'use client';

import { useEffect, useState, useRef } from 'react';
import Link from 'next/link';
import type { ExperimentMeta, Trial, ReproSummary } from '@/lib/types';
import { listImported, putImported, detectFormat, deleteImported } from '@/lib/local-store';
import { StatusBadge } from '@/components/StatusBadge';

type Row = ExperimentMeta & { _origin: 'fs' | 'local' };

export default function Home() {
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(true);
  const [importing, setImporting] = useState(false);
  const [importMsg, setImportMsg] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  async function refresh() {
    setLoading(true);
    const fsList: ExperimentMeta[] = await fetch('/api/experiments').then((r) => r.json());
    const local = await listImported();
    const merged: Row[] = [
      ...fsList.map((e) => ({ ...e, _origin: 'fs' as const })),
      ...local.map((e) => ({
        id: e.id,
        source: 'imported' as const,
        summary: e.summary,
        _origin: 'local' as const,
      })),
    ];
    setRows(merged);
    setLoading(false);
  }

  useEffect(() => { refresh(); }, []);

  async function handleImport(file: File) {
    setImporting(true);
    setImportMsg(null);
    try {
      const text = await file.text();
      const json = JSON.parse(text);
      const fmt = detectFormat(json);
      if (!fmt) throw new Error('未対応の形式です。{summary, trials, prompt?} を含む JSON が必要です');
      const id = (json.id as string) || `imported-${Date.now()}`;
      await putImported({
        id,
        importedAt: new Date().toISOString(),
        source: 'imported',
        summary: fmt.summary,
        trials: fmt.trials,
        prompt: fmt.prompt ?? null,
      });
      setImportMsg(`インポート成功: ${id}`);
      await refresh();
    } catch (e) {
      setImportMsg(`失敗: ${(e as Error).message}`);
    } finally {
      setImporting(false);
    }
  }

  async function handleDelete(id: string) {
    if (!confirm(`${id} をローカルから削除しますか？（filesystem 側は触りません）`)) return;
    await deleteImported(id);
    await refresh();
  }

  return (
    <main className="min-h-dvh">
      <header className="border-b border-border bg-surface/50 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <div>
            <h1 className="text-balance text-[15px] font-semibold tracking-tight">
              repro-viewer
            </h1>
            <p className="text-[11px] text-muted-foreground">
              Paper 1 — 再現性実験ログのブラウザ
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => fileInput.current?.click()}
              disabled={importing}
              className="inline-flex h-8 items-center gap-1.5 rounded border border-border bg-surface-2 px-3 text-[11px] hover:bg-ink-700"
            >
              {importing ? '…' : '⇪'} 実験ログを import
            </button>
            <input
              ref={fileInput}
              type="file"
              accept=".json,application/json"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void handleImport(f);
                e.target.value = '';
              }}
            />
          </div>
        </div>
      </header>

      <section className="mx-auto max-w-6xl px-6 py-6">
        {importMsg && (
          <p className="mb-4 rounded-md border border-depth-700/50 bg-depth-900/30 px-3 py-2 text-[12px]">
            {importMsg}
          </p>
        )}

        {loading ? (
          <p className="text-muted-foreground text-[12px]">読み込み中…</p>
        ) : rows.length === 0 ? (
          <div className="rounded-lg border-2 border-dashed border-border p-8 text-center">
            <h2 className="text-[14px] font-semibold mb-2">実験データがまだありません</h2>
            <p className="text-[12px] text-muted-foreground mb-4">
              実験を走らせるか（<code className="font-mono">experiments/repro-v1/run.py</code>）、
              既存の実験 JSON を上の「import」から取り込んでください。
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-[12px]">
              <thead className="bg-surface text-muted-foreground">
                <tr>
                  <th className="px-3 py-2 text-left">実験 ID</th>
                  <th className="px-3 py-2 text-left">出処</th>
                  <th className="px-3 py-2 text-left">モデル</th>
                  <th className="px-3 py-2 text-right">温度</th>
                  <th className="px-3 py-2 text-right">試行数</th>
                  <th className="px-3 py-2 text-left">テキスト一致</th>
                  <th className="px-3 py-2 text-left">パラメータ一致</th>
                  <th className="px-3 py-2 text-right">操作</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r._origin + ':' + r.id} className="border-t border-border hover:bg-surface/50">
                    <td className="px-3 py-2 font-mono">
                      <Link href={`/e/${r._origin}:${encodeURIComponent(r.id)}`} className="text-depth-300 hover:underline">
                        {r.id}
                      </Link>
                    </td>
                    <td className="px-3 py-2">
                      <span className="font-mono text-[10.5px] text-muted-foreground">
                        {r._origin === 'fs' ? 'filesystem' : 'imported'}
                      </span>
                    </td>
                    <td className="px-3 py-2 font-mono">{r.summary.model}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{r.summary.temperature}</td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {r.summary.n_trials}
                      {r.summary.n_parse_failures > 0 && (
                        <span className="ml-1 text-copper-300">(失敗 {r.summary.n_parse_failures})</span>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      <StatusBadge ok={r.summary.fully_reproducible_response}
                        label={`${r.summary.unique_response_count} ユニーク`} />
                    </td>
                    <td className="px-3 py-2">
                      <StatusBadge ok={r.summary.fully_reproducible_params}
                        label={`${r.summary.unique_param_set_count} ユニーク`} />
                    </td>
                    <td className="px-3 py-2 text-right">
                      {r._origin === 'local' && (
                        <button
                          onClick={() => handleDelete(r.id)}
                          className="text-[11px] text-copper-300 hover:underline"
                        >
                          削除
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}
