import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'

export default function AppLayout() {
  return (
    <div className="flex h-screen bg-[#111318]">
      <Sidebar />
      {/* 主内容区域 - 左侧留出 sidebar 宽度 */}
      <main className="flex-1 ml-60 overflow-y-auto">
        <div className="px-10 py-8">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
