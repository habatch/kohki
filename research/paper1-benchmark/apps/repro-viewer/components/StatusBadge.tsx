export function StatusBadge({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span
      className={
        'inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-medium ' +
        (ok
          ? 'border-success/40 bg-success/10 text-success'
          : 'border-warn/50 bg-warn/10 text-copper-300')
      }
    >
      <span className={'h-1.5 w-1.5 rounded-full ' + (ok ? 'bg-success' : 'bg-copper-300')} />
      {label}
    </span>
  );
}
