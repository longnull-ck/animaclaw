/**
 * ChatPanel — WebChat 对话面板
 * 用户在控制中心里直接和 Anima 对话
 * 支持流式输出（逐字显示打字效果）
 */

import { useState, useRef, useEffect, useCallback } from 'react'

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: string
  streaming?: boolean
}

interface Props {
  sendCommand: (action: string, data?: Record<string, unknown>) => void
  onWsMessage?: (handler: (msg: any) => void) => () => void
}

export function ChatPanel({ sendCommand, onWsMessage }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [streamingContent, setStreamingContent] = useState('')
  const scrollRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // 自动滚动到底部
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages, streamingContent])

  // 监听 WebSocket 消息
  useEffect(() => {
    if (!onWsMessage) return

    const unsubscribe = onWsMessage((msg: any) => {
      if (msg.type === 'chat_reply') {
        // 非流式回复
        setMessages(prev => [...prev, {
          id: Date.now().toString(),
          role: 'assistant',
          content: msg.text,
          timestamp: new Date().toISOString(),
        }])
        setIsLoading(false)
      } else if (msg.type === 'chat_stream_start') {
        setStreamingContent('')
      } else if (msg.type === 'chat_stream_chunk') {
        setStreamingContent(prev => prev + msg.text)
      } else if (msg.type === 'chat_stream_end') {
        // 流式结束，把累积内容转为正式消息
        setStreamingContent(prev => {
          if (prev) {
            setMessages(msgs => [...msgs, {
              id: Date.now().toString(),
              role: 'assistant',
              content: prev,
              timestamp: new Date().toISOString(),
            }])
          }
          return ''
        })
        setIsLoading(false)
      }
    })

    return unsubscribe
  }, [onWsMessage])

  const handleSend = useCallback(() => {
    const text = input.trim()
    if (!text || isLoading) return

    // 添加用户消息
    setMessages(prev => [...prev, {
      id: Date.now().toString(),
      role: 'user',
      content: text,
      timestamp: new Date().toISOString(),
    }])

    setInput('')
    setIsLoading(true)

    // 发送到后端（使用流式）
    sendCommand('chat_stream', { text })
  }, [input, isLoading, sendCommand])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="h-full flex flex-col bg-anima-bg rounded-lg border border-anima-border overflow-hidden">
      {/* 头部 */}
      <div className="px-4 py-2 border-b border-anima-border flex items-center gap-2 flex-shrink-0">
        <span className="text-sm">💬</span>
        <span className="text-sm font-medium">与 Anima 对话</span>
        <span className="text-xs text-anima-muted ml-auto">
          {messages.length} 条消息
        </span>
      </div>

      {/* 消息列表 */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-3 space-y-3">
        {messages.length === 0 && !streamingContent && (
          <div className="text-center text-anima-muted py-8 animate-fade-in">
            <p className="text-2xl mb-2">💬</p>
            <p className="text-sm">在这里和 Anima 对话</p>
            <p className="text-xs mt-1 opacity-60">发送消息后，思维流中会实时显示处理过程</p>
          </div>
        )}

        {messages.map(msg => (
          <MessageBubble key={msg.id} message={msg} />
        ))}

        {/* 流式输出中 */}
        {streamingContent && (
          <div className="flex gap-2 animate-fade-in">
            <div className="w-6 h-6 rounded-full bg-anima-accent/20 flex items-center justify-center text-xs flex-shrink-0">
              🦾
            </div>
            <div className="bg-anima-card rounded-lg rounded-tl-none px-3 py-2 max-w-[80%]">
              <p className="text-sm whitespace-pre-wrap">{streamingContent}<span className="animate-pulse">|</span></p>
            </div>
          </div>
        )}

        {/* 加载状态 */}
        {isLoading && !streamingContent && (
          <div className="flex gap-2 animate-fade-in">
            <div className="w-6 h-6 rounded-full bg-anima-accent/20 flex items-center justify-center text-xs flex-shrink-0">
              🦾
            </div>
            <div className="bg-anima-card rounded-lg rounded-tl-none px-3 py-2">
              <div className="flex gap-1">
                <span className="w-2 h-2 bg-anima-accent rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-2 h-2 bg-anima-accent rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-2 h-2 bg-anima-accent rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
            </div>
          </div>
        )}
      </div>

      {/* 输入框 */}
      <div className="p-3 border-t border-anima-border flex-shrink-0">
        <div className="flex gap-2">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入消息... (Enter 发送)"
            disabled={isLoading}
            className="flex-1 bg-anima-card border border-anima-border rounded-lg px-3 py-2 text-sm
                       text-anima-text placeholder-anima-muted/50
                       focus:outline-none focus:border-anima-accent/50 focus:ring-1 focus:ring-anima-accent/20
                       disabled:opacity-50 transition-colors"
          />
          <button
            onClick={handleSend}
            disabled={isLoading || !input.trim()}
            className="px-4 py-2 bg-anima-accent text-anima-bg text-sm font-medium rounded-lg
                       hover:bg-anima-accent/80 disabled:opacity-30 disabled:cursor-not-allowed
                       transition-all active:scale-95"
          >
            发送
          </button>
        </div>
      </div>
    </div>
  )
}

// ── 消息气泡 ─────────────────────────────────────────────────

function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === 'user'
  const time = formatTime(message.timestamp)

  return (
    <div className={`flex gap-2 ${isUser ? 'flex-row-reverse' : ''} animate-slide-in`}>
      {/* 头像 */}
      <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs flex-shrink-0 ${
        isUser ? 'bg-anima-accent2/20' : 'bg-anima-accent/20'
      }`}>
        {isUser ? '👤' : '🦾'}
      </div>

      {/* 内容 */}
      <div className={`max-w-[80%] ${isUser ? 'items-end' : 'items-start'}`}>
        <div className={`rounded-lg px-3 py-2 ${
          isUser
            ? 'bg-anima-accent2/15 rounded-tr-none'
            : 'bg-anima-card rounded-tl-none'
        }`}>
          <p className="text-sm whitespace-pre-wrap break-words">{message.content}</p>
        </div>
        <span className="text-xs text-anima-muted/50 mt-0.5 block">{time}</span>
      </div>
    </div>
  )
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString('zh-CN', {
      hour: '2-digit', minute: '2-digit',
    })
  } catch {
    return ''
  }
}
