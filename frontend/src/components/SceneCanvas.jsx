import { useEffect, useRef, useState } from 'react'
import { url } from '../lib/api'

const idColor = (id) => `hsl(${(id * 137.508) % 360} 75% 55%)`

/**
 * Draws the reference frame with a density heatmap and/or trajectories on a canvas.
 * Coordinates are the stabilised (reference frame) coordinates produced by the backend.
 */
export default function SceneCanvas({ jobId, width, height, heatmap, tracks, highlight = [], showHeatmap = true,
  showTracks = true, selected, onSelect, maxHeight = 560 }) {
  const canvas = useRef(null)
  const [bg, setBg] = useState(null)

  useEffect(() => {
    if (!jobId) return
    const img = new Image()
    img.onload = () => setBg(img)
    img.onerror = () => setBg(null)
    img.src = url(`/api/jobs/${jobId}/reference.jpg`)
  }, [jobId])

  useEffect(() => {
    const c = canvas.current
    if (!c || !width || !height) return
    c.width = width
    c.height = height
    const ctx = c.getContext('2d')
    ctx.fillStyle = '#0f172a'
    ctx.fillRect(0, 0, width, height)
    if (bg) {
      ctx.globalAlpha = 0.55
      ctx.drawImage(bg, 0, 0, width, height)
      ctx.globalAlpha = 1
    }
    if (showHeatmap && heatmap?.values) {
      const { rows, cols } = heatmap
      // normalise by the 98th percentile so a single hot spot does not wash out everything else
      const flat = heatmap.values.flat().filter((v) => v > 0).sort((a, b) => a - b)
      const ref = flat.length ? flat[Math.floor(flat.length * 0.98)] || flat[flat.length - 1] : 1
      const values = heatmap.values.map((row) => row.map((v) => Math.min(1, v / ref)))
      const off = document.createElement('canvas')
      off.width = cols
      off.height = rows
      const octx = off.getContext('2d')
      const imgData = octx.createImageData(cols, rows)
      for (let r = 0; r < rows; r++) {
        for (let k = 0; k < cols; k++) {
          const v = Math.sqrt(values[r][k])
          const i = (r * cols + k) * 4
          // blue -> cyan -> yellow -> red ramp
          const hue = 230 - 230 * v
          const [R, G, B] = hslToRgb(hue / 360, 0.95, 0.5)
          imgData.data[i] = R; imgData.data[i + 1] = G; imgData.data[i + 2] = B
          imgData.data[i + 3] = v < 0.08 ? 0 : Math.round(90 + 150 * v)
        }
      }
      octx.putImageData(imgData, 0, 0)
      ctx.save()
      ctx.filter = `blur(${Math.max(width, height) / 160}px)`
      ctx.imageSmoothingEnabled = true
      ctx.drawImage(off, 0, 0, width, height)
      ctx.restore()
    }
    if (showTracks && tracks) {
      const hi = new Set(highlight)
      const lw = Math.max(2, width / 500)
      for (const tr of tracks) {
        if (!tr.path || tr.path.length < 2) continue
        const isSel = selected === tr.track_id
        const isHi = hi.has(tr.track_id)
        ctx.strokeStyle = isSel ? '#ffffff' : isHi ? '#f43f5e' : idColor(tr.track_id)
        ctx.globalAlpha = selected && !isSel ? 0.25 : 0.9
        ctx.lineWidth = isSel || isHi ? lw * 2 : lw
        ctx.beginPath()
        tr.path.forEach(([, x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)))
        ctx.stroke()
        const [, ex, ey] = tr.path[tr.path.length - 1]
        ctx.fillStyle = ctx.strokeStyle
        ctx.beginPath()
        ctx.arc(ex, ey, lw * 2, 0, Math.PI * 2)
        ctx.fill()
        if (isSel || isHi) {
          ctx.font = `bold ${Math.round(width / 60)}px Inter, sans-serif`
          ctx.fillText(`ID ${tr.track_id}`, ex + 8, ey - 8)
        }
      }
      ctx.globalAlpha = 1
    }
  }, [bg, width, height, heatmap, tracks, highlight, showHeatmap, showTracks, selected])

  const handleClick = (e) => {
    if (!onSelect || !tracks) return
    const rect = canvas.current.getBoundingClientRect()
    const x = ((e.clientX - rect.left) / rect.width) * width
    const y = ((e.clientY - rect.top) / rect.height) * height
    let best = null
    let bestD = (width / 40) ** 2
    for (const tr of tracks) {
      for (const [, px, py] of tr.path || []) {
        const d = (px - x) ** 2 + (py - y) ** 2
        if (d < bestD) { bestD = d; best = tr.track_id }
      }
    }
    onSelect(best)
  }

  return (
    <canvas ref={canvas} onClick={handleClick}
      className={`block mx-auto max-w-full rounded-lg bg-slate-900 ${onSelect ? 'cursor-crosshair' : ''}`}
      style={{ maxHeight, width: 'auto', height: 'auto' }} />
  )
}

function hslToRgb(h, s, l) {
  const f = (n) => {
    const k = (n + h * 12) % 12
    const a = s * Math.min(l, 1 - l)
    return Math.round(255 * (l - a * Math.max(-1, Math.min(k - 3, 9 - k, 1))))
  }
  return [f(0), f(8), f(4)]
}
