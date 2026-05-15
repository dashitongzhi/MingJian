import { Routes, Route, Navigate } from 'react-router-dom'
import AppLayout from './components/layout/AppLayout'
import { ErrorBoundary } from './components/ui/ErrorBoundary'
import Dashboard from './pages/Dashboard'
import AiAssistant from './pages/AiAssistant'
import Workbench from './pages/Workbench'
import Agents from './pages/Agents'
import Debate from './pages/Debate'
import Simulation from './pages/Simulation'
import Evidence from './pages/Evidence'
import Predictions from './pages/Predictions'
import Monitoring from './pages/Monitoring'
import Providers from './pages/Providers'
import Sources from './pages/Sources'
import Batch from './pages/Batch'
import Reports from './pages/Reports'
import Settings from './pages/Settings'

export default function App() {
  return (
    <ErrorBoundary>
      <Routes>
        <Route element={<AppLayout />}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/ai-assistant" element={<AiAssistant />} />
          <Route path="/workbench" element={<Workbench />} />
          <Route path="/agents" element={<Agents />} />
          <Route path="/debate" element={<Debate />} />
          <Route path="/simulation" element={<Simulation />} />
          <Route path="/evidence" element={<Evidence />} />
          <Route path="/predictions" element={<Predictions />} />
          <Route path="/monitoring" element={<Monitoring />} />
          <Route path="/providers" element={<Providers />} />
          <Route path="/sources" element={<Sources />} />
          <Route path="/batch" element={<Batch />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="/settings" element={<Settings />} />
        </Route>
      </Routes>
    </ErrorBoundary>
  )
}
