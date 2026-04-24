/**
 * サーバ専用 — ファイルシステム上の experiments/ ディレクトリを scan して
 * 実験データを返すユーティリティ。
 *
 * 期待構造:
 *   experiments/
 *     <id>/
 *       results/summary.json
 *       results/summary.jsonl   (任意)
 *       trials/{0000..NNNN}.json
 *       prompts/v*.txt          (任意)
 */
import { promises as fs } from 'node:fs';
import path from 'node:path';
import type { ReproSummary, Trial } from '@/lib/types';

// monorepo 直下の experiments/ を root とする
const EXP_ROOT = path.resolve(process.cwd(), '..', '..', 'experiments');

export async function listExperimentIds(): Promise<string[]> {
  try {
    const entries = await fs.readdir(EXP_ROOT, { withFileTypes: true });
    const out: string[] = [];
    for (const e of entries) {
      if (!e.isDirectory()) continue;
      const summary = path.join(EXP_ROOT, e.name, 'results', 'summary.json');
      try {
        await fs.access(summary);
        out.push(e.name);
      } catch { /* skip */ }
    }
    return out.sort();
  } catch {
    return [];
  }
}

export async function loadSummary(id: string): Promise<ReproSummary | null> {
  try {
    const buf = await fs.readFile(path.join(EXP_ROOT, id, 'results', 'summary.json'), 'utf8');
    return JSON.parse(buf) as ReproSummary;
  } catch {
    return null;
  }
}

export async function loadTrials(id: string): Promise<Trial[]> {
  const dir = path.join(EXP_ROOT, id, 'trials');
  try {
    const files = (await fs.readdir(dir)).filter((f) => f.endsWith('.json')).sort();
    const out: Trial[] = [];
    for (const f of files) {
      const buf = await fs.readFile(path.join(dir, f), 'utf8');
      out.push(JSON.parse(buf) as Trial);
    }
    return out;
  } catch {
    return [];
  }
}

export async function loadPrompt(id: string): Promise<string | null> {
  const dir = path.join(EXP_ROOT, id, 'prompts');
  try {
    const files = (await fs.readdir(dir)).filter((f) => f.endsWith('.txt')).sort();
    if (files.length === 0) return null;
    return await fs.readFile(path.join(dir, files[files.length - 1]), 'utf8');
  } catch {
    return null;
  }
}
