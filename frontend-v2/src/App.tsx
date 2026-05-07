import { Routes, Route, Navigate } from 'react-router-dom'
import AppLayout from './components/layout/AppLayout'
import Dashboard from './pages/Dashboard'
import Placeholder from './pages/Placeholder'

export default function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/ai-assistant" element={<Placeholder title="AI 助手" />} />
        <Route path="/agents" element={<Placeholder title="智能体管理" />} />
        <Route path="/debate" element={<Placeholder title="辩论中心" />} />
        <Route path="/simulation" element={<Placeholder title="场景模拟" />} />
        <Route path="/evidence" element={<Placeholder title="证据库" />} />
        <Route path="/reports" element={<Placeholder title="报告中心" />} />
        <Route path="/settings" element={<Placeholder title="设置" />} />
      </Route>
    </Routes>
  )
}
