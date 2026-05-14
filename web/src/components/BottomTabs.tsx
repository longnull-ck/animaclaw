import { useState } from 'react'
import type { AnimaEvent, AnimaSnapshot } from '../hooks/useAnima'

interface Props {
  snapshot: AnimaSnapshot | null
  events: AnimaEvent[]
}

type Tab = 'questions' | 'memory' | 'evolution' | 'providers'

export function BottomTabs({ snapshot, events }: Props) {
  const [activeTab, setActiveTab] = useState<Tab>('questions')

  const tabs: { key: Tab; label: string; icon: string }[] = [
    { key: 'questions', label: '问题树', icon: '❓' },
    { key: 'memory', label: '记忆库', icon: '💾' },
    { key: 'evolution', label: '进化日志', icon: '🧬' },
    { key: 'providers', label: '模型', icon: '🤖' },
  ]

  return (
    <div className="h-full flex flex-col">
      {/* Tab 切换栏 */}
      <div className="flex border-b border-anima-border flex-shrink-0">
        {tabs.map(tab => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`px-4 py-2 text-xs font-medium transition-colors ${
              activeTab === tab.key
                ? 'text-anima-accent border-b-2 border-anima-accent bg-anima-accent/5'
                : 'text-anima-muted hover:text-anima-text'
            }`}
          >
            {tab.icon} {tab.label}
          </button>
        ))}
      </div>

      {/* Tab 内容 */}
      <div className="flex-1 overflow-y-auto p-3">
        {activeTab === 'questions' && <QuestionsTab snapshot={snapshot} />}
        {activeTab === 'memory' && <MemoryTab events={events} />}
        {activeTab === 'evolution' && <EvolutionTab snapshot={snapshot} events={events} />}
        {activeTab === 'providers' && <ProvidersTab snapshot={snapshot} />}
      </div>
    </div>
  )
}

// ── 问题树 Tab ───────────────────────────────────────────────

function QuestionsTab({ snapshot }: { snapshot: AnimaSnapshot | null }) {
  const stats = snapshot?.questions
  if (!stats) return <Empty text="暂无数据" />

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-4 gap-2 text-center">
        <MiniStat label="待处理" value={stats.pending} color="text-anima-warm" />
        <MiniStat label="进行中" value={stats.in_progress} color="text-anima-accent" />
        <MiniStat label="已解决" value={stats.resolved} color="text-green-400" />
        <MiniStat label="总计" value={stats.total} color="text-anima-text" />
      </div>
      <p className="text-xs text-anima-muted">
        问题树是 Anima 的驱动力——每个需求产生问题，问题衍生子问题，优先级高的先处理。
      </p>
    </div>
  )
}

// ── 记忆库 Tab ───────────────────────────────────────────────

function MemoryTab({ events }: { events: AnimaEvent[] }) {
  const memoryEvents = events.filter(e => e.type === 'memory').slice(-20)

  if (memoryEvents.length === 0) {
    return <Empty text="暂无记忆操作记录" />
  }

  return (
    <div className="space-y-1.5">
      {memoryEvents.map((e, i) => (
        <div key={e.id + i} className="flex items-center gap-2 text-xs py-1 border-b border-anima-border/30">
          <span>{e.icon}</span>
          <span className="font-medium">{e.title}</span>
          <span className="text-anima-muted truncate flex-1">{e.detail}</span>
        </div>
      ))}
    </div>
  )
}

// ── 进化日志 Tab ─────────────────────────────────────────────

function EvolutionTab({ snapshot, events }: { snapshot: AnimaSnapshot | null; events: AnimaEvent[] }) {
  const evoEvents = events.filter(e => e.type === 'evolution').slice(-15)
  const stats = snapshot?.evolution

  return (
    <div className="space-y-3">
      {stats && (
        <div className="grid grid-cols-4 gap-2 text-center">
          <MiniStat label="经历" value={stats.total_experiences} color="text-anima-accent2" />
          <MiniStat label="成功率" value={`${Math.round(stats.success_rate * 100)}%`} color="text-anima-accent" />
          <MiniStat label="满意度" value={`${Math.round(stats.avg_owner_satisfaction * 100)}%`} color="text-anima-warm" />
          <MiniStat label="方法论" value={stats.methodology_count} color="text-pink-400" />
        </div>
      )}
      <div className="space-y-1">
        {evoEvents.map((e, i) => (
          <div key={e.id + i} className="text-xs py-1 border-b border-anima-border/30">
            <span className="mr-1">{e.icon}</span>
            <span className="font-medium">{e.title}</span>
            {e.detail && <span className="text-anima-muted ml-2">{e.detail}</span>}
          </div>
        ))}
        {evoEvents.length === 0 && <Empty text="暂无进化日志" />}
      </div>
    </div>
  )
}

// ── 模型 Provider Tab ────────────────────────────────────────

function ProvidersTab({ snapshot }: { snapshot: AnimaSnapshot | null }) {
  const providers = snapshot?.providers
  if (!providers) return <Empty text="暂无 Provider 数据" />

  return (
    <div className="space-y-2">
      <div className="text-xs text-anima-muted">
        当前活跃: <span className="text-anima-accent font-medium">{providers.active || '无'}</span>
        {providers.active_model && (
          <span className="ml-2">模型: <span className="text-anima-accent2">{providers.active_model}</span></span>
        )}
      </div>
      <p className="text-xs text-anima-muted">
        共 {providers.total_providers} 个 Provider，{providers.enabled} 个已启用。
        支持自动 failover：主力失败自动切换到备用。
      </p>
    </div>
  )
}

// ── 工具组件 ─────────────────────────────────────────────────

function MiniStat({ label, value, color }: { label: string; value: string | number; color: string }) {
  return (
    <div>
      <div className={`text-base font-bold ${color}`}>{value}</div>
      <div className="text-xs text-anima-muted">{label}</div>
    </div>
  )
}

function Empty({ text }: { text: string }) {
  return <p className="text-xs text-anima-muted text-center py-4">{text}</p>
}
