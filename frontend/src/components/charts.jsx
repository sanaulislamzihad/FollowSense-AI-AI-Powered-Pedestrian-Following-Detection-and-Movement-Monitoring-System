import {
  ArcElement, BarElement, CategoryScale, Chart as ChartJS, Filler, Legend, LinearScale, LineElement,
  PointElement, RadialLinearScale, Tooltip,
} from 'chart.js'
import { Bar, Doughnut, Line, PolarArea } from 'react-chartjs-2'
import { REL_COLORS, REL_LABELS } from '../lib/format'

ChartJS.register(ArcElement, BarElement, CategoryScale, LinearScale, LineElement, PointElement,
  RadialLinearScale, Tooltip, Legend, Filler)
ChartJS.defaults.font.family = 'Inter, system-ui, Segoe UI, sans-serif'
ChartJS.defaults.color = '#64748b'

const grid = { color: '#eef2f7' }

export function RelationshipDoughnut({ data }) {
  // "insufficient evidence" (pairs seen too briefly / not moving) would dwarf everything else
  const keys = Object.keys(REL_LABELS).filter((k) => k !== 'insufficient_evidence' && (data?.[k] || 0) > 0)
  if (!keys.length) return <div className="text-sm text-slate-500 py-10 text-center">No pair relationships yet</div>
  return (
    <div>
    <div className="h-64">
      <Doughnut
        data={{
          labels: keys.map((k) => REL_LABELS[k]),
          datasets: [{ data: keys.map((k) => data[k]), backgroundColor: keys.map((k) => REL_COLORS[k]), borderWidth: 2 }],
        }}
        options={{ maintainAspectRatio: false, cutout: '62%', plugins: { legend: { position: 'right', labels: { boxWidth: 12 } } } }}
      />
    </div>
    {data?.insufficient_evidence > 0 && (
      <p className="text-xs text-slate-500 mt-2">+ {data.insufficient_evidence} pairs with insufficient evidence (seen together too briefly or standing still), not shown.</p>
    )}
    </div>
  )
}

const DIRS = ['East →', 'North-East ↗', 'North ↑', 'North-West ↖', 'West ←', 'South-West ↙', 'South ↓', 'South-East ↘']

export function DirectionRose({ bins }) {
  return (
    <div className="h-72">
      <PolarArea
        data={{
          labels: DIRS,
          datasets: [{
            data: bins || [],
            backgroundColor: ['#0d9488cc', '#14b8a6cc', '#2dd4bfcc', '#5eead4cc', '#0f766ecc', '#115e59cc', '#134e4acc', '#99f6e4cc'],
          }],
        }}
        options={{ maintainAspectRatio: false, plugins: { legend: { position: 'right', labels: { boxWidth: 12 } } }, scales: { r: { grid } } }}
      />
    </div>
  )
}

export function SpeedHistogram({ bins }) {
  return (
    <div className="h-64">
      <Bar
        data={{
          labels: (bins || []).map((b) => b.bin),
          datasets: [{ label: 'Samples', data: (bins || []).map((b) => b.count), backgroundColor: '#0d9488', borderRadius: 4 }],
        }}
        options={{
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: { x: { grid: { display: false }, title: { display: true, text: 'Speed (body heights / second)' } }, y: { grid } },
        }}
      />
    </div>
  )
}

export function CrowdTimeline({ timeline, warning, critical, height = 'h-72' }) {
  const pts = timeline || []
  return (
    <div className={height}>
      <Line
        data={{
          labels: pts.map((p) => `${p.t.toFixed(0)}s`),
          datasets: [
            { label: 'People in view', data: pts.map((p) => p.count), borderColor: '#0d9488', backgroundColor: '#0d948822', fill: true, tension: 0.3, pointRadius: 0, borderWidth: 2 },
            { label: 'Largest cluster', data: pts.map((p) => p.max_cluster), borderColor: '#f59e0b', pointRadius: 0, borderWidth: 1.5, tension: 0.3 },
            ...(warning ? [{ label: 'Elevated', data: pts.map(() => warning), borderColor: '#f59e0b88', borderDash: [6, 4], pointRadius: 0, borderWidth: 1 }] : []),
            ...(critical ? [{ label: 'Critical', data: pts.map(() => critical), borderColor: '#e11d4888', borderDash: [6, 4], pointRadius: 0, borderWidth: 1 }] : []),
          ],
        }}
        options={{
          maintainAspectRatio: false,
          interaction: { mode: 'index', intersect: false },
          plugins: { legend: { position: 'bottom', labels: { boxWidth: 12 } } },
          scales: { x: { grid: { display: false }, ticks: { maxTicksLimit: 12 } }, y: { grid, beginAtZero: true } },
        }}
      />
    </div>
  )
}

export function SimpleBar({ labels, values, label, color = '#0d9488', horizontal }) {
  return (
    <div className="h-64">
      <Bar
        data={{ labels, datasets: [{ label, data: values, backgroundColor: color, borderRadius: 4 }] }}
        options={{ maintainAspectRatio: false, indexAxis: horizontal ? 'y' : 'x', plugins: { legend: { display: false } }, scales: { x: { grid: { display: false } }, y: { grid, beginAtZero: true } } }}
      />
    </div>
  )
}
