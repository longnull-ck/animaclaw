import { useState, lazy, Suspense, useCallback } from 'react'
import { useAnima } from './hooks/useAnima'
import { StatusBar } from './components/StatusBar'
import { EmployeeCard } from './components/EmployeeCard'

// 懒加载非首屏组件
const ThinkingStream = lazy(() => import('./components/ThinkingStream').then(m => ({ default: m.ThinkingStream })))
const ChatPanel = lazy(() => import('./components/ChatPanel').then(m => ({ default: m.ChatPanel })))
const BottomTabs = lazy(() => import('./components/BottomTabs').then(m => ({ default: m.BottomTabs })))

type MainView = 'thinking' | 'chat'

function LoadingFallback() {
  return (
    <div className="h-full flex items-center justify-center text-anima-muted">
      <div className="flex items-center gap-2">
        <span className="w-2 h-2 bg-anima-accent rounded-full animate-pulse" />
        <span className="text-sm">加载中...</span>
      </div>
    </div>
  )
}

export default function App() {
  const { connected, events, snapshot, sendCommand, onWsMessage } = useAnima()
  const [mainView, setMainView] = useState<MainView>('thinking')
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)

  const switchToThinking = useCallback(() => setMainView('thinking'), [])
  const switchToChat = useCallback(() => setMainView('chat'), [])
  const toggleSidebar = useCallback(() => setSidebarCollapsed(s => !s), [])

  return (
    <div className="h-screen flex flex-col overflow-hidden bg-anima-bg text-anima-text">
      {/* 顶部状态栏 */}
      <StatusBar connected={connected} snapshot={snapshot} onToggleSidebar={toggleSidebar} />

      {/* 主体内容 */}
      <div className="flex-1 flex overflow-hidden">
        {/* 左侧：员工档案 */}
        <aside
          className={`border-r border-anima-border overflow-y-auto p-4 flex-shrink-0 transition-all duration-300 ${
            sidebarCollapsed ? 'w-0 p-0 overflow-hidden opacity-0' : 'w-80'
          } hidden lg:block`}
        >
          <EmployeeCard snapshot={snapshot} />
        </aside>

        {/* 中间：思维流 / 对话 切换 */}
        <main className="flex-1 flex flex-col overflow-hidden min-w-0">
          {/* 视图切换 Tab */}
          <div className="flex border-b border-anima-border flex-shrink-0">
            <button
              onClick={switchToThinking}
              className={`px-5 py-2.5 text-sm font-medium transition-colors ${
                mainView === 'thinking'
                  ? 'text-anima-accent border-b-2 border-anima-accent bg-anima-accent/5'
                  : 'text-anima-muted hover:text-anima-text'
              }`}
            >
              🧠 思维流
            </button>
            <button
              onClick={switchToChat}
              className={`px-5 py-2.5 text-sm font-medium transition-colors ${
                mainView === 'chat'
                  ? 'text-anima-accent border-b-2 border-anima-accent bg-anima-accent/5'
                  : 'text-anima-muted hover:text-anima-text'
              }`}
            >
              💬 对话
            </button>

            {/* 移动端：显示员工信息按钮 */}
            <button
              onClick={toggleSidebar}
              className="ml-auto px-3 py-2 text-xs text-anima-muted hover:text-anima-text lg:hidden"
            >
              📋 档案
            </button>
          </div>

          {/* 主内容区域 */}
          <div className="flex-1 overflow-hidden">
            <Suspense fallback={<LoadingFallback />}>
              {mainView === 'thinking' ? (
                <ThinkingStream events={events} />
              ) : (
                <ChatPanel sendCommand={sendCommand} onWsMessage={onWsMessage} />
              )}
            </Suspense>
          </div>

          {/* 底部：Tab 面板 */}
          <div className="h-48 lg:h-56 border-t border-anima-border flex-shrink-0">
            <Suspense fallback={<LoadingFallback />}>
              <BottomTabs snapshot={snapshot} events={events} />
            </Suspense>
          </div>
        </main>
      </div>

      {/* 移动端侧边栏 overlay */}
      {sidebarCollapsed && (
        <div className="fixed inset-0 z-50 lg:hidden" onClick={toggleSidebar}>
          <div className="absolute inset-0 bg-black/50" />
          <aside
            className="absolute left-0 top-0 bottom-0 w-80 bg-anima-card overflow-y-auto p-4 shadow-2xl"
            onClick={e => e.stopPropagation()}
          >
            <EmployeeCard snapshot={snapshot} />
          </aside>
        </div>
      )}
    </div>
  )
}
