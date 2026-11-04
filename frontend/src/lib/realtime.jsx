import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'

const RealtimeContext = createContext(null)

/** One WebSocket for the whole app: job progress, alerts and event updates. */
export function RealtimeProvider({ children }) {
  const [connected, setConnected] = useState(false)
  const [progress, setProgress] = useState({}) // job_id -> latest status
  const [toasts, setToasts] = useState([])
  const [version, setVersion] = useState(0) // bumps whenever data changed server-side
  const listeners = useRef(new Set())

  const dismiss = useCallback((id) => setToasts((t) => t.filter((x) => x.id !== id)), [])

  useEffect(() => {
    let ws
    let retry
    let ping
    let closed = false
    const connect = () => {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      const base = import.meta.env.VITE_API_BASE
      const target = base ? base.replace(/^http/, 'ws') + '/ws' : `${proto}://${location.host}/ws`
      ws = new WebSocket(target)
      ws.onopen = () => {
        setConnected(true)
        ping = setInterval(() => ws.readyState === 1 && ws.send('ping'), 20000)
      }
      ws.onclose = () => {
        setConnected(false)
        clearInterval(ping)
        if (!closed) retry = setTimeout(connect, 2000)
      }
      ws.onmessage = (e) => {
        let msg
        try { msg = JSON.parse(e.data) } catch { return }
        listeners.current.forEach((fn) => fn(msg))
        if (msg.type === 'progress') {
          setProgress((p) => ({ ...p, [msg.job_id]: msg }))
        } else {
          setVersion((v) => v + 1)
          if (msg.type === 'job') {
            setProgress((p) => ({ ...p, [msg.job_id]: { ...(p[msg.job_id] || {}), status: msg.status } }))
          }
          if (msg.type === 'alert') {
            const id = `${msg.kind}-${msg.event_id}-${Date.now()}`
            const text = msg.kind === 'following'
              ? `ID ${msg.follower_id} appears to be following ID ${msg.leader_id} (${Math.round(msg.confidence * 100)}%)`
              : msg.crowd_type === 'overcrowding'
                ? `Overcrowding: ${msg.peak_count} people in view`
                : `Congestion zone: ${msg.peak_count} people clustered`
            setToasts((t) => [...t.slice(-4), { id, kind: msg.kind, text, job_id: msg.job_id }])
            setTimeout(() => dismiss(id), 9000)
          }
        }
      }
    }
    connect()
    return () => {
      closed = true
      clearTimeout(retry)
      clearInterval(ping)
      ws?.close()
    }
  }, [dismiss])

  const subscribe = useCallback((fn) => {
    listeners.current.add(fn)
    return () => listeners.current.delete(fn)
  }, [])

  return (
    <RealtimeContext.Provider value={{ connected, progress, toasts, dismiss, version, subscribe }}>
      {children}
    </RealtimeContext.Provider>
  )
}

export const useRealtime = () => useContext(RealtimeContext)

/** Re-run a loader on mount, whenever server data changes, and optionally on an interval. */
export function useLive(loader, deps = [], intervalMs = 0) {
  const { version } = useRealtime()
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const reload = useCallback(() => {
    loader().then((d) => { setData(d); setError(null) }).catch(setError)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  useEffect(() => { reload() }, [reload, version])
  useEffect(() => {
    if (!intervalMs) return undefined
    const t = setInterval(reload, intervalMs)
    return () => clearInterval(t)
  }, [reload, intervalMs])
  return { data, error, reload, setData }
}
