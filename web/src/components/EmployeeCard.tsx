import type { AnimaSnapshot } from '../hooks/useAnima'

interface Props {
  snapshot: AnimaSnapshot | null
}

const DOMAIN_LABELS: Record<string, string> = {
  media: '传媒/营销', sales: '销售/客户', finance: '财务',
  operations: '运营', hr: '人力资源', engineering: '技术研发',
  research: '研究分析', legal: '法务合规',
  logistics: '物流供应链', customer_service: '客户服务',
}

export function EmployeeCard({ snapshot }: Props) {
  if (!snapshot?.identity) {
    return (
      <div className="text-center text-anima-muted py-12 animate-fade-in">
        <div className="text-4xl mb-4">🦾</div>
        <p>等待连接...</p>
        <p className="text-xs mt-2">请确保 Anima 后端正在运行</p>
      </div>
    )
  }

  const { identity, trust, skills, evolution } = snapshot
  const trustPercent = trust.score

  return (
    <div className="space-y-5 animate-fade-in">
      {/* 头像区域 */}
      <div className="text-center">
        <div className="w-20 h-20 mx-auto rounded-full bg-gradient-to-br from-anima-accent to-anima-accent2 flex items-center justify-center text-3xl shadow-lg animate-glow">
          🦾
        </div>
        <h2 className="text-xl font-bold mt-3">{identity.name}</h2>
        <p className="text-xs text-anima-muted">v{identity.version} · 服务于 {identity.owner_name}</p>
      </div>

      {/* 信任度 */}
      <div className="bg-anima-bg rounded-lg p-3">
        <div className="flex justify-between text-xs mb-1">
          <span className="text-anima-muted">信任等级</span>
          <span className="text-anima-warm font-medium">{trust.label}</span>
        </div>
        <div className="h-2 bg-anima-border rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-anima-accent to-anima-accent2 rounded-full transition-all duration-1000"
            style={{ width: `${trustPercent}%` }}
          />
        </div>
        <div className="flex justify-between text-xs mt-1 text-anima-muted">
          <span>{trustPercent}分</span>
          {trust.points_to_next !== null && (
            <span>距下级还差 {trust.points_to_next} 分</span>
          )}
        </div>
      </div>

      {/* 公司信息 */}
      <div className="bg-anima-bg rounded-lg p-3">
        <h3 className="text-xs text-anima-muted mb-1">公司业务</h3>
        <p className="text-sm">{identity.company_description}</p>
      </div>

      {/* 激活领域 */}
      <div className="bg-anima-bg rounded-lg p-3">
        <h3 className="text-xs text-anima-muted mb-2">已激活领域</h3>
        <div className="flex flex-wrap gap-1.5">
          {identity.active_domains.length > 0 ? (
            identity.active_domains.map(d => (
              <span key={d} className="px-2 py-0.5 bg-anima-accent/15 text-anima-accent text-xs rounded-full">
                {DOMAIN_LABELS[d] || d}
              </span>
            ))
          ) : (
            <span className="text-xs text-anima-muted">暂无（按需自动激活）</span>
          )}
        </div>
      </div>

      {/* 技能列表 */}
      <div className="bg-anima-bg rounded-lg p-3">
        <h3 className="text-xs text-anima-muted mb-2">已安装技能 ({skills.length})</h3>
        <div className="space-y-2 max-h-40 overflow-y-auto">
          {skills.map(s => (
            <div key={s.id} className="flex items-center gap-2">
              <div className="flex-1 text-xs">{s.name}</div>
              <div className="w-16 h-1.5 bg-anima-border rounded-full overflow-hidden">
                <div
                  className="h-full bg-anima-accent2 rounded-full"
                  style={{ width: `${s.proficiency * 100}%` }}
                />
              </div>
              <span className="text-xs text-anima-muted w-8 text-right">{Math.round(s.proficiency * 100)}%</span>
            </div>
          ))}
          {skills.length === 0 && (
            <p className="text-xs text-anima-muted">暂无技能（遇到任务后自动安装）</p>
          )}
        </div>
      </div>

      {/* 性格参数 */}
      <div className="bg-anima-bg rounded-lg p-3">
        <h3 className="text-xs text-anima-muted mb-2">性格参数</h3>
        <div className="space-y-1.5">
          <ParamBar label="主动程度" value={identity.personality.proactivity} color="from-anima-accent to-emerald-400" />
          <ParamBar label="决策激进度" value={identity.personality.risk_tolerance} color="from-anima-warm to-red-400" />
        </div>
      </div>

      {/* 进化统计 */}
      <div className="bg-anima-bg rounded-lg p-3 grid grid-cols-2 gap-2 text-center">
        <Stat label="经历总数" value={evolution.total_experiences} />
        <Stat label="成功率" value={`${Math.round(evolution.success_rate * 100)}%`} />
        <Stat label="满意度" value={`${Math.round(evolution.avg_owner_satisfaction * 100)}%`} />
        <Stat label="方法论" value={evolution.methodology_count} />
      </div>
    </div>
  )
}

function ParamBar({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-anima-muted w-16">{label}</span>
      <div className="flex-1 h-1.5 bg-anima-border rounded-full overflow-hidden">
        <div className={`h-full bg-gradient-to-r ${color} rounded-full`} style={{ width: `${value * 100}%` }} />
      </div>
      <span className="text-xs text-anima-muted w-8 text-right">{Math.round(value * 100)}%</span>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <div className="text-lg font-bold text-anima-accent">{value}</div>
      <div className="text-xs text-anima-muted">{label}</div>
    </div>
  )
}
