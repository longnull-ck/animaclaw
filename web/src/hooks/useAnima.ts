/**
 * useAnima — WebSocket Hook
 * 连接 Anima 后端，实时接收思维流事件
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

const WS_URL = `ws://${window.location.hostname}:${window.location.port || '3210'}/ws`

export function useAnima(): UseAnimaResult {
  const [connected, setConnected] = useState(false)
  const [events, setEvents] = useState<AnimaEvent[]>([])
  const [snapshot, setSnapshot] = useState<AnimaSnapshot | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectRef = useRef<ReturnType<typeof setTimeout>>()
  const messageHandlersRef = useRef<Set<(msg: any) => void>>(new Set())

  const connect = useCallback(() => {
    const ws = new WebSocket(WS_URL)
    wsRef.current = ws

    ws.onopen = () => {
      setConnected(true)
      console.log('[Anima] WebSocket 已连接')
    }

    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data)

        // 派发给所有外部处理器（ChatPanel 等）
        messageHandlersRef.current.forEach(handler => handler(msg))

        if (msg.type === 'history') {
          // 历史事件回放
          setEvents(msg.events || [])
        } else if (msg.type === 'snapshot') {
          // 状态快照
          setSnapshot(msg.data)
        } else if (msg.type === 'pong') {
          // heartbeat response
        } else if (msg.type?.startsWith('chat_')) {
          // chat 相关消息由 ChatPanel 的 handler 处理，不加入事件流
        } else if (msg.type === 'feedback_result') {
          // 反馈结果由 handler 处理
        } else {
          // 新实时事件
          setEvents(prev => [...prev.slice(-199), msg])
        }
      } catch (err) {
        console.error('[Anima] 消息解析失败:', err)
      }
    }

    ws.onclose = () => {
      setConnected(false)
      console.log('[Anima] WebSocket 断开，5s 后重连')
      reconnectRef.current = setTimeout(connect, 5000)
    }

    ws.onerror = () => {
      ws.close()
    }
  }, [])

  useEffect(() => {
    connect()
    return () => {
      wsRef.current?.close()
      if (reconnectRef.current) clearTimeout(reconnectRef.current)
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
