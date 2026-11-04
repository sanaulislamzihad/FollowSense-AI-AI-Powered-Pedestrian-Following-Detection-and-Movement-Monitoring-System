import { useEffect, useState } from 'react'
import { RotateCcw, Save } from 'lucide-react'
import { api } from '../lib/api'
import { Card, PageHeader } from '../components/ui'

// [key, label, help, {min, max, step} | options]
const SECTIONS = [
  {
    title: 'Detection & tracking',
    fields: [
      ['confidence_threshold', 'Detection confidence', 'Minimum YOLO score to start a track', { min: 0.1, max: 0.9, step: 0.05 }],
      ['image_size', 'Inference size (px)', 'Larger finds smaller / distant people but is slower', { options: [640, 960, 1280, 1600] }],
      ['detection_mode', 'Detection mode', 'Tiled adds full-resolution tiles for dense crowds (≈4× slower, use with a GPU)', { options: ['standard', 'tiled'] }],
      ['tracker', 'Tracker', 'ByteTrack is faster; BoT-SORT handles moving cameras slightly better', { options: ['bytetrack', 'botsort'] }],
      ['target_fps', 'Analysed frames / second', 'Frames sampled from recorded video (0 = every frame)', { min: 0, max: 30, step: 1 }],
      ['occlusion_buffer_sec', 'Occlusion memory (s)', 'Keep a lost track alive this long to survive occlusions', { min: 0.5, max: 10, step: 0.5 }],
      ['min_track_hits', 'Min detections per track', 'Shorter tracks are ignored as noise', { min: 1, max: 20, step: 1 }],
      ['camera_motion_compensation', 'Camera motion compensation', 'Stabilise coordinates for handheld / PTZ cameras', { bool: true }],
    ],
  },
  {
    title: 'Following detection',
    fields: [
      ['min_following_duration_sec', 'Minimum following duration (s)', 'Relationship must persist this long before an alert', { min: 1, max: 60, step: 0.5 }],
      ['analysis_window_sec', 'Analysis window (s)', 'Trajectory length compared at each step', { min: 2, max: 10, step: 0.5 }],
      ['follow_min_distance', 'Min distance (body heights)', 'Closer pairs are treated as walking together', { min: 0.2, max: 3, step: 0.1 }],
      ['follow_max_distance', 'Max distance (body heights)', 'Farther pairs are not compared', { min: 2, max: 20, step: 0.5 }],
      ['direction_similarity_threshold', 'Direction similarity', 'Cosine of walking directions (1 = identical)', { min: 0.5, max: 1, step: 0.01 }],
      ['speed_consistency_threshold', 'Speed consistency', 'Slower ÷ faster speed', { min: 0.2, max: 1, step: 0.05 }],
      ['trajectory_similarity_threshold', 'Trajectory similarity', 'How closely the follower retraces the leader’s path', { min: 0.1, max: 1, step: 0.05 }],
      ['behind_ratio_threshold', 'Behind ratio', 'Share of time the follower must be behind', { min: 0.3, max: 1, step: 0.05 }],
      ['min_lag_sec', 'Minimum time lag (s)', 'Smaller lags look like walking side by side', { min: 0, max: 3, step: 0.1 }],
      ['max_lag_sec', 'Maximum time lag (s)', 'Longest delay searched between leader and follower', { min: 2, max: 15, step: 0.5 }],
      ['gap_tolerance_sec', 'Gap tolerance (s)', 'Short interruptions allowed inside one event', { min: 0, max: 5, step: 0.25 }],
      ['min_alert_confidence', 'Minimum alert confidence', 'Events below this are not raised', { min: 0, max: 1, step: 0.05 }],
    ],
  },
  {
    title: 'Group walking',
    fields: [
      ['group_max_distance', 'Max group distance (body heights)', 'People closer than this and side by side form a group', { min: 0.5, max: 4, step: 0.1 }],
      ['min_group_duration_sec', 'Min group duration (s)', 'Time walking together before a group is formed', { min: 1, max: 20, step: 0.5 }],
    ],
  },
  {
    title: 'Crowd management',
    fields: [
      ['crowd_warning_count', 'Elevated level at (people)', 'People in view for an “elevated” crowd level', { min: 1, max: 500, step: 1 }],
      ['crowd_critical_count', 'Critical level at (people)', 'People in view for “critical” and an overcrowding alert', { min: 1, max: 1000, step: 1 }],
      ['congestion_distance', 'Congestion spacing (body heights)', 'Neighbours closer than this are packed together', { min: 0.3, max: 3, step: 0.1 }],
      ['congestion_min_people', 'Congestion cluster size', 'People needed for a congestion zone', { min: 3, max: 50, step: 1 }],
      ['crowd_alert_min_duration_sec', 'Crowd alert duration (s)', 'Condition must persist this long', { min: 0, max: 30, step: 0.5 }],
    ],
  },
]

export default function Settings() {
  const [values, setValues] = useState(null)
  const [defaults, setDefaults] = useState({})
  const [saved, setSaved] = useState('')

  useEffect(() => { api.settings().then((r) => { setValues(r.values); setDefaults(r.defaults) }) }, [])
  const set = (k, v) => setValues((s) => ({ ...s, [k]: v }))
  const save = async () => {
    const r = await api.saveSettings(values)
    setValues(r.values)
    setSaved('Saved — new analyses will use these settings.')
    setTimeout(() => setSaved(''), 4000)
  }
  const reset = async () => {
    if (!confirm('Reset all settings to defaults?')) return
    const r = await api.resetSettings()
    setValues(r.values)
  }
  if (!values) return null

  return (
    <>
      <PageHeader title="Settings" subtitle="Detection thresholds, following rules, tracking and crowd configuration. Distances are in body heights, so they work for any camera angle or resolution.">
        <button className="btn-ghost" onClick={reset}><RotateCcw size={16} /> Defaults</button>
        <button className="btn-primary" onClick={save}><Save size={16} /> Save settings</button>
      </PageHeader>
      {saved && <div className="card p-3 mb-4 text-sm text-emerald-800 bg-emerald-50 border-emerald-200">{saved}</div>}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        {SECTIONS.map((sec) => (
          <Card key={sec.title} title={sec.title}>
            <div className="space-y-5">
              {sec.fields.map(([k, label, help, opt]) => (
                <Field key={k} k={k} label={label} help={help} opt={opt} value={values[k]} def={defaults[k]} onChange={(v) => set(k, v)} />
              ))}
            </div>
          </Card>
        ))}
      </div>
    </>
  )
}

function Field({ label, help, opt, value, def, onChange }) {
  const changed = value !== def
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3">
        <label className="text-sm font-medium text-slate-800">{label}</label>
        {changed && <button className="text-xs text-brand-700" onClick={() => onChange(def)}>default: {String(def)}</button>}
      </div>
      <div className="text-xs text-slate-500 mb-1.5">{help}</div>
      {opt.bool ? (
        <label className="inline-flex items-center gap-2 text-sm">
          <input type="checkbox" checked={!!value} onChange={(e) => onChange(e.target.checked)} className="accent-teal-700 h-4 w-4" /> Enabled
        </label>
      ) : opt.options ? (
        <select className="input" value={value} onChange={(e) => onChange(typeof def === 'number' ? Number(e.target.value) : e.target.value)}>
          {opt.options.map((o) => <option key={o} value={o}>{o}</option>)}
        </select>
      ) : (
        <div className="flex items-center gap-3">
          <input type="range" min={opt.min} max={opt.max} step={opt.step} value={value} onChange={(e) => onChange(Number(e.target.value))} className="flex-1 accent-teal-700" />
          <input type="number" min={opt.min} max={opt.max} step={opt.step} value={value} onChange={(e) => onChange(Number(e.target.value))} className="input !w-24 tabular-nums" />
        </div>
      )}
    </div>
  )
}
