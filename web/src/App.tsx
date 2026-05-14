import { useAnima } from './hooks/useAnima'
import { EmployeeCard } from './components/EmployeeCard'
import { ThinkingStream } from './components/ThinkingStream'
import { BottomTabs } from './components/BottomTabs'
import { StatusBar } from './components/StatusBar'

export default function App() {
  const { connected, events, snapshot } = useAnima()

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

        {/* 中间：实时思维流 */}
        <main className="flex-1 flex flex-col overflow-hidden">
          <div className="flex-1 overflow-hidden">
            <ThinkingStream events={events} />
          </div>

          {/* 底部：Tab 面板 */}
          <div className="h-64 border-t border-anima-border flex-shrink-0">
            <BottomTabs snapshot={snapshot} events={events} />
          </div>
        </main>
      </div>
    </div>
  )
}
