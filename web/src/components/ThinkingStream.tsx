import { useEffect, useRef } from 'react'
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

export function ThinkingStream({ events }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)

  // 自动滚动到底部
  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight
    }
  }, [events])

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
    <div ref={containerRef} className="h-full overflow-y-auto p-4 space-y-1">
      <div className="text-xs text-anima-muted mb-3 flex items-center gap-2">
        <span className="w-2 h-2 bg-anima-accent rounded-full animate-pulse" />
        实时思维流 · 共 {events.length} 条事件
      </div>

      {events.map((event, i) => (
        <EventItem key={event.id + '-' + i} event={event} />
      ))}
    </div>
  )
}

function EventItem({ event }: { event: AnimaEvent }) {
  const borderColor = TYPE_COLORS[event.type] || 'border-l-anima-border'
  const bgColor = TYPE_BG[event.type] || ''
  const time = formatTime(event.timestamp)

  return (
    <div className={`animate-slide-in border-l-2 ${borderColor} ${bgColor} rounded-r-lg px-3 py-2 hover:bg-anima-card/50 transition-colors`}>
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
        <span className="text-xs text-anima-muted/50 flex-shrink-0 uppercase tracking-wider">
          {event.type}
        </span>
      </div>
    </div>
  )
}

function formatTime(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch {
    return ''
  }
}
