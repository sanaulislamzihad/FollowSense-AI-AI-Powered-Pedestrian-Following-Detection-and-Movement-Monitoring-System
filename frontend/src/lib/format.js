export const fmtTime = (sec) => {
  if (sec == null || Number.isNaN(sec)) return '-'
  const m = Math.floor(sec / 60)
  const s = (sec % 60).toFixed(1).padStart(4, '0')
  return `${String(m).padStart(2, '0')}:${s}`
}

export const fmtPct = (v) => (v == null ? '-' : `${Math.round(v * 100)}%`)
export const fmtNum = (v, d = 2) => (v == null ? '-' : Number(v).toFixed(d))

export const fmtBytes = (b) => {
  if (!b) return '0 B'
  const u = ['B', 'KB', 'MB', 'GB']
  const i = Math.min(u.length - 1, Math.floor(Math.log(b) / Math.log(1024)))
  return `${(b / 1024 ** i).toFixed(i ? 1 : 0)} ${u[i]}`
}

export const fmtDate = (d) => (d ? new Date(d).toLocaleString() : '-')

export const REL_LABELS = {
  potential_following: 'Potential following',
  same_direction: 'Same direction',
  group_walking: 'Group walking',
  no_following: 'No following',
  insufficient_evidence: 'Insufficient evidence',
}

export const REL_COLORS = {
  potential_following: '#e11d48',
  group_walking: '#16a34a',
  same_direction: '#2563eb',
  no_following: '#94a3b8',
  insufficient_evidence: '#cbd5e1',
}

export const LEVEL_STYLE = {
  normal: 'bg-emerald-100 text-emerald-800',
  elevated: 'bg-amber-100 text-amber-800',
  critical: 'bg-rose-100 text-rose-800',
}

export const STATUS_STYLE = {
  new: 'bg-sky-100 text-sky-800',
  confirmed: 'bg-rose-100 text-rose-800',
  dismissed: 'bg-slate-200 text-slate-600',
  reviewed: 'bg-emerald-100 text-emerald-800',
  running: 'bg-sky-100 text-sky-800',
  queued: 'bg-amber-100 text-amber-800',
  completed: 'bg-emerald-100 text-emerald-800',
  failed: 'bg-rose-100 text-rose-800',
  stopped: 'bg-slate-200 text-slate-600',
}
