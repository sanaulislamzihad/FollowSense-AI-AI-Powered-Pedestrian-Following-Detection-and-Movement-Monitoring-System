import { NavLink, Outlet } from 'react-router-dom'
import { useState } from 'react'
import {
  Activity, BarChart3, Footprints, LayoutDashboard, Menu, MonitorPlay, Settings, Users, Video, X,
} from 'lucide-react'
import { useRealtime } from '../lib/realtime'
import Toasts from './Toasts'

const NAV = [
  { to: '/', label: 'Overview', icon: LayoutDashboard, end: true },
  { to: '/monitor', label: 'Live Monitoring', icon: MonitorPlay },
  { to: '/events', label: 'Following Events', icon: Footprints },
  { to: '/crowd', label: 'Crowd Management', icon: Users },
  { to: '/analytics', label: 'Movement Analytics', icon: BarChart3 },
  { to: '/videos', label: 'Video Management', icon: Video },
  { to: '/settings', label: 'Settings', icon: Settings },
]

export default function Layout() {
  const { connected } = useRealtime()
  const [open, setOpen] = useState(false)
  return (
    <div className="min-h-screen flex">
      <aside className={`fixed inset-y-0 left-0 z-40 w-64 bg-ink-900 text-slate-300 flex flex-col transition-transform lg:translate-x-0 ${open ? 'translate-x-0' : '-translate-x-full'}`}>
        <div className="flex items-center gap-3 px-5 h-16 border-b border-white/5">
          <div className="h-9 w-9 rounded-lg bg-brand-700 grid place-items-center">
            <Activity className="h-5 w-5 text-white" />
          </div>
          <div>
            <div className="text-white font-semibold leading-tight">FollowSense AI</div>
            <div className="text-[11px] text-slate-400">Movement monitoring</div>
          </div>
          <button className="ml-auto lg:hidden" onClick={() => setOpen(false)}><X className="h-5 w-5" /></button>
        </div>
        <nav className="flex-1 px-3 py-4 space-y-1">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end} onClick={() => setOpen(false)}
              className={({ isActive }) => `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition ${isActive ? 'bg-brand-700/90 text-white' : 'hover:bg-white/5 hover:text-white'}`}>
              <Icon className="h-4.5 w-4.5 shrink-0" size={18} />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="px-5 py-4 border-t border-white/5 text-xs flex items-center gap-2">
          <span className={`h-2 w-2 rounded-full ${connected ? 'bg-emerald-400' : 'bg-rose-400 animate-pulse'}`} />
          {connected ? 'Real-time connected' : 'Reconnecting…'}
        </div>
      </aside>
      {open && <div className="fixed inset-0 z-30 bg-black/40 lg:hidden" onClick={() => setOpen(false)} />}
      <div className="flex-1 lg:pl-64 min-w-0">
        <header className="lg:hidden h-14 bg-white border-b border-slate-200 flex items-center px-4 gap-3 sticky top-0 z-20">
          <button onClick={() => setOpen(true)}><Menu className="h-5 w-5" /></button>
          <span className="font-semibold">FollowSense AI</span>
        </header>
        <main className="p-4 sm:p-6 lg:p-8 max-w-[1500px] mx-auto">
          <Outlet />
        </main>
      </div>
      <Toasts />
    </div>
  )
}
