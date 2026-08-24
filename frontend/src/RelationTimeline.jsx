import React, { useMemo } from 'react'

// 我和某人的关系随时间变化:月度互动强度(真实时间戳)+ 关键节点 + 走势。
// months: [{ym:'2023-02', count, mine, theirs}], milestones:[{date, label}], trajectory, phase
export default function RelationTimeline({ data, onOpen }) {
  const months = (data && data.months) || []
  const milestones = (data && data.milestones) || []
  const docId = data && data.doc_id
  const jump = () => { if (onOpen && docId != null) onOpen(docId) }

  const chart = useMemo(() => {
    if (!months.length) return null
    const W = 680, H = 132, padB = 18, padT = 8
    const n = months.length
    const gap = 2
    const bw = Math.max(2, (W - (n - 1) * gap) / n)
    const maxc = Math.max(1, ...months.map((m) => m.count))
    const sq = (v) => Math.sqrt(v) / Math.sqrt(maxc)   // sqrt 缩放:小月份也看得见
    const bars = months.map((m, i) => {
      const x = i * (bw + gap)
      const h = sq(m.count) * (H - padB - padT)
      const mineFrac = m.count ? m.mine / m.count : 0
      return { x, w: bw, hTotal: h, hMine: h * mineFrac, ym: m.ym, count: m.count, mine: m.mine, theirs: m.theirs, i }
    })
    const xOfYm = (ym) => {
      let idx = months.findIndex((m) => m.ym === ym)
      if (idx < 0) idx = months.findIndex((m) => m.ym >= ym)   // 就近
      if (idx < 0) idx = n - 1
      return idx * (bw + gap) + bw / 2
    }
    // 年份刻度
    const years = []
    let lastY = ''
    months.forEach((m, i) => { const y = m.ym.slice(0, 4); if (y !== lastY) { years.push({ y, x: i * (bw + gap) }); lastY = y } })
    // 里程碑落点
    const mile = milestones.map((ms, k) => ({ ...ms, x: xOfYm(String(ms.date || '').slice(0, 7)), n: k + 1 }))
    return { W, H, padB, bars, years, mile, baseY: H - padB }
  }, [months, milestones])

  if (!data || !data.found) return <div className="gg-empty">这个联系人还没解析出关系走势</div>
  if (!months.length) return <div className="gg-empty">聊天里没有可用的时间信息,画不出走势</div>

  return (
    <div className="rt-wrap">
      {(data.phase || data.trajectory) && (
        <div className="rt-head">
          {data.phase && <span className="rt-phase">{data.phase}</span>}
          {data.trajectory && <span className="rt-traj">{data.trajectory}</span>}
        </div>
      )}
      <div className="rt-chart">
        <svg viewBox={`0 0 ${chart.W} ${chart.H}`} width="100%" preserveAspectRatio="none" style={{ display: 'block' }}>
          <defs>
            <linearGradient id="rtTheirs" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor="#7c8bff" stopOpacity="0.85" /><stop offset="1" stopColor="#7c8bff" stopOpacity="0.35" />
            </linearGradient>
          </defs>
          {chart.years.map((y, i) => (
            <g key={i}>
              <line x1={y.x} y1={chart.padB ? 4 : 0} x2={y.x} y2={chart.baseY} stroke="rgba(255,255,255,0.06)" strokeWidth="1" />
              <text x={y.x + 2} y={chart.H - 5} fontSize="9" fill="rgba(154,163,176,0.8)">{y.y}</text>
            </g>
          ))}
          {chart.bars.map((b) => (
            <g key={b.i}>
              <rect x={b.x} y={chart.baseY - b.hTotal} width={b.w} height={b.hTotal} fill="url(#rtTheirs)" rx="0.8">
                <title>{b.ym}:共 {b.count} 条(我 {b.mine} / TA {b.theirs})</title>
              </rect>
              <rect x={b.x} y={chart.baseY - b.hMine} width={b.w} height={b.hMine} fill="#ffd166" fillOpacity="0.9" rx="0.8" />
            </g>
          ))}
          <line x1="0" y1={chart.baseY} x2={chart.W} y2={chart.baseY} stroke="rgba(255,255,255,0.14)" strokeWidth="1" />
          {chart.mile.map((m, i) => (
            <g key={i} style={{ cursor: onOpen ? 'pointer' : 'default' }} onClick={jump}>
              <line x1={m.x} y1={8} x2={m.x} y2={chart.baseY} stroke="rgba(255,209,102,0.35)" strokeWidth="1" strokeDasharray="2 2" />
              <circle cx={m.x} cy={8} r="6.5" fill="#ffd166" />
              <text x={m.x} y={11} fontSize="8.5" fontWeight="700" fill="#06080d" textAnchor="middle">{m.n}</text>
            </g>
          ))}
        </svg>
      </div>
      <div className="rt-legend">
        <span><i className="gg-dot" style={{ background: '#7c8bff' }} />TA 发的</span>
        <span><i className="gg-dot" style={{ background: '#ffd166' }} />我发的</span>
        <span className="gg-hint">柱高=当月互动量 · 悬停看数</span>
      </div>
      {chart.mile.length > 0 && (
        <div className="rt-miles">
          {chart.mile.map((m, i) => (
            <div key={i} className={'rt-mile' + (onOpen ? ' clickable' : '')} onClick={jump} title={onOpen ? '看这段聊天' : ''}>
              <span className="rt-mile-n">{m.n}</span>
              <span className="rt-mile-date">{m.date}</span>
              <span className="rt-mile-label">{m.label}</span>
            </div>
          ))}
        </div>
      )}
      {onOpen && docId != null && (
        <button className="rt-jump" onClick={jump}>翻这段聊天原文 →</button>
      )}
    </div>
  )
}
