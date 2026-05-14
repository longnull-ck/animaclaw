import type { AnimaSnapshot } from '../hooks/useAnima'

interface Props {
  connected: boolean
  snapshot: AnimaSnapshot | null
}

export function StatusBar({ connected, snapshot }: Props) {
  const name = snapshot?.identity?.name || 'Anima'
  const model = snapshot?.providers?.active_model || '未连接'

  return (
    <header className="h-12 bg-anima-card border-b border-anima-border flex items-center px-4 gap-4 flex-shrink-0">
      {/* Logo + 名字 */}
      <div className="flex items-center gap-2">
        <div className={`w-3 h-3 rounded-full ${connected ? 'bg-anima-accent animate-pulse-slow' : 'bg-anima-danger'}`} />
        <span className="font-bold text-lg">🦾 {name}</span>
        <span className="text-xs text-anima-muted">员工控制中心</span>
      </div>

      {/* 间隔 */}
      <div className="flex-1" />

      {/* 状态指标 */}
      <div className="flex items-center gap-4 text-xs text-anima-muted">
        <span>模型: <span className="text-anima-accent">{model}</span></span>
        <span>信任: <span className="text-anima-warm">{snapshot?.trust?.score ?? 0}分</span></span>
        <span>技能: <span className="text-anima-accent2">{snapshot?.skills?.length ?? 0}个</span></span>
        <span className={connected ? 'text-anima-accent' : 'text-anima-danger'}>
          {connected ? '● 在线' : '○ 离线'}
        </span>
      </div>
    </header>
  )
}
