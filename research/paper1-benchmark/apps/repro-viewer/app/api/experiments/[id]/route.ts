import { NextResponse } from 'next/server';
import { loadSummary, loadPrompt, loadTrials } from '@/lib/server-fs';

export async function GET(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const summary = await loadSummary(id);
  if (!summary) return NextResponse.json({ error: 'not found' }, { status: 404 });
  const [prompt, trials] = await Promise.all([loadPrompt(id), loadTrials(id)]);
  return NextResponse.json({ id, summary, prompt, trials });
}
