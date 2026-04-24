'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import type { ReproSummary, Trial } from '@/lib/types';
import { getImported } from '@/lib/local-store';
import { Histogram } from '@/components/Histogram';
import { StatusBadge } from '@/components/StatusBadge';

type Loaded = {
  id: string;
  summary: ReproSummary;
  trials: Trial[];
  prompt: string | null;
  origin: 'fs' | 'local';
};

export default function ExperimentDetail() {
  const params = useParams<{ id: string }>();
  const raw = decodeURIComponent(params.id);
  const [origin, id] = raw.split(':') as ['fs' | 'local', string];
  const [data, setData] = useState<Loaded | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<'overview' | 'distributions' | 'trials' | 'prompt'>('overview');
  const [search, setSearch] = useState('');

  useEffect(() => {
    (async () => {
      try {
        if (origin === 'fs') {
          const r = await fetch(`/api/experiments/${encodeURIComponent(id)}`);
          if (!r.ok) throw new Error(`fetch ${r.status}`);
          const j = await r.json();
          setData({ id, summary: j.summary, trials: j.trials, prompt: j.prompt, origin });
        } else {
          const e = await getImported(id);
          if (!e) throw new Error('not found in IndexedDB');
          setData({ id, summary: e.summary, trials: e.trials, prompt: e.prompt, origin });
        }
      } catch (e) {
        setError((e as Error).message);
      }
    })();
  }, [id, origin]);

  if (error) return <main className="p-8 text-danger">エラー: {error}</main>;
  if (!data) return <main className="p-8 text-muted-foreground">読み込み中…</main>;

  const { summary, trials } = data;
  const filteredTrials = search
    ? trials.filter((t) =>
        t.response_text.toLowerCase().includes(search.toLowerCase()) ||
        JSON.stringify(t.params).toLowerCase().includes(search.toLowerCase()))
    : trials;

  return (
    <main className="min-h-dvh">
      <header className="border-b border-border bg-surface/50">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <div>
            <Link href="/" className="text-[11px] text-muted-foreground hover:text-foreground">
              ← 一覧へ戻る
            </Link>
            <h1 className="mt-1 text-[15px] font-semibold tracking-tight font-mono">
              {data.id}
            </h1>
            <p className="text-[11px] text-muted-foreground mt-1">
              {summary.model} · temperature={summary.temperature} · seed_base={summary.seed_base}
            </p>
          </div>
          <button
            onClick={() => exportToFile(data)}
            className="inline-flex h-8 items-center gap-1.5 rounded border border-border bg-surface-2 px-3 text-[11px] hover:bg-ink-700"
          >
            ⇩ JSON エクスポート
          </button>
        </div>

        <nav className="mx-auto max-w-6xl px-6">
          <div className="flex gap-4 text-[12px]">
            {(['overview','distributions','trials','prompt'] as const).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={
                  'border-b-2 px-2 py-2 transition-colors ' +
                  (tab === t
                    ? 'border-depth-300 text-foreground'
                    : 'border-transparent text-muted-foreground hover:text-foreground')
                }
              >
                {tab_label(t)}
              </button>
            ))}
          </div>
        </nav>
      </header>

      <section className="mx-auto max-w-6xl px-6 py-6">
        {tab === 'overview' && <Overview summary={summary} prompt={data.prompt} />}
        {tab === 'distributions' && <Distributions summary={summary} />}
        {tab === 'prompt' && (
          <pre className="rounded border border-border bg-surface p-4 font-mono text-[12px] leading-relaxed whitespace-pre-wrap">
            {data.prompt || '(プロンプト未保存)'}
          </pre>
        )}
        {tab === 'trials' && (
          <TrialsList trials={filteredTrials} search={search} setSearch={setSearch} totalCount={trials.length} />
        )}
      </section>
    </main>
  );
}

function tab_label(t: string): string {
  return ({
    overview: '概要',
    distributions: '分布',
    trials: '試行 (生応答)',
    prompt: 'プロンプト',
  } as Record<string, string>)[t];
}

function Overview({ summary, prompt }: { summary: ReproSummary; prompt: string | null }) {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card label="試行数 (有効 / 全)" value={`${summary.n_valid} / ${summary.n_trials}`} sub={summary.n_parse_failures>0 ? `パース失敗 ${summary.n_parse_failures}件` : '全件パース OK'} />
        <Card label="ユニークな生応答" value={String(summary.unique_response_count)}
          sub={summary.fully_reproducible_response ? '完全再現' : 'テキスト揺れあり'}
          ok={summary.fully_reproducible_response} />
        <Card label="ユニークなパラメータ集合" value={String(summary.unique_param_set_count)}
          sub={summary.fully_reproducible_params ? '完全再現' : 'パラメータ揺れあり'}
          ok={summary.fully_reproducible_params} />
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card label="総 wall 時間 (秒)" value={String(summary.wall_seconds_total)}
          sub={`平均 ${summary.wall_seconds_per_trial_mean}s / 試行`} />
        <Card label="プロンプト SHA-256" value={summary.prompt_sha256.slice(0, 16) + '…'}
          sub="同 prompt → 同 hash" />
      </div>

      {(summary.stats.ecutwfc_Ry || summary.stats.mixing_beta) && (
        <div className="rounded-lg border border-border bg-surface p-4">
          <h3 className="text-[12px] font-semibold uppercase tracking-wider text-depth-200 mb-3">
            数値統計 (有効試行のみ)
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-[12px]">
              <thead className="text-muted-foreground">
                <tr>
                  <th className="text-left py-1">パラメータ</th>
                  <th className="text-right py-1">平均</th>
                  <th className="text-right py-1">標準偏差</th>
                  <th className="text-right py-1">最小</th>
                  <th className="text-right py-1">最大</th>
                  <th className="text-right py-1">N</th>
                </tr>
              </thead>
              <tbody className="font-mono">
                {([
                  ['ecutwfc Ry',  'ecutwfc_Ry'],
                  ['ecutrho Ry',  'ecutrho_Ry'],
                  ['degauss Ry',  'degauss_Ry'],
                  ['conv_thr Ry', 'conv_thr_Ry'],
                  ['mixing_beta', 'mixing_beta'],
                ] as const).map(([label, key]) => {
                  const s = summary.stats[key];
                  if (!s) return null;
                  return (
                    <tr key={key} className="border-t border-border">
                      <td className="py-1.5">{label}</td>
                      <td className="text-right tabular-nums py-1.5">{fmt(s.mean)}</td>
                      <td className="text-right tabular-nums py-1.5">{fmt(s.stdev)}</td>
                      <td className="text-right tabular-nums py-1.5">{fmt(s.min)}</td>
                      <td className="text-right tabular-nums py-1.5">{fmt(s.max)}</td>
                      <td className="text-right tabular-nums py-1.5 text-muted-foreground">{s.n}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

function Card({ label, value, sub, ok }: { label: string; value: string; sub?: string; ok?: boolean }) {
  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="flex items-baseline justify-between mb-1">
        <span className="text-[10.5px] uppercase tracking-wider text-muted-foreground">{label}</span>
        {typeof ok === 'boolean' && <StatusBadge ok={ok} label={ok ? 'OK' : 'NG'} />}
      </div>
      <div className="text-[20px] font-semibold tabular-nums font-mono">{value}</div>
      {sub && <div className="mt-1 text-[11px] text-muted-foreground">{sub}</div>}
    </div>
  );
}

function Distributions({ summary }: { summary: ReproSummary }) {
  const order = ['ecutwfc', 'ecutrho', 'kpoints', 'smearing', 'degauss', 'conv_thr', 'mixing_beta'];
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      {order.map((k) => {
        const counts = summary.param_distributions[k];
        if (!counts) return null;
        return <Histogram key={k} title={k} counts={counts} />;
      })}
    </div>
  );
}

function TrialsList({
  trials, search, setSearch, totalCount,
}: { trials: Trial[]; search: string; setSearch: (s: string) => void; totalCount: number }) {
  const [open, setOpen] = useState<number | null>(null);
  return (
    <div>
      <div className="flex items-center gap-3 mb-3">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="本文 / params を検索..."
          className="h-8 flex-1 rounded border border-border bg-surface px-3 text-[12px] font-mono"
        />
        <span className="text-[11px] text-muted-foreground">
          {trials.length} / {totalCount} 件表示
        </span>
      </div>
      <div className="rounded-lg border border-border bg-surface overflow-hidden">
        {trials.map((t) => (
          <div key={t.trial_index} className="border-b border-border last:border-0">
            <button
              onClick={() => setOpen(open === t.trial_index ? null : t.trial_index)}
              className="flex w-full items-center justify-between gap-4 px-4 py-2 text-left text-[12px] hover:bg-surface-2"
            >
              <span className="font-mono w-12 text-muted-foreground">#{String(t.trial_index).padStart(3, '0')}</span>
              <span className={'inline-flex h-2 w-2 rounded-full ' + (t.params_valid ? 'bg-success' : 'bg-copper-300')} />
              <span className="font-mono text-[10.5px] text-muted-foreground w-24 truncate">
                {t.response_sha256.slice(0, 12)}
              </span>
              <span className="font-mono flex-1 truncate text-[11px]">{t.response_text.slice(0, 100)}</span>
              <span className="text-muted-foreground text-[11px] tabular-nums">{t.wall_seconds.toFixed(1)}s</span>
            </button>
            {open === t.trial_index && (
              <div className="px-4 pb-3 grid grid-cols-1 md:grid-cols-2 gap-3 bg-surface-2/50">
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">生応答</div>
                  <pre className="rounded bg-ink-900 p-2 font-mono text-[11px] whitespace-pre-wrap">
                    {t.response_text}
                  </pre>
                </div>
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">parsed params</div>
                  <pre className="rounded bg-ink-900 p-2 font-mono text-[11px] whitespace-pre-wrap">
                    {JSON.stringify(t.params, null, 2)}
                  </pre>
                  <div className="mt-2 text-[10.5px] text-muted-foreground font-mono">
                    eval_count={t.ollama_eval_count}, eval_duration={t.ollama_eval_duration_s.toFixed(2)}s,
                    seed={String(t.seed)}, ts={t.timestamp_utc}
                  </div>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function fmt(v: number): string {
  if (Math.abs(v) < 1e-3 || Math.abs(v) > 1e4) return v.toExponential(3);
  return v.toFixed(4);
}

function exportToFile(data: Loaded) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${data.id}.json`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
