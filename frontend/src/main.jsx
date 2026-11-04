import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import './index.css'
import Layout from './components/Layout'
import { RealtimeProvider } from './lib/realtime'
import Overview from './pages/Overview'
import Monitor from './pages/Monitor'
import Events from './pages/Events'
import Crowd from './pages/Crowd'
import Analytics from './pages/Analytics'
import Videos from './pages/Videos'
import Settings from './pages/Settings'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <RealtimeProvider>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Overview />} />
            <Route path="monitor" element={<Monitor />} />
            <Route path="events" element={<Events />} />
            <Route path="crowd" element={<Crowd />} />
            <Route path="analytics" element={<Analytics />} />
            <Route path="videos" element={<Videos />} />
            <Route path="settings" element={<Settings />} />
          </Route>
        </Routes>
      </RealtimeProvider>
    </BrowserRouter>
  </React.StrictMode>,
)
