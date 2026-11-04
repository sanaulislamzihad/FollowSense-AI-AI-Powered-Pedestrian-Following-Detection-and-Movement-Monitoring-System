import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Camera, CircleStop, Download, FileText, MonitorPlay, Play, Plus, Radio, Trash2 } from 'lucide-react'
import { api, url } from '../lib/api'
import { useLive, useRealtime } from '../lib/realtime'
import { Badge, Card, Empty, JobSelect, Modal, PageHeader, Progress } from '../components/ui'
import { LEVEL_STYLE, fmtPct, fmtTime } from '../lib/format'

export default function Monitor() {
  const [params, setParams] = useSearchParams()
  const { data: jobs, reload } = useLive(() => api.jobs(), [], 4000)
  const { data: cameras, reload: reloadCams } = useLive(api.cameras, [])
  const { progress, subscribe } = useRealtime()
  const [jobId, setJobId] = useState(Number(params.get('job')) || null)
  const [feed, setFeed] = useState([])
  const [camModal, setCamModal] = useState(false)

  useEffect(() => {
    if (!jobId && jobs?.length) {
      const running = jobs.find((j) => j.status === 'running')
      setJobId((running || jobs[0]).id)
    }
  }, [jobs, jobId])

  useEffect(() => { if (jobId) setParams({ job: jobId }, { replace: true }) }, [jobId, setParams])

  // live event feed for the selected job
  useEffect(() => {
    setFeed([])
    return subscribe((m) => {
      if (m.job_id !== jobId || (m.type !== 'alert' && m.type !== 'event')) return
      setFeed((f) => [{ ...m, _t: Date.now() }, ...f].slice(0, 40))
    })
  }, [jobId, subscribe])

  const job = useMemo(() => jobs?.find((j) => j.id === jobId), [jobs, jobId])
  const live = (job && (progress[job.id] || job.live)) || {}
  const isRunning = job && ['running', 'queued'].includes(job.status) && live.status !== 'completed'

  const startCamera = async (cam) => {
    const j = await api.createJob({ camera_id: cam.id })
    setJobId(j.id)
    reload(); reloadCams()
  }
  const stop = async () => { await api.stopJob(jobId); reload() }

  return (
    <>
      <PageHeader title="Live Monitoring" subtitle="Annotated video with tracking IDs, trajectories, following links, groups and congestion zones">
        <JobSelect jobs={jobs} value={jobId} onChange={setJobId} />
        <button className="btn-ghost" onClick={() => setCamModal(true)}><Camera size={16} /> Cameras</button>
      </PageHeader>

      <div className="grid grid-cols-1 2xl:grid-cols-[1fr_380px] gap-6">
        <Card pad={false} className="overflow-hidden">
          <div className="bg-slate-950 grid place-items-center min-h-[320px]">
            {!job && <Empty icon={MonitorPlay} title="Nothing to show">Upload a video or start a camera stream.</Empty>}
            {job && isRunning && (
              job.status === 'queued'
                ? <div className="text-slate-400 py-24">Queued — waiting for a free worker…</div>
                : <img key={`live-${job.id}`} src={url(`/api/jobs/${job.id}/live`)} alt="live" className="max-h-[75vh] w-auto max-w-full" />
            )}
            {job && !isRunning && job.has_output && (
              <video key={`vid-${job.id}`} src={url(`/api/jobs/${job.id}/video`)} controls className="max-h-[75vh] w-auto max-w-full" />
            )}
            {job && !isRunning && !job.has_output && <div className="text-slate-400 py-24">{job.status === 'failed' ? 'Analysis failed' : 'No annotated output for this job'}</div>}
          </div>
          {job && (
            <div className="px-5 py-3 flex flex-wrap items-center gap-3 border-t border-slate-100">
              <Badge status={job.status} />
              {job.is_live && <Badge className="bg-rose-100 text-rose-700"><Radio size={12} className="mr-1" /> LIVE</Badge>}
              <span className="text-sm text-slate-600 truncate">{job.source_name}</span>
              {isRunning && !job.is_live && <Progress className="flex-1 min-w-[120px]" value={live.progress ?? job.progress} />}
              <div className="ml-auto flex gap-2">
                {isRunning && <button className="btn-danger" onClick={stop}><CircleStop size={16} /> Stop</button>}
                {!isRunning && job.has_output && <a className="btn-ghost" href={url(`/api/jobs/${job.id}/video`)}><Download size={16} /> Video</a>}
                {!isRunning && <a className="btn-ghost" href={url(`/api/jobs/${job.id}/report.pdf`)}><FileText size={16} /> PDF report</a>}
              </div>
            </div>
          )}
        </Card>

        <div className="space-y-6">
          <Card title="Live status">
            <dl className="grid grid-cols-2 gap-4">
              <Stat label="Video time" value={fmtTime(live.t ?? job?.duration)} />
              <Stat label="People in view" value={live.count ?? '-'} />
              <Stat label="Crowd level" value={<span className={`rounded px-2 py-0.5 text-sm capitalize ${LEVEL_STYLE[live.level] || ''}`}>{live.level || '-'}</span>} />
              <Stat label="Congestion zones" value={live.clusters ?? '-'} />
              <Stat label="Tracks so far" value={live.tracks_total ?? job?.total_pedestrians ?? '-'} />
              <Stat label="Following now" value={<span className={live.following_active ? 'text-rose-600' : ''}>{live.following_active ?? '-'}</span>} />
              <Stat label="Groups now" value={live.groups_active ?? '-'} />
              <Stat label="Processing" value={live.processing_fps ? `${live.processing_fps} fps` : '-'} />
            </dl>
          </Card>
          <Card title="Event feed" pad={false}>
            {feed.length ? (
              <ul className="divide-y divide-slate-100 max-h-[420px] overflow-auto">
                {feed.map((m, i) => (
                  <li key={i} className="px-5 py-2.5 text-sm">
                    <FeedLine m={m} />
                  </li>
                ))}
              </ul>
            ) : <div className="text-sm text-slate-500 px-5 py-6">Events from this analysis will appear here in real time.</div>}
            {job && <div className="px-5 py-3 border-t border-slate-100 text-sm"><Link className="text-brand-700 font-medium" to={`/events?job=${job.id}`}>All events of job #{job.id} →</Link></div>}
          </Card>
        </div>
      </div>

      <CameraModal open={camModal} onClose={() => setCamModal(false)} cameras={cameras} reload={reloadCams} onStart={startCamera} />
    </>
  )
}

function Stat({ label, value }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-slate-500 font-semibold">{label}</dt>
      <dd className="text-lg font-bold text-slate-800 mt-0.5 tabular-nums">{value}</dd>
    </div>
  )
}

function FeedLine({ m }) {
  const t = <span className="text-slate-400 tabular-nums mr-2">{fmtTime(m.end_time ?? m.start_time)}</span>
  if (m.kind === 'following') {
    return <div>{t}<span className="font-semibold text-rose-600">Following {m.action}</span> · ID {m.follower_id} → ID {m.leader_id} · {fmtPct(m.confidence)}</div>
  }
  if (m.kind === 'group') {
    return <div>{t}<span className="font-semibold text-emerald-600">Group {m.key} {m.action}</span> · members {m.members?.join(', ')}</div>
  }
  return <div>{t}<span className="font-semibold text-amber-600 capitalize">{m.crowd_type} {m.action}</span> · peak {m.peak_count}</div>
}

function CameraModal({ open, onClose, cameras, reload, onStart }) {
  const [form, setForm] = useState({ name: '', source_url: '', location: '' })
  const [err, setErr] = useState('')
  const add = async (e) => {
    e.preventDefault()
    setErr('')
    try {
      await api.createCamera(form)
      setForm({ name: '', source_url: '', location: '' })
      reload()
    } catch (ex) { setErr(ex.message) }
  }
  return (
    <Modal open={open} onClose={onClose} title="CCTV cameras">
      <ul className="divide-y divide-slate-100 mb-4">
        {(cameras || []).map((c) => (
          <li key={c.id} className="py-2.5 flex items-center gap-3">
            <Camera size={18} className="text-slate-400" />
            <div className="flex-1 min-w-0">
              <div className="text-sm font-medium">{c.name} {c.location && <span className="text-slate-400">· {c.location}</span>}</div>
              <div className="text-xs text-slate-500 truncate">{c.source_url}</div>
            </div>
            {c.live_job_id
              ? <Badge className="bg-rose-100 text-rose-700">LIVE #{c.live_job_id}</Badge>
              : <button className="btn-primary !py-1.5" onClick={() => { onStart(c); onClose() }}><Play size={14} /> Start</button>}
            <button className="text-slate-400 hover:text-rose-600" onClick={async () => { await api.deleteCamera(c.id); reload() }}><Trash2 size={16} /></button>
          </li>
        ))}
        {!cameras?.length && <li className="text-sm text-slate-500 py-2">No cameras configured.</li>}
      </ul>
      <form onSubmit={add} className="space-y-3 border-t border-slate-100 pt-4">
        <div className="grid grid-cols-2 gap-3">
          <div><label className="label">Name</label><input className="input" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></div>
          <div><label className="label">Location</label><input className="input" value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} /></div>
        </div>
        <div>
          <label className="label">Stream URL</label>
          <input className="input" required placeholder="rtsp://user:pass@192.168.1.20:554/stream1  (or 0 for webcam)" value={form.source_url} onChange={(e) => setForm({ ...form, source_url: e.target.value })} />
        </div>
        {err && <div className="text-sm text-rose-600">{err}</div>}
        <button className="btn-primary"><Plus size={16} /> Add camera</button>
      </form>
    </Modal>
  )
}
