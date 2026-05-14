import { useEffect, useRef, useMemo, memo, useCallback, useState } from 'react'
import type { AnimaEvent } from '../hooks/useAnima'

interface Props {
  events: AnimaEvent[]
}

const TYPE_COLORS: Record<string, string> = {
  perception: 'border-l-sky-400',
  thinking:   'border-l-anima-accent2',
  action:     'border-l-anima-accent',
  memory:     'border-l-purple-400',
  skill:      'border-l-anima-warm',
  trust:      'border-l-yellow-400',
  evolution:  'border-l-pink-400',
  question:   'border-l-blue-400',
  system:     'border-l-anima-muted',
  message:    'border-l-green-400',
}

const TYPE_BG: Record<string, string> = {
  thinking: 'bg-anima-accent2/5',
  action:   'bg-anima-accent/5',
  skill:    'bg-anima-warm/5',
}

// 事件类型筛选
const EVENT_TYPES = [
  { key: 'all', label: '全部' },
  { key: 'thinking', label: '思考' },
  { key: 'action', label: '行动' },
  { key: 'memory', label: '记忆' },
  { key: 'message', label: '消息' },
  { key: 'evolution', label: '进化' },
] as const

export function ThinkingStream({ events }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [autoScroll, setAutoScroll] = useState(true)
  const [filter, setFilter] = useState<string>('all')

  // 筛选事件
  const filteredEvents = useMemo(() => {
    if (filter === 'all') return events
    return events.filter(e => e.type === filter)
  }, [events, filter])

  // 自动滚动到底部（仅当用户没有手动滚动时）
  useEffect(() => {
    if (autoScroll && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight
    }
  }, [filteredEvents, autoScroll])

  // 检测用户是否手动滚动了
  const handleScroll = useCallback(() => {
    if (!containerRef.current) return
    const { scrollTop, scrollHeight, clientHeight } = containerRef.current
    const isAtBottom = scrollHeight - scrollTop - clientHeight < 50
    setAutoScroll(isAtBottom)
  }, [])

  const scrollToBottom = useCallback(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight
      setAutoScroll(true)
    }
  }, [])

  if (events.length === 0) {
    return (
      <div className="h-full flex items-center justify-center text-anima-muted">
        <div className="text-center animate-fade-in">
          <div className="text-5xl mb-4 animate-pulse-slow">🧠</div>
          <p className="text-lg">思维流</p>
          <p className="text-sm mt-1">等待 Anima 开始工作...</p>
          <p className="text-xs mt-3 opacity-50">这里会实时显示 Anima 的每一步思考和行动</p>
        </div>
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col">
      {/* 筛选栏 */}
      <div className="flex items-center gap-1 px-4 py-2 border-b border-anima-border/50 flex-shrink-0 overflow-x-auto">
        {EVENT_TYPES.map(t => (
          <button
            key={t.key}
            onClick={() => setFilter(t.key)}
            className={`px-2.5 py-1 text-xs rounded-full whitespace-nowrap transition-colors ${
              filter === t.key
                ? 'bg-anima-accent/20 text-anima-accent'
                : 'text-anima-muted hover:text-anima-text hover:bg-anima-card'
            }`}
          >
            {t.label}
          </button>
        ))}
        <span className="ml-auto text-xs text-anima-muted/60 flex-shrink-0">
          {filteredEvents.length}/{events.length}
        </span>
      </div>

      {/* 事件流 */}
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto p-4 space-y-1"
      >
        <div className="text-xs text-anima-muted mb-3 flex items-center gap-2">
          <span className="w-2 h-2 bg-anima-accent rounded-full animate-pulse" />
          实时思维流 · 共 {filteredEvents.length} 条事件
        </div>

        {filteredEvents.map((event, i) => (
          <EventItem key={event.id + '-' + i} event={event} />
        ))}
      </div>

      {/* 回到底部按钮 */}
      {!autoScroll && (
        <button
          onClick={scrollToBottom}
          className="absolute bottom-2 right-4 px-3 py-1.5 text-xs bg-anima-accent text-anima-bg rounded-full shadow-lg hover:bg-anima-accent/80 transition-all animate-fade-in"
        >
          ↓ 最新
        </button>
      )}
    </div>
  )
}

// 使用 memo 避免未变化的事件项重新渲染
const EventItem = memo(function EventItem({ event }: { event: AnimaEvent }) {
  const borderColor = TYPE_COLORS[event.type] || 'border-l-anima-border'
  const bgColor = TYPE_BG[event.type] || ''
  const time = formatTime(event.timestamp)

  return (
    <div className={`border-l-2 ${borderColor} ${bgColor} rounded-r-lg px-3 py-2 hover:bg-anima-card/50 transition-colors`}>
      <div className="flex items-start gap-2">
        <span className="text-sm flex-shrink-0">{event.icon}</span>
        <div className="flex-1 min-w-0">
          <div className="flex items-baseline gap-2">
            <span className="text-sm font-medium">{event.title}</span>
            <span className="text-xs text-anima-muted">{time}</span>
          </div>
          {event.detail && (
            <p className="text-xs text-anima-muted mt-0.5 truncate">{event.detail}</p>
          )}
        </div>
        <span className="text-xs text-anima-muted/50 flex-shrink-0 uppercase tracking-wider hidden sm:inline">
          {event.type}
        </span>
      </div>
    </div>
  )
})

function formatTime(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch {
    return ''
  }
}
