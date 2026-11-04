import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Check, Download, Eye, Footprints, X } from 'lucide-react'
import { api, url } from '../lib/api'
import { useLive } from '../lib/realtime'
import { Badge, Card, Empty, Modal, PageHeader } from '../components/ui'
import SceneCanvas from '../components/SceneCanvas'
import { fmtDate, fmtNum, fmtPct, fmtTime } from '../lib/format'

const STATUSES = ['', 'new', 'confirmed', 'reviewed', 'dismissed']

export default function Events() {
  const [params] = useSearchParams()
  const [jobId, setJobId] = useState(params.get('job') || '')
  const [status, setStatus] = useState('')
  const [minConf, setMinConf] = useState(0)
  const [selected, setSelected] = useState(null)
  const { data: jobs } = useLive(() => api.jobs(), [])
  const query = useMemo(() => {
    const q = {}
    if (jobId) q.job_id = jobId
    if (status) q.status = status
    if (minConf) q.min_confidence = minConf
    return q
  }, [jobId, status, minConf])
  const { data: events, reload } = useLive(() => api.following(query), [query])

  const review = async (ev, newStatus) => {
    await api.reviewFollowing(ev.id, { status: newStatus })
    reload()
  }

  return (
    <>
      <PageHeader title="Following Events" subtitle="Pairs whose movement consistently resembled one person following another. Review before acting.">
        <a className="btn-ghost" href={url(`/api/events/following/export.csv?${new URLSearchParams(query)}`)}><Download size={16} /> Export CSV</a>
      </PageHeader>

      <div className="card p-4 mb-5 flex flex-wrap gap-4 items-end">
        <div>
          <label className="label">Analysis</label>
          <select className="input w-auto min-w-[220px]" value={jobId} onChange={(e) => setJobId(e.target.value)}>
            <option value="">All analyses</option>
            {(jobs || []).map((j) => <option key={j.id} value={j.id}>#{j.id} · {j.source_name}</option>)}
          </select>
        </div>
        <div>
          <label className="label">Review status</label>
          <select className="input w-auto" value={status} onChange={(e) => setStatus(e.target.value)}>
            {STATUSES.map((s) => <option key={s} value={s}>{s || 'Any'}</option>)}
          </select>
        </div>
        <div className="min-w-[200px]">
          <label className="label">Min confidence: {Math.round(minConf * 100)}%</label>
          <input type="range" min="0" max="1" step="0.05" value={minConf} onChange={(e) => setMinConf(Number(e.target.value))} className="w-full accent-teal-700" />
        </div>
      </div>

      <Card pad={false}>
        {events?.length ? (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr>
                  <th className="th">Event</th><th className="th">Lead</th><th className="th">Follower</th><th className="th">Detected at</th>
                  <th className="th">Duration</th><th className="th">Confidence</th><th className="th">Distance</th><th className="th">Lag</th>
                  <th className="th">Status</th><th className="th text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {events.map((e) => (
                  <tr key={e.id} className="hover:bg-slate-50">
                    <td className="td font-medium">#{e.id}<div className="text-xs text-slate-400">job {e.job_id}{e.is_active && <span className="text-rose-500 ml-1">● active</span>}</div></td>
                    <td className="td">ID {e.leader_id}</td>
                    <td className="td">ID {e.follower_id}</td>
                    <td className="td tabular-nums">{fmtTime(e.start_time)}</td>
                    <td className="td tabular-nums">{e.duration.toFixed(1)}s</td>
                    <td className="td"><ConfidenceBar v={e.confidence} /></td>
                    <td className="td tabular-nums">{fmtNum(e.metrics?.mean_distance)} bh</td>
                    <td className="td tabular-nums">{fmtNum(e.metrics?.lag_sec, 1)}s</td>
                    <td className="td"><Badge status={e.status} /></td>
                    <td className="td text-right whitespace-nowrap">
                      <button className="btn-ghost !px-2 !py-1" title="Inspect" onClick={() => setSelected(e)}><Eye size={15} /></button>
                      <button className="btn-ghost !px-2 !py-1 ml-1" title="Confirm" onClick={() => review(e, 'confirmed')}><Check size={15} /></button>
                      <button className="btn-ghost !px-2 !py-1 ml-1" title="Dismiss" onClick={() => review(e, 'dismissed')}><X size={15} /></button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <Empty icon={Footprints} title="No following events">Nothing matches the filters.</Empty>}
      </Card>

      <EventModal event={selected} onClose={() => setSelected(null)} onSaved={() => { reload(); setSelected(null) }} />
    </>
  )
}

function ConfidenceBar({ v }) {
  const pct = Math.round(v * 100)
  const color = v >= 0.8 ? 'bg-rose-500' : v >= 0.65 ? 'bg-amber-500' : 'bg-sky-500'
  return (
    <div className="flex items-center gap-2">
      <div className="w-16 h-1.5 bg-slate-200 rounded-full overflow-hidden"><div className={`h-full ${color}`} style={{ width: `${pct}%` }} /></div>
      <span className="text-sm font-semibold tabular-nums">{pct}%</span>
    </div>
  )
}

function EventModal({ event, onClose, onSaved }) {
  const [notes, setNotes] = useState('')
  const [analytics, setAnalytics] = useState(null)
  const video = useRef(null)
  useEffect(() => {
    setNotes(event?.notes || '')
    setAnalytics(null)
    if (event) api.analytics(event.job_id).then(setAnalytics).catch(() => {})
  }, [event])
  if (!event) return null
  const m = event.metrics || {}
  const pairTracks = analytics?.tracks.filter((t) => t.track_id === event.leader_id || t.track_id === event.follower_id)
  const save = async (status) => { await api.reviewFollowing(event.id, { status, notes }); onSaved() }

  const evidence = [
    ['Mean distance', `${fmtNum(m.mean_distance)} body heights`, 'How far apart the two people walked'],
    ['Direction similarity', fmtPct(m.direction_similarity), 'Cosine similarity of walking directions'],
    ['Speed consistency', fmtPct(m.speed_consistency), 'Slower speed ÷ faster speed'],
    ['Trajectory similarity', fmtPct(m.trajectory_similarity), 'Follower passes the leader’s earlier positions'],
    ['Behind ratio', fmtPct(m.behind_ratio), 'Share of time the follower was behind the leader'],
    ['Time lag', `${fmtNum(m.lag_sec, 1)} s`, 'Follower reaches leader’s positions this much later'],
    ['Temporal consistency', fmtPct(event.consistency), 'Share of analysis windows classified as following'],
  ]
  return (
    <Modal open={!!event} onClose={onClose} title={`Event #${event.id} · ID ${event.follower_id} following ID ${event.leader_id}`} wide>
      <div className="grid lg:grid-cols-2 gap-6">
        <div className="space-y-4">
          {analytics?.job?.has_output ? (
            <video ref={video} src={url(`/api/jobs/${event.job_id}/video`)} controls className="w-full max-h-[420px] rounded-lg bg-black"
              onLoadedMetadata={() => { if (video.current) video.current.currentTime = event.start_time }} />
          ) : event.has_snapshot && <img src={url(`/api/events/following/${event.id}/snapshot.jpg`)} alt="snapshot" className="w-full rounded-lg" />}
          {event.has_snapshot && analytics?.job?.has_output && (
            <details className="text-sm"><summary className="cursor-pointer text-brand-700 font-medium">Detection snapshot</summary>
              <img src={url(`/api/events/following/${event.id}/snapshot.jpg`)} alt="snapshot" className="w-full rounded-lg mt-2" />
            </details>
          )}
          {pairTracks && (
            <div>
              <div className="label">Trajectories of the pair (stabilised coordinates)</div>
              <SceneCanvas jobId={event.job_id} width={analytics.width} height={analytics.height} tracks={pairTracks}
                highlight={[event.follower_id]} showHeatmap={false} maxHeight={360} />
              <div className="text-xs text-slate-500 mt-1">Red = follower (ID {event.follower_id}); coloured = leader (ID {event.leader_id}).</div>
            </div>
          )}
        </div>
        <div>
          <div className="grid grid-cols-3 gap-3 mb-4">
            <Mini label="Confidence" value={fmtPct(event.confidence)} />
            <Mini label="Duration" value={`${event.duration.toFixed(1)}s`} />
            <Mini label="Window" value={`${fmtTime(event.start_time)}–${fmtTime(event.end_time)}`} />
          </div>
          <div className="label">Movement evidence</div>
          <table className="w-full mb-4">
            <tbody>
              {evidence.map(([k, v, hint]) => (
                <tr key={k}><td className="td"><div className="font-medium">{k}</div><div className="text-xs text-slate-400">{hint}</div></td><td className="td text-right font-semibold tabular-nums">{v}</td></tr>
              ))}
            </tbody>
          </table>
          <div className="rounded-lg bg-amber-50 text-amber-800 text-xs p-3 mb-4">
            This is an observable movement pattern, not a statement about intent. Verify the footage before taking any action.
          </div>
          <label className="label">Operator notes</label>
          <textarea className="input h-20" value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="e.g. walking in the same queue" />
          <div className="flex flex-wrap gap-2 mt-3">
            <button className="btn-danger" onClick={() => save('confirmed')}><Check size={16} /> Confirm</button>
            <button className="btn-primary" onClick={() => save('reviewed')}>Mark reviewed</button>
            <button className="btn-ghost" onClick={() => save('dismissed')}><X size={16} /> Dismiss</button>
          </div>
          <div className="text-xs text-slate-400 mt-3">Status: {event.status} · created {fmtDate(event.created_at)}{event.reviewed_at && ` · reviewed ${fmtDate(event.reviewed_at)}`}</div>
        </div>
      </div>
    </Modal>
  )
}

function Mini({ label, value }) {
  return (
    <div className="rounded-lg bg-slate-50 p-3">
      <div className="text-[11px] uppercase font-semibold tracking-wide text-slate-500">{label}</div>
      <div className="font-bold text-slate-800 tabular-nums">{value}</div>
    </div>
  )
}
