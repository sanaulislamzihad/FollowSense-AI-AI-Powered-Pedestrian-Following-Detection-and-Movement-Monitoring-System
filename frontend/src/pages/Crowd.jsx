import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Check, Download, Flame, Gauge, Image as ImageIcon, Users, X } from 'lucide-react'
import { api, url } from '../lib/api'
import { useLive, useRealtime } from '../lib/realtime'
import { Badge, Card, Empty, JobSelect, Modal, PageHeader, StatCard } from '../components/ui'
import { CrowdTimeline } from '../components/charts'
import SceneCanvas from '../components/SceneCanvas'
import { LEVEL_STYLE, fmtTime } from '../lib/format'

export default function Crowd() {
  const [params, setParams] = useSearchParams()
  const { data: jobs } = useLive(() => api.jobs(), [])
  const { data: settings } = useLive(api.settings, [])
  const { progress } = useRealtime()
  const [jobId, setJobId] = useState(Number(params.get('job')) || null)
  const { data: an, reload } = useLive(() => (jobId ? api.analytics(jobId) : Promise.resolve(null)), [jobId])
  const [snap, setSnap] = useState(null)

  useEffect(() => {
    if (!jobId && jobs?.length) setJobId((jobs.find((j) => j.status === 'completed') || jobs[0]).id)
  }, [jobs, jobId])
  useEffect(() => { if (jobId) setParams({ job: jobId }, { replace: true }) }, [jobId, setParams])

  const s = settings?.values || {}
  const crowd = an?.crowd || {}
  const lvl = crowd.level_seconds || {}
  const totalLvl = (lvl.normal || 0) + (lvl.elevated || 0) + (lvl.critical || 0)
  const running = (jobs || []).filter((j) => j.status === 'running')

  const review = async (c, status) => { await api.reviewCrowd(c.id, { status }); reload() }

  return (
    <>
      <PageHeader title="Crowd Management" subtitle="People counts, crowd levels, congestion zones and overcrowding alerts">
        <JobSelect jobs={jobs} value={jobId} onChange={setJobId} />
        {jobId && <a className="btn-ghost" href={url(`/api/events/crowd/export.csv?job_id=${jobId}`)}><Download size={16} /> CSV</a>}
      </PageHeader>

      {running.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 mb-6">
          {running.map((j) => {
            const p = progress[j.id] || j.live || {}
            return (
              <div key={j.id} className="card card-pad">
                <div className="flex items-center justify-between">
                  <div className="text-sm font-semibold text-slate-700 truncate">Live · #{j.id} {j.source_name}</div>
                  <span className={`rounded px-2 py-0.5 text-xs font-bold uppercase ${LEVEL_STYLE[p.level] || 'bg-slate-100'}`}>{p.level || '…'}</span>
                </div>
                <div className="flex items-end gap-3 mt-3">
                  <div className="text-4xl font-bold tabular-nums">{p.count ?? 0}</div>
                  <div className="text-sm text-slate-500 pb-1">people in view · {p.clusters ?? 0} congestion zone(s)</div>
                </div>
                <CapacityBar count={p.count || 0} warning={s.crowd_warning_count} critical={s.crowd_critical_count} />
              </div>
            )
          })}
        </div>
      )}

      {!an ? <Card><Empty icon={Users} title="Select a completed analysis" /></Card> : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
            <StatCard icon={Users} label="Peak people in view" value={crowd.peak_count ?? an.job.peak_count} hint={crowd.peak_time != null ? `at ${fmtTime(crowd.peak_time)}` : ''} />
            <StatCard icon={Gauge} tone="sky" label="Average in view" value={crowd.average_count ?? an.job.average_count} hint={`${an.job.total_pedestrians} unique track IDs`} />
            <StatCard icon={Flame} tone="amber" label="Congestion alerts" value={an.crowd_events.filter((c) => c.crowd_type === 'congestion').length} hint={`≥ ${s.congestion_min_people} people within ${s.congestion_distance} body heights`} />
            <StatCard icon={Users} tone="rose" label="Overcrowding alerts" value={an.crowd_events.filter((c) => c.crowd_type === 'overcrowding').length} hint={`≥ ${s.crowd_critical_count} people for ${s.crowd_alert_min_duration_sec}s`} />
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-3 gap-6 mt-6">
            <Card title="People count over time" className="xl:col-span-2">
              <CrowdTimeline timeline={crowd.timeline} warning={s.crowd_warning_count} critical={s.crowd_critical_count} />
            </Card>
            <Card title="Time at each crowd level">
              <div className="space-y-4">
                {['normal', 'elevated', 'critical'].map((k) => (
                  <div key={k}>
                    <div className="flex justify-between text-sm mb-1">
                      <span className={`rounded px-2 py-0.5 text-xs font-bold uppercase ${LEVEL_STYLE[k]}`}>{k}</span>
                      <span className="tabular-nums text-slate-600">{(lvl[k] || 0).toFixed(1)}s · {totalLvl ? Math.round(100 * (lvl[k] || 0) / totalLvl) : 0}%</span>
                    </div>
                    <div className="h-2 rounded-full bg-slate-100 overflow-hidden">
                      <div className={`h-full ${k === 'normal' ? 'bg-emerald-500' : k === 'elevated' ? 'bg-amber-500' : 'bg-rose-500'}`} style={{ width: `${totalLvl ? (100 * (lvl[k] || 0)) / totalLvl : 0}%` }} />
                    </div>
                  </div>
                ))}
                <p className="text-xs text-slate-500 pt-2">Levels: elevated ≥ {s.crowd_warning_count}, critical ≥ {s.crowd_critical_count} people in view (change in Settings to match each camera’s capacity).</p>
              </div>
            </Card>
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-2 gap-6 mt-6">
            <Card title="Crowd density heatmap">
              <SceneCanvas jobId={jobId} width={an.width} height={an.height} heatmap={an.heatmap} showTracks={false} />
              {an.heatmap?.zones?.length > 0 && (
                <p className="text-xs text-slate-500 mt-2">{an.heatmap.zones.length} high-occupancy cell(s) highlighted in red/yellow are frequently occupied areas — potential congestion zones.</p>
              )}
            </Card>
            <Card title="Crowd alerts" pad={false}>
              {an.crowd_events.length ? (
                <table className="w-full">
                  <thead><tr><th className="th">Type</th><th className="th">Start</th><th className="th">Duration</th><th className="th">Peak</th><th className="th">Status</th><th className="th" /></tr></thead>
                  <tbody>
                    {an.crowd_events.map((c) => (
                      <tr key={c.id}>
                        <td className="td capitalize font-medium">{c.crowd_type}</td>
                        <td className="td tabular-nums">{fmtTime(c.start_time)}</td>
                        <td className="td tabular-nums">{c.duration.toFixed(1)}s</td>
                        <td className="td font-semibold">{c.peak_count}</td>
                        <td className="td"><Badge status={c.status} /></td>
                        <td className="td text-right whitespace-nowrap">
                          {c.has_snapshot && <button className="btn-ghost !px-2 !py-1" onClick={() => setSnap(c)}><ImageIcon size={15} /></button>}
                          <button className="btn-ghost !px-2 !py-1 ml-1" onClick={() => review(c, 'reviewed')}><Check size={15} /></button>
                          <button className="btn-ghost !px-2 !py-1 ml-1" onClick={() => review(c, 'dismissed')}><X size={15} /></button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : <Empty icon={Users} title="No crowd alerts for this analysis" />}
            </Card>
          </div>
        </>
      )}
      <Modal open={!!snap} onClose={() => setSnap(null)} title={snap ? `${snap.crowd_type} at ${fmtTime(snap.start_time)}` : ''} wide>
        {snap && <img className="w-full max-h-[75vh] object-contain" src={url(`/api/events/crowd/${snap.id}/snapshot.jpg`)} alt="crowd snapshot" />}
      </Modal>
    </>
  )
}

function CapacityBar({ count, warning, critical }) {
  const max = Math.max(critical * 1.2, count, 1)
  return (
    <div className="mt-4">
      <div className="relative h-3 rounded-full bg-slate-100 overflow-hidden">
        <div className={`h-full ${count >= critical ? 'bg-rose-500' : count >= warning ? 'bg-amber-500' : 'bg-emerald-500'}`} style={{ width: `${(100 * count) / max}%` }} />
        <div className="absolute inset-y-0 w-0.5 bg-amber-600" style={{ left: `${(100 * warning) / max}%` }} />
        <div className="absolute inset-y-0 w-0.5 bg-rose-600" style={{ left: `${(100 * critical) / max}%` }} />
      </div>
      <div className="flex justify-between text-[11px] text-slate-500 mt-1"><span>0</span><span>elevated {warning}</span><span>critical {critical}</span></div>
    </div>
  )
}
