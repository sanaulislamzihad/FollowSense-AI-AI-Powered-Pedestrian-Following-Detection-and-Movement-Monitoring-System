import { AlertTriangle, Users, X } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useRealtime } from '../lib/realtime'

export default function Toasts() {
  const { toasts, dismiss } = useRealtime()
  const nav = useNavigate()
  return (
    <div className="fixed bottom-4 right-4 z-50 space-y-2 w-[min(380px,calc(100vw-2rem))]">
      {toasts.map((t) => (
        <div key={t.id} className={`card p-3.5 flex gap-3 items-start border-l-4 ${t.kind === 'following' ? 'border-l-rose-500' : 'border-l-amber-500'} animate-[fadeIn_.2s]`}>
          {t.kind === 'following'
            ? <AlertTriangle className="h-5 w-5 text-rose-500 shrink-0 mt-0.5" />
            : <Users className="h-5 w-5 text-amber-500 shrink-0 mt-0.5" />}
          <button className="text-left flex-1" onClick={() => { nav(t.kind === 'following' ? '/events' : '/crowd'); dismiss(t.id) }}>
            <div className="text-sm font-semibold text-slate-800">
              {t.kind === 'following' ? 'Potential following detected' : 'Crowd alert'}
            </div>
            <div className="text-sm text-slate-600">{t.text}</div>
            <div className="text-xs text-slate-400 mt-0.5">Job #{t.job_id} · click to review</div>
          </button>
          <button onClick={() => dismiss(t.id)} className="text-slate-400 hover:text-slate-600"><X className="h-4 w-4" /></button>
        </div>
      ))}
    </div>
  )
}
