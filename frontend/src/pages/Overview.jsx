import { Link } from 'react-router-dom'
import { AlertTriangle, Footprints, MonitorPlay, Users, UsersRound, Video } from 'lucide-react'
import { api } from '../lib/api'
import { useLive, useRealtime } from '../lib/realtime'
import { Badge, Card, Empty, PageHeader, Progress, StatCard } from '../components/ui'
import { RelationshipDoughnut } from '../components/charts'
import { fmtDate, fmtPct, fmtTime } from '../lib/format'

export default function Overview() {
  const { data } = useLive(api.overview, [], 5000)
  const { progress } = useRealtime()
  const d = data || {}

  return (
    <>
      <PageHeader title="Overview" subtitle="Pedestrian movement, following behaviour and crowd status at a glance">
        <Link to="/videos" className="btn-primary"><Video size={16} /> Analyse a video</Link>
        <Link to="/monitor" className="btn-ghost"><MonitorPlay size={16} /> Live monitoring</Link>
      </PageHeader>

      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        <StatCard icon={Users} label="Pedestrians detected" value={d.total_pedestrians} hint={`${d.jobs_completed ?? 0} analyses completed`} />
        <StatCard icon={MonitorPlay} tone="sky" label="Active tracking IDs" value={d.active_tracks} hint={`${d.live_people ?? 0} people in view now · ${d.jobs_running ?? 0} running`} />
        <StatCard icon={Footprints} tone="rose" label="Potential following" value={d.following_events} hint={`${d.following_unreviewed ?? 0} awaiting review`} />
        <StatCard icon={UsersRound} tone="green" label="Group / crowd events" value={`${d.group_events ?? 0} / ${d.crowd_alerts ?? 0}`} hint={`Peak crowd ${d.peak_crowd ?? 0} people`} />
      </div>

      {d.running_jobs?.length > 0 && (
        <Card title="Processing now" className="mt-6">
          <div className="space-y-4">
            {d.running_jobs.map((j) => {
              const p = progress[j.id] || j.live || {}
              return (
                <div key={j.id} className="flex flex-wrap items-center gap-4">
                  <div className="min-w-[220px]">
                    <div className="font-medium text-slate-800">#{j.id} · {j.source_name}</div>
                    <div className="text-xs text-slate-500">
                      {p.count ?? 0} people · {p.following_active ?? 0} following · {p.processing_fps ?? 0} fps
                    </div>
                  </div>
                  <div className="flex-1 min-w-[160px]">
                    {j.is_live ? <Badge className="bg-rose-100 text-rose-700">LIVE</Badge> : <Progress value={p.progress ?? j.progress} />}
                  </div>
                  <Link to={`/monitor?job=${j.id}`} className="btn-ghost">Watch</Link>
                </div>
              )
            })}
          </div>
        </Card>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6 mt-6">
        <Card title="Recent following alerts" className="xl:col-span-2" pad={false}
          actions={<Link to="/events" className="text-sm text-brand-700 font-medium">View all</Link>}>
          {d.recent_alerts?.length ? (
            <table className="w-full">
              <thead><tr><th className="th">Event</th><th className="th">Pair</th><th className="th">Time</th><th className="th">Duration</th><th className="th">Confidence</th><th className="th">Status</th></tr></thead>
              <tbody>
                {d.recent_alerts.map((e) => (
                  <tr key={e.id}>
                    <td className="td font-medium">#{e.id} <span className="text-slate-400">job {e.job_id}</span></td>
                    <td className="td">ID {e.follower_id} → ID {e.leader_id}</td>
                    <td className="td">{fmtTime(e.start_time)}</td>
                    <td className="td">{e.duration.toFixed(1)}s</td>
                    <td className="td font-semibold">{fmtPct(e.confidence)}</td>
                    <td className="td"><Badge status={e.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <Empty icon={AlertTriangle} title="No following alerts yet">Upload a video or connect a camera to start.</Empty>}
        </Card>

        <Card title="Pair relationships (all analyses)">
          <RelationshipDoughnut data={d.relationships} />
        </Card>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6 mt-6">
        <Card title="Recent crowd alerts" pad={false} actions={<Link to="/crowd" className="text-sm text-brand-700 font-medium">Crowd management</Link>}>
          {d.recent_crowd?.length ? (
            <ul className="divide-y divide-slate-100">
              {d.recent_crowd.map((c) => (
                <li key={c.id} className="px-5 py-3 flex items-center gap-3">
                  <Users className={c.crowd_type === 'overcrowding' ? 'text-rose-500' : 'text-amber-500'} size={18} />
                  <div className="flex-1">
                    <div className="text-sm font-medium capitalize">{c.crowd_type}</div>
                    <div className="text-xs text-slate-500">Job #{c.job_id} · {fmtTime(c.start_time)} · {c.duration.toFixed(1)}s</div>
                  </div>
                  <div className="text-sm font-semibold">{c.peak_count} people</div>
                </li>
              ))}
            </ul>
          ) : <Empty icon={Users} title="No crowd alerts" />}
        </Card>
        <Card title="Recent analyses" pad={false} actions={<Link to="/videos" className="text-sm text-brand-700 font-medium">Videos</Link>}>
          {d.recent_jobs?.length ? (
            <ul className="divide-y divide-slate-100">
              {d.recent_jobs.map((j) => (
                <li key={j.id} className="px-5 py-3 flex items-center gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium truncate">#{j.id} · {j.source_name}</div>
                    <div className="text-xs text-slate-500">{fmtDate(j.created_at)} · {j.total_pedestrians} pedestrians · {j.following_count} following</div>
                  </div>
                  <Badge status={j.status} />
                  {j.status === 'completed' && <Link className="text-sm text-brand-700 font-medium" to={`/analytics?job=${j.id}`}>Analytics</Link>}
                </li>
              ))}
            </ul>
          ) : <Empty icon={Video} title="No analyses yet" />}
        </Card>
      </div>
    </>
  )
}
