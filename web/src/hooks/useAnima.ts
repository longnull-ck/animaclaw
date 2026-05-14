/**
 * useAnima — WebSocket Hook
 * 连接 Anima 后端，实时接收思维流事件
 * 优化：事件批量更新、有限缓冲区、自动重连退避
 */

import { useState, useEffect, useCallback, useRef } from 'react'

export interface AnimaEvent {
  id: string
  type: string
  title: string
  detail: string
  icon: string
  data: Record<string, unknown>
  timestamp: string
}

export interface AnimaSnapshot {
  identity: {
    name: string
    owner_name: string
    company_description: string
    active_domains: string[]
    version: number
    personality: { proactivity: number; risk_tolerance: number }
  } | null
  trust: { score: number; level: string; label: string; next_level: string | null; points_to_next: number | null }
  skills: Array<{ id: string; name: string; proficiency: number; success_rate: number; use_count: number }>
  questions: { total: number; pending: number; in_progress: number; resolved: number; abandoned: number }
  evolution: { total_experiences: number; success_rate: number; avg_owner_satisfaction: number; methodology_count: number }
  providers: { total_providers: number; enabled: number; active: string | null; active_model: string | null }
  ws_clients: number
}

export interface UseAnimaResult {
  connected: boolean
  events: AnimaEvent[]
  snapshot: AnimaSnapshot | null
  sendCommand: (action: string, data?: Record<string, unknown>) => void
  onWsMessage: (handler: (msg: any) => void) => () => void
}

const MAX_EVENTS = 200
const HEARTBEAT_INTERVAL = 30000 // 30s

// 根据当前连接构建 WS URL
function buildWsUrl(): string {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const host = window.location.hostname
  const port = window.location.port || '3210'
  return `${proto}://${host}:${port}/ws`
}

export function useAnima(): UseAnimaResult {
  const [connected, setConnected] = useState(false)
  const [events, setEvents] = useState<AnimaEvent[]>([])
  const [snapshot, setSnapshot] = useState<AnimaSnapshot | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectRef = useRef<ReturnType<typeof setTimeout>>()
  const heartbeatRef = useRef<ReturnType<typeof setInterval>>()
  const messageHandlersRef = useRef<Set<(msg: any) => void>>(new Set())
  const reconnectDelayRef = useRef(1000) // 指数退避起始值

  const connect = useCallback(() => {
    try {
      const ws = new WebSocket(buildWsUrl())
      wsRef.current = ws

      ws.onopen = () => {
        setConnected(true)
        reconnectDelayRef.current = 1000 // 重置退避
        console.log('[Anima] WebSocket 已连接')

        // 启动心跳
        heartbeatRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ action: 'ping' }))
          }
        }, HEARTBEAT_INTERVAL)
      }

      ws.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data)

          // 派发给所有外部处理器
          messageHandlersRef.current.forEach(handler => handler(msg))

          if (msg.type === 'history') {
            setEvents(msg.events || [])
          } else if (msg.type === 'snapshot') {
            setSnapshot(msg.data)
          } else if (msg.type === 'pong') {
            // heartbeat response — no-op
          } else if (msg.type?.startsWith('chat_') || msg.type === 'feedback_result') {
            // 由 handler 处理，不加入事件流
          } else {
            // 新实时事件 — 有限缓冲
            setEvents(prev => {
              const next = [...prev, msg]
              return next.length > MAX_EVENTS ? next.slice(-MAX_EVENTS) : next
            })
          }
        } catch (err) {
          console.error('[Anima] 消息解析失败:', err)
        }
      }

      ws.onclose = () => {
        setConnected(false)
        if (heartbeatRef.current) clearInterval(heartbeatRef.current)

        // 指数退避重连 (1s → 2s → 4s → ... → max 30s)
        const delay = reconnectDelayRef.current
        console.log(`[Anima] WebSocket 断开，${delay / 1000}s 后重连`)
        reconnectRef.current = setTimeout(connect, delay)
        reconnectDelayRef.current = Math.min(delay * 2, 30000)
      }

      ws.onerror = () => {
        ws.close()
      }
    } catch (err) {
      console.error('[Anima] WebSocket 连接失败:', err)
      const delay = reconnectDelayRef.current
      reconnectRef.current = setTimeout(connect, delay)
      reconnectDelayRef.current = Math.min(delay * 2, 30000)
    }
  }, [])

  useEffect(() => {
    connect()
    return () => {
      wsRef.current?.close()
      if (reconnectRef.current) clearTimeout(reconnectRef.current)
      if (heartbeatRef.current) clearInterval(heartbeatRef.current)
    }
  }, [connect])

  const sendCommand = useCallback((action: string, data?: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ action, ...data }))
    }
  }, [])

  const onWsMessage = useCallback((handler: (msg: any) => void) => {
    messageHandlersRef.current.add(handler)
    return () => {
      messageHandlersRef.current.delete(handler)
    }
  }, [])

  return { connected, events, snapshot, sendCommand, onWsMessage }
}
