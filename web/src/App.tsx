import { useState } from 'react'
import { useAnima } from './hooks/useAnima'
import { EmployeeCard } from './components/EmployeeCard'
import { ThinkingStream } from './components/ThinkingStream'
import { ChatPanel } from './components/ChatPanel'
import { BottomTabs } from './components/BottomTabs'
import { StatusBar } from './components/StatusBar'

type MainView = 'thinking' | 'chat'

export default function App() {
  const { connected, events, snapshot, sendCommand, onWsMessage } = useAnima()
  const [mainView, setMainView] = useState<MainView>('thinking')

  return (
    <div className="h-screen flex flex-col overflow-hidden">
      {/* 顶部状态栏 */}
      <StatusBar connected={connected} snapshot={snapshot} />

      {/* 主体内容 */}
      <div className="flex-1 flex overflow-hidden">
        {/* 左侧：员工档案 */}
        <aside className="w-80 border-r border-anima-border overflow-y-auto p-4 flex-shrink-0">
          <EmployeeCard snapshot={snapshot} />
        </aside>

        {/* 中间：思维流 / 对话 切换 */}
        <main className="flex-1 flex flex-col overflow-hidden">
          {/* 视图切换 Tab */}
          <div className="flex border-b border-anima-border flex-shrink-0">
            <button
              onClick={() => setMainView('thinking')}
              className={`px-5 py-2.5 text-sm font-medium transition-colors ${
                mainView === 'thinking'
                  ? 'text-anima-accent border-b-2 border-anima-accent bg-anima-accent/5'
                  : 'text-anima-muted hover:text-anima-text'
              }`}
            >
              🧠 思维流
            </button>
            <button
              onClick={() => setMainView('chat')}
              className={`px-5 py-2.5 text-sm font-medium transition-colors ${
                mainView === 'chat'
                  ? 'text-anima-accent border-b-2 border-anima-accent bg-anima-accent/5'
                  : 'text-anima-muted hover:text-anima-text'
              }`}
            >
              💬 对话
            </button>
          </div>

          {/* 主内容区域 */}
          <div className="flex-1 overflow-hidden">
            {mainView === 'thinking' ? (
              <ThinkingStream events={events} />
            ) : (
              <ChatPanel sendCommand={sendCommand} onWsMessage={onWsMessage} />
            )}
          </div>

          {/* 底部：Tab 面板 */}
          <div className="h-56 border-t border-anima-border flex-shrink-0">
            <BottomTabs snapshot={snapshot} events={events} />
          </div>
        </main>
      </div>
    </div>
  )
}
