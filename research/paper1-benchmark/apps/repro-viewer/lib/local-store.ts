/**
 * ブラウザ side: import した実験を IndexedDB に保存する薄いラッパ。
 * 仕様:
 *   - DB 名 'repro-viewer'、object store 'experiments'、key = experiment id
 *   - 1 レコード = { id, importedAt, summary, trials, prompt, source: 'imported' }
 */
'use client';
import type { ReproSummary, Trial } from './types';

const DB_NAME = 'repro-viewer';
const STORE = 'experiments';

export type ImportedExperiment = {
  id: string;
  importedAt: string;
  source: 'imported';
  summary: ReproSummary;
  trials: Trial[];
  prompt: string | null;
};

function open(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE)) db.createObjectStore(STORE, { keyPath: 'id' });
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

export async function listImported(): Promise<ImportedExperiment[]> {
  const db = await open();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, 'readonly').objectStore(STORE).getAll();
    tx.onsuccess = () => resolve(tx.result as ImportedExperiment[]);
    tx.onerror = () => reject(tx.error);
  });
}

export async function getImported(id: string): Promise<ImportedExperiment | null> {
  const db = await open();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, 'readonly').objectStore(STORE).get(id);
    tx.onsuccess = () => resolve(tx.result || null);
    tx.onerror = () => reject(tx.error);
  });
}

export async function putImported(exp: ImportedExperiment): Promise<void> {
  const db = await open();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, 'readwrite').objectStore(STORE).put(exp);
    tx.onsuccess = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

export async function deleteImported(id: string): Promise<void> {
  const db = await open();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, 'readwrite').objectStore(STORE).delete(id);
    tx.onsuccess = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

export type ImportFormat =
  | { kind: 'summary-and-trials'; summary: ReproSummary; trials: Trial[]; prompt?: string };

export function detectFormat(json: unknown): ImportFormat | null {
  if (!json || typeof json !== 'object') return null;
  const obj = json as Record<string, unknown>;
  if (obj.summary && Array.isArray(obj.trials)) {
    return {
      kind: 'summary-and-trials',
      summary: obj.summary as ReproSummary,
      trials: obj.trials as Trial[],
      prompt: typeof obj.prompt === 'string' ? obj.prompt : undefined,
    };
  }
  return null;
}
