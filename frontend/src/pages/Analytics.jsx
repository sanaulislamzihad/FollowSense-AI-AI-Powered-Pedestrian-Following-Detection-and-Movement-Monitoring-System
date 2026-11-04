import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { BarChart3, FileText } from 'lucide-react'
import { api, url } from '../lib/api'
import { useLive } from '../lib/realtime'
import { Card, Empty, JobSelect, PageHeader } from '../components/ui'
import { DirectionRose, RelationshipDoughnut, SimpleBar, SpeedHistogram } from '../components/charts'
import SceneCanvas from '../components/SceneCanvas'
import { fmtNum, fmtTime } from '../lib/format'

export default function Analytics() {
  const [params, setParams] = useSearchParams()
  const { data: jobs } = useLive(() => api.jobs('completed,stopped'), [])
  const [jobId, setJobId] = useState(Number(params.get('job')) || null)
  const [an, setAn] = useState(null)
  const [layers, setLayers] = useState({ heat: false, tracks: true, onlyFollow: false })
  const [selected, setSelected] = useState(null)
  const [minLen, setMinLen] = useState(1)

  useEffect(() => { if (!jobId && jobs?.length) setJobId(jobs[0].id) }, [jobs, jobId])
  useEffect(() => {
    if (!jobId) return
    setParams({ job: jobId }, { replace: true })
    setAn(null)
    setSelected(null)
    api.analytics(jobId).then(setAn)
  }, [jobId, setParams])

  const followIds = useMemo(() => new Set((an?.following || []).flatMap((e) => [e.leader_id, e.follower_id])), [an])
  const tracks = useMemo(() => (an?.tracks || []).filter((t) =>
    t.last_seen - t.first_seen >= minLen && (!layers.onlyFollow || followIds.has(t.track_id))), [an, minLen, layers.onlyFollow, followIds])
  const sel = an?.tracks.find((t) => t.track_id === selected)
  const groupsOf = (id) => (an?.groups || []).filter((g) => g.all_members.includes(id)).map((g) => g.group_key)

  return (
    <>
      <PageHeader title="Movement Analytics" subtitle="Trajectories, density, walking directions, speeds and group movement">
        <JobSelect jobs={jobs} value={jobId} onChange={setJobId} />
        {jobId && <a className="btn-ghost" href={url(`/api/jobs/${jobId}/report.pdf`)}><FileText size={16} /> PDF report</a>}
      </PageHeader>

      {!an ? <Card><Empty icon={BarChart3} title={jobs?.length ? 'Loading analytics…' : 'No completed analyses yet'} /></Card> : (
        <>
          <div className="grid grid-cols-1 2xl:grid-cols-[1fr_360px] gap-6">
            <Card title="Trajectory map" actions={
              <div className="flex flex-wrap gap-3 text-sm">
                <Toggle label="Heatmap" on={layers.heat} set={(v) => setLayers({ ...layers, heat: v })} />
                <Toggle label="Trajectories" on={layers.tracks} set={(v) => setLayers({ ...layers, tracks: v })} />
                <Toggle label="Following pairs only" on={layers.onlyFollow} set={(v) => setLayers({ ...layers, onlyFollow: v })} />
              </div>}>
              <SceneCanvas jobId={jobId} width={an.width} height={an.height} heatmap={an.heatmap} tracks={tracks}
                highlight={[...followIds]} showHeatmap={layers.heat} showTracks={layers.tracks}
                selected={selected} onSelect={setSelected} maxHeight={640} />
              <div className="flex flex-wrap items-center gap-4 mt-3 text-sm text-slate-600">
                <label className="flex items-center gap-2">Min track length
                  <input type="range" min="0" max="15" value={minLen} onChange={(e) => setMinLen(Number(e.target.value))} className="accent-teal-700" /> {minLen}s
                </label>
                <span>{tracks.length} trajectories · click a path to inspect · red = involved in a following event</span>
              </div>
            </Card>
            <div className="space-y-6">
              <Card title={sel ? `Track ID ${sel.track_id}` : 'Track details'}>
                {sel ? (
                  <dl className="grid grid-cols-2 gap-3 text-sm">
                    <Item k="Visible" v={`${fmtTime(sel.first_seen)} – ${fmtTime(sel.last_seen)}`} />
                    <Item k="Duration" v={`${(sel.last_seen - sel.first_seen).toFixed(1)}s`} />
                    <Item k="Distance" v={`${fmtNum(sel.total_distance, 1)} bh`} />
                    <Item k="Avg speed" v={`${fmtNum(sel.avg_speed)} bh/s`} />
                    <Item k="Direction" v={sel.direction != null ? `${sel.direction}°` : 'stationary'} />
                    <Item k="Groups" v={groupsOf(sel.track_id).join(', ') || '—'} />
                    <Item k="Following" v={(an.following.filter((e) => e.follower_id === sel.track_id).map((e) => `follows ID ${e.leader_id}`)
                      .concat(an.following.filter((e) => e.leader_id === sel.track_id).map((e) => `followed by ID ${e.follower_id}`))).join(', ') || '—'} />
                  </dl>
                ) : <p className="text-sm text-slate-500">Click a trajectory on the map.</p>}
              </Card>
              <Card title="Relationship classes"><RelationshipDoughnut data={an.relationships} /></Card>
            </div>
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-2 gap-6 mt-6">
            <Card title="Movement direction analysis"><DirectionRose bins={an.directions} /></Card>
            <Card title="Walking speed distribution"><SpeedHistogram bins={an.speed_histogram} /></Card>
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-3 gap-6 mt-6">
            <Card title="Group sizes">
              {Object.keys(an.group_sizes).length
                ? <SimpleBar labels={Object.keys(an.group_sizes).map((k) => `${k} people`)} values={Object.values(an.group_sizes)} label="Groups" color="#16a34a" />
                : <Empty title="No groups detected" />}
            </Card>
            <Card title="Group movement events" className="xl:col-span-2" pad={false}>
              {an.groups.length ? (
                <div className="max-h-80 overflow-auto">
                  <table className="w-full">
                    <thead className="sticky top-0"><tr><th className="th">Group</th><th className="th">Members</th><th className="th">Max size</th><th className="th">Formed</th><th className="th">Duration</th><th className="th">Changes</th></tr></thead>
                    <tbody>
                      {an.groups.map((g) => (
                        <tr key={g.id}>
                          <td className="td font-medium">{g.group_key}</td>
                          <td className="td">{g.all_members.map((m) => <button key={m} className="text-brand-700 hover:underline mr-1.5" onClick={() => setSelected(m)}>ID {m}</button>)}</td>
                          <td className="td">{g.max_size}</td>
                          <td className="td tabular-nums">{fmtTime(g.start_time)}</td>
                          <td className="td tabular-nums">{g.duration.toFixed(1)}s</td>
                          <td className="td text-xs text-slate-500">{g.history.filter((h) => h[1] === 'join' || h[1] === 'leave').length} join/leave</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : <Empty title="No group walking detected" />}
            </Card>
          </div>
        </>
      )}
    </>
  )
}

function Toggle({ label, on, set }) {
  return (
    <label className="flex items-center gap-1.5 cursor-pointer select-none">
      <input type="checkbox" checked={on} onChange={(e) => set(e.target.checked)} className="accent-teal-700" /> {label}
    </label>
  )
}

function Item({ k, v }) {
  return (
    <div className="col-span-2 sm:col-span-1">
      <dt className="text-xs uppercase font-semibold text-slate-500 tracking-wide">{k}</dt>
      <dd className="font-medium text-slate-800">{v}</dd>
    </div>
  )
}
