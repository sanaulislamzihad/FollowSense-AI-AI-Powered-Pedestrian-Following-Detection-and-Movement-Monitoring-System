const BASE = import.meta.env.VITE_API_BASE || ''

async function request(path, options = {}) {
  const res = await fetch(BASE + path, {
    ...options,
    headers: options.body && !(options.body instanceof FormData)
      ? { 'Content-Type': 'application/json', ...(options.headers || {}) }
      : options.headers,
  })
  if (!res.ok) {
    let msg = res.statusText
    try {
      const j = await res.json()
      msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail)
    } catch { /* not json */ }
    throw new Error(msg)
  }
  const ct = res.headers.get('content-type') || ''
  return ct.includes('application/json') ? res.json() : res.text()
}

export const url = (path) => BASE + path

export const api = {
  overview: () => request('/api/overview'),
  videos: () => request('/api/videos'),
  video: (id) => request(`/api/videos/${id}`),
  deleteVideo: (id) => request(`/api/videos/${id}`, { method: 'DELETE' }),
  jobs: (status) => request(`/api/jobs${status ? `?status=${status}` : ''}`),
  job: (id) => request(`/api/jobs/${id}`),
  createJob: (body) => request('/api/jobs', { method: 'POST', body: JSON.stringify(body) }),
  stopJob: (id) => request(`/api/jobs/${id}/stop`, { method: 'POST' }),
  deleteJob: (id) => request(`/api/jobs/${id}`, { method: 'DELETE' }),
  analytics: (id) => request(`/api/jobs/${id}/analytics`),
  following: (params = {}) => request(`/api/events/following?${new URLSearchParams(params)}`),
  reviewFollowing: (id, body) => request(`/api/events/following/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  crowd: (params = {}) => request(`/api/events/crowd?${new URLSearchParams(params)}`),
  reviewCrowd: (id, body) => request(`/api/events/crowd/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  groups: (params = {}) => request(`/api/events/groups?${new URLSearchParams(params)}`),
  cameras: () => request('/api/cameras'),
  createCamera: (body) => request('/api/cameras', { method: 'POST', body: JSON.stringify(body) }),
  deleteCamera: (id) => request(`/api/cameras/${id}`, { method: 'DELETE' }),
  settings: () => request('/api/settings'),
  saveSettings: (values) => request('/api/settings', { method: 'PUT', body: JSON.stringify(values) }),
  resetSettings: () => request('/api/settings/reset', { method: 'POST' }),
}

/** Upload with progress (fetch has no upload progress). */
export function uploadVideo(file, { analyze = true, onProgress } = {}) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${BASE}/api/videos?analyze=${analyze}`)
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress?.(e.loaded / e.total)
    xhr.onload = () => {
      let data = null
      try { data = JSON.parse(xhr.responseText) } catch { /* ignore */ }
      if (xhr.status >= 200 && xhr.status < 300) resolve(data)
      else reject(new Error(data?.detail || xhr.statusText))
    }
    xhr.onerror = () => reject(new Error('Upload failed'))
    const fd = new FormData()
    fd.append('file', file)
    xhr.send(fd)
  })
}
