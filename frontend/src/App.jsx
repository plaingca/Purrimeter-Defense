import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { useEffect } from 'react'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Cameras from './pages/Cameras'
import Rules from './pages/Rules'
import Recordings from './pages/Recordings'
import Settings from './pages/Settings'
import { useAlertStore } from './stores/alertStore'

function App() {
  const { connect } = useAlertStore()
  
  useEffect(() => {
    // Connect to alert WebSocket
    connect()
  }, [connect])
  
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="cameras" element={<Cameras />} />
          <Route path="rules" element={<Rules />} />
          <Route path="recordings" element={<Recordings />} />
          <Route path="settings" element={<Settings />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App

