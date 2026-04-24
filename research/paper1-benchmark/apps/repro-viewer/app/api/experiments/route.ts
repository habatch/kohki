import { NextResponse } from 'next/server';
import { listExperimentIds, loadSummary } from '@/lib/server-fs';
import type { ExperimentMeta } from '@/lib/types';

export async function GET() {
  const ids = await listExperimentIds();
  const out: ExperimentMeta[] = [];
  for (const id of ids) {
    const s = await loadSummary(id);
    if (s) out.push({ id, source: 'filesystem', summary: s });
  }
  return NextResponse.json(out);
}
