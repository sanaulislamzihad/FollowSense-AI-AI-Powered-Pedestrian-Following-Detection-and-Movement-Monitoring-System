import { STATUS_STYLE } from '../lib/format'

export function PageHeader({ title, subtitle, children }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4 mb-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">{title}</h1>
        {subtitle && <p className="text-sm text-slate-500 mt-1">{subtitle}</p>}
      </div>
      <div className="flex flex-wrap gap-2">{children}</div>
    </div>
  )
}

export function StatCard({ label, value, hint, icon: Icon, tone = 'brand' }) {
  const tones = {
    brand: 'bg-brand-50 text-brand-700',
    rose: 'bg-rose-50 text-rose-600',
    amber: 'bg-amber-50 text-amber-600',
    sky: 'bg-sky-50 text-sky-600',
    green: 'bg-emerald-50 text-emerald-600',
  }
  return (
    <div className="card card-pad flex items-start gap-4">
      {Icon && <div className={`h-11 w-11 rounded-xl grid place-items-center ${tones[tone]}`}><Icon size={22} /></div>}
      <div className="min-w-0">
        <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</div>
        <div className="text-2xl font-bold text-slate-900 mt-0.5 tabular-nums">{value ?? '-'}</div>
        {hint && <div className="text-xs text-slate-500 mt-0.5">{hint}</div>}
      </div>
    </div>
  )
}

export function Badge({ children, className = '', status }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold capitalize ${status ? STATUS_STYLE[status] || 'bg-slate-100 text-slate-700' : ''} ${className}`}>
      {children ?? status}
    </span>
  )
}

export function Progress({ value, className = '' }) {
  return (
    <div className={`h-2 rounded-full bg-slate-200 overflow-hidden ${className}`}>
      <div className="h-full bg-brand-600 transition-all" style={{ width: `${Math.round((value || 0) * 100)}%` }} />
    </div>
  )
}

export function Empty({ icon: Icon, title, children }) {
  return (
    <div className="text-center py-12 px-4">
      {Icon && <Icon className="mx-auto h-10 w-10 text-slate-300" />}
      <div className="mt-3 font-semibold text-slate-700">{title}</div>
      {children && <div className="text-sm text-slate-500 mt-1">{children}</div>}
    </div>
  )
}

export function Card({ title, actions, children, className = '', pad = true }) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <div className="flex items-center justify-between gap-3 px-5 py-3.5 border-b border-slate-100">
          <h2 className="font-semibold text-slate-800">{title}</h2>
          <div className="flex gap-2">{actions}</div>
        </div>
      )}
      <div className={pad ? 'p-5' : ''}>{children}</div>
    </section>
  )
}

export function JobSelect({ jobs, value, onChange, filter }) {
  const list = (jobs || []).filter(filter || (() => true))
  return (
    <select className="input w-auto min-w-[260px]" value={value || ''} onChange={(e) => onChange(Number(e.target.value))}>
      {!list.length && <option value="">No analyses yet</option>}
      {list.map((j) => (
        <option key={j.id} value={j.id}>
          #{j.id} · {j.source_name} · {j.status}
        </option>
      ))}
    </select>
  )
}

export function Modal({ open, onClose, title, children, wide }) {
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 bg-black/50 grid place-items-center p-4" onClick={onClose}>
      <div className={`card w-full ${wide ? 'max-w-5xl' : 'max-w-lg'} max-h-[92vh] overflow-auto`} onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-slate-100 sticky top-0 bg-white">
          <h3 className="font-semibold">{title}</h3>
          <button className="text-slate-400 hover:text-slate-600 text-xl leading-none" onClick={onClose}>×</button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  )
}
