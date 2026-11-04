import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { BarChart3, FileText, MonitorPlay, RefreshCw, Trash2, Upload, Video } from 'lucide-react'
import { api, uploadVideo, url } from '../lib/api'
import { useLive, useRealtime } from '../lib/realtime'
import { Badge, Card, Empty, PageHeader, Progress } from '../components/ui'
import { fmtBytes, fmtDate, fmtTime } from '../lib/format'

export default function Videos() {
  const { data: videos, reload } = useLive(api.videos, [], 5000)
  const { progress } = useRealtime()
  const [uploads, setUploads] = useState([])
  const [drag, setDrag] = useState(false)
  const [error, setError] = useState('')
  const input = useRef(null)

  const handleFiles = async (files) => {
    setError('')
    for (const file of files) {
      const id = `${file.name}-${Date.now()}`
      setUploads((u) => [...u, { id, name: file.name, p: 0 }])
      try {
        await uploadVideo(file, { onProgress: (p) => setUploads((u) => u.map((x) => (x.id === id ? { ...x, p } : x))) })
      } catch (e) {
        setError(`${file.name}: ${e.message}`)
      }
      setUploads((u) => u.filter((x) => x.id !== id))
      reload()
    }
  }

  const reanalyse = async (v) => { await api.createJob({ video_id: v.id }); reload() }
  const remove = async (v) => {
    if (!confirm(`Delete "${v.original_name}" with all its analyses and events?`)) return
    try { await api.deleteVideo(v.id); reload() } catch (e) { setError(e.message) }
  }

  return (
    <>
      <PageHeader title="Video Management" subtitle="Upload recorded footage, follow processing and open previous analyses" />

      <div
        onDragOver={(e) => { e.preventDefault(); setDrag(true) }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); handleFiles([...e.dataTransfer.files]) }}
        onClick={() => input.current?.click()}
        className={`card border-2 border-dashed cursor-pointer text-center py-10 mb-6 transition ${drag ? 'border-brand-500 bg-brand-50' : 'border-slate-300 hover:border-brand-400'}`}>
        <Upload className="mx-auto h-9 w-9 text-brand-600" />
        <div className="mt-2 font-semibold text-slate-800">Drop video files here or click to browse</div>
        <div className="text-sm text-slate-500">MP4, MOV, AVI, MKV · analysis starts automatically with the current settings</div>
        <input ref={input} type="file" accept="video/*,.mov,.mkv" multiple hidden onChange={(e) => handleFiles([...e.target.files])} />
      </div>
      {uploads.map((u) => (
        <div key={u.id} className="card p-4 mb-3 flex items-center gap-4">
          <span className="text-sm font-medium truncate w-64">{u.name}</span>
          <Progress className="flex-1" value={u.p} />
          <span className="text-sm tabular-nums w-12 text-right">{Math.round(u.p * 100)}%</span>
        </div>
      ))}
      {error && <div className="card p-3 mb-4 text-sm text-rose-700 bg-rose-50 border-rose-200">{error}</div>}

      <Card pad={false} title="Videos">
        {videos?.length ? (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead><tr><th className="th">Video</th><th className="th">Length</th><th className="th">Resolution</th><th className="th">Uploaded</th><th className="th">Latest analysis</th><th className="th">Results</th><th className="th text-right">Actions</th></tr></thead>
              <tbody>
                {videos.map((v) => {
                  const j = v.latest_job
                  const live = j && progress[j.id]
                  const busy = j && ['queued', 'running'].includes(live?.status || j.status) && live?.status !== 'completed'
                  return (
                    <tr key={v.id}>
                      <td className="td"><div className="font-medium text-slate-800 flex items-center gap-2"><Video size={16} className="text-slate-400" />{v.original_name}</div><div className="text-xs text-slate-400">{fmtBytes(v.size_bytes)} · {Math.round(v.fps)} fps</div></td>
                      <td className="td tabular-nums">{fmtTime(v.duration)}</td>
                      <td className="td">{v.width}×{v.height}</td>
                      <td className="td text-xs">{fmtDate(v.created_at)}</td>
                      <td className="td min-w-[180px]">
                        {j ? (busy ? (
                          <div><div className="flex justify-between text-xs mb-1"><Badge status={live?.status === 'running' || j.status === 'running' ? 'running' : 'queued'} /><span className="tabular-nums">{Math.round(100 * (live?.progress ?? j.progress))}%</span></div><Progress value={live?.progress ?? j.progress} /></div>
                        ) : <div><Badge status={j.status} />{j.error && <div className="text-xs text-rose-600 mt-1 truncate max-w-[220px]" title={j.error}>{j.error.split('\n')[0]}</div>}</div>) : <span className="text-slate-400 text-sm">not analysed</span>}
                      </td>
                      <td className="td text-xs text-slate-600">{j && !busy ? <>{j.total_pedestrians} people · <span className="text-rose-600 font-semibold">{j.following_count} following</span> · {j.group_count} groups · {j.crowd_alert_count} crowd</> : '—'}</td>
                      <td className="td text-right whitespace-nowrap">
                        {j && <Link className="btn-ghost !px-2 !py-1" title="Monitor" to={`/monitor?job=${j.id}`}><MonitorPlay size={15} /></Link>}
                        {j && j.status === 'completed' && <Link className="btn-ghost !px-2 !py-1 ml-1" title="Analytics" to={`/analytics?job=${j.id}`}><BarChart3 size={15} /></Link>}
                        {j && j.status === 'completed' && <a className="btn-ghost !px-2 !py-1 ml-1" title="PDF report" href={url(`/api/jobs/${j.id}/report.pdf`)}><FileText size={15} /></a>}
                        <button className="btn-ghost !px-2 !py-1 ml-1" title="Analyse again with current settings" disabled={busy} onClick={() => reanalyse(v)}><RefreshCw size={15} /></button>
                        <button className="btn-ghost !px-2 !py-1 ml-1 hover:!text-rose-600" title="Delete" disabled={busy} onClick={() => remove(v)}><Trash2 size={15} /></button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        ) : <Empty icon={Video} title="No videos uploaded yet" />}
      </Card>
    </>
  )
}
