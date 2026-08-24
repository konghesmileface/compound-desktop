import React, { useState, useRef, useEffect, useMemo, useCallback } from 'react'
import { createPortal } from 'react-dom'
import ForceGraph2D from 'react-force-graph-2d'

// 群成员熟络度:窄抽屉里给清单(好扫、带依据),点「关系图」展开大浮层看真正的关系网。
// 数据来自 LLM 对真实群聊的分析。
const CLR = { '高': '#34d399', '中': '#8b8cff', '低': '#9aa0aa' }
const RANK = { '高': 0, '中': 1, '低': 2 }
const CW = { '高': 2.2, '中': 1.3, '低': 0.7 }
// 成员配色(按名字哈希,稳定):暖冷交错,和金色的「我」区分
const PAL = ['#7c8bff', '#fb7185', '#22c9ff', '#f472b6', '#38bdf8', '#c084fc', '#2dd4bf', '#fb923c', '#a3e635', '#60a5fa']
function colorOf(name) { let h = 0; for (const c of name) h = (h * 31 + c.charCodeAt(0)) & 0xffff; return PAL[h % PAL.length] }

function Badge({ c }) {
  const col = CLR[c] || CLR['中']
  return <span className="ggl-badge" style={{ color: col, borderColor: col + '66', background: col + '1e' }}>{c}</span>
}

// ---- 大图浮层 ----
function GraphModal({ members, edges, meName, onClose }) {
  const hostRef = useRef(); const fgRef = useRef()
  const [dim, setDim] = useState({ w: 900, h: 600 })
  const [hoverId, setHoverId] = useState(null)

  useEffect(() => {
    const el = hostRef.current; if (!el) return
    const ro = new ResizeObserver(() => setDim({ w: el.clientWidth || 900, h: el.clientHeight || 600 }))
    ro.observe(el); return () => ro.disconnect()
  }, [])
  useEffect(() => {
    const fg = fgRef.current; if (!fg) return
    // 节点少时斥力要小,否则弱连接的点会被甩到角落飘出去;再加 x/y 向心力把它们收回中心
    try {
      fg.d3Force('charge').strength(-80).distanceMax(260)
      const l = fg.d3Force('link'); if (l) l.distance(62)
      const c = fg.d3Force('center'); if (c && c.strength) c.strength(1)
      fg.d3ReheatSimulation()
    } catch (e) {}
  }, [])

  const graph = useMemo(() => {
    const names = new Set(members.map((m) => m.name))
    const deg = {}; edges.forEach((e) => { deg[e.a] = (deg[e.a] || 0) + 1; deg[e.b] = (deg[e.b] || 0) + 1 })
    // 只画有连线的成员(孤点没关系,画出来只会飘散在空白处)
    return {
      // 「我」钉在正中心(fx/fy=0),自我为中心的关系网,永远居中可见,其他人环绕——治"我飘出去"
      nodes: members.filter((m) => (deg[m.name] || 0) > 0 || m.is_me).map((m) => ({
        id: m.name, name: m.name, role: m.role || '', is_me: !!m.is_me, degree: deg[m.name] || 0,
        ...(m.is_me ? { fx: 0, fy: 0 } : {}),
      })),
      links: edges.filter((e) => names.has(e.a) && names.has(e.b)).map((e) => ({ source: e.a, target: e.b, closeness: e.closeness || '中', why: e.why || '' })),
    }
  }, [members, edges])
  const radiusOf = (n) => n.is_me ? 13 : Math.max(6, Math.min(15, 6 + (n.degree || 0) * 1.2))

  const nbr = useMemo(() => {
    const m = new Map()
    graph.links.forEach((l) => {
      const s = typeof l.source === 'object' ? l.source.id : l.source, t = typeof l.target === 'object' ? l.target.id : l.target
      if (!m.has(s)) m.set(s, new Set()); if (!m.has(t)) m.set(t, new Set()); m.get(s).add(t); m.get(t).add(s)
    })
    return m
  }, [graph])

  const paint = useCallback((n, ctx, scale) => {
    if (!Number.isFinite(n.x) || !Number.isFinite(n.y)) return
    const r = radiusOf(n)
    const col = n.is_me ? '#e8b923' : colorOf(n.name)
    const active = !hoverId || n.id === hoverId || (nbr.get(hoverId) || new Set()).has(n.id)
    ctx.globalAlpha = active ? 1 : 0.22
    // 现代扁平:实心圆,无渐变无辉光;仅一圈与底色同调的细描边分隔重叠
    ctx.beginPath(); ctx.arc(n.x, n.y, r, 0, 2 * Math.PI)
    ctx.fillStyle = col; ctx.fill()
    ctx.lineWidth = 1.5 / scale
    ctx.strokeStyle = 'rgba(10,12,18,0.9)'   // 深色描边=干净分隔,不是发光
    ctx.stroke()
    if (n.is_me) {   // "我"=外层一道细白环,克制地强调,不发光
      ctx.beginPath(); ctx.arc(n.x, n.y, r + 3 / scale, 0, 2 * Math.PI)
      ctx.lineWidth = 1.5 / scale; ctx.strokeStyle = 'rgba(255,255,255,0.85)'; ctx.stroke()
    }
    // 标签:细字重、字距,现代感;深色描边保证可读(非辉光)
    const fs = Math.max(9, 12 / scale)
    ctx.font = `${n.is_me ? 700 : 500} ${fs}px -apple-system, "SF Pro Text", sans-serif`
    ctx.textAlign = 'center'; ctx.textBaseline = 'top'
    ctx.lineWidth = 3 / scale; ctx.strokeStyle = 'rgba(8,10,15,0.92)'
    ctx.strokeText((n.is_me ? '我' : '') + String(n.name).slice(0, 10), n.x, n.y + r + 5 / scale)
    ctx.fillStyle = n.is_me ? '#f0d074' : 'rgba(228,231,238,0.95)'
    ctx.fillText((n.is_me ? '我' : '') + String(n.name).slice(0, 10), n.x, n.y + r + 5 / scale)
    ctx.globalAlpha = 1
  }, [hoverId, nbr])

  return createPortal(
    <div className="ggm-overlay" onClick={onClose}>
      <div className="ggm-panel" onClick={(e) => e.stopPropagation()}>
        <div className="ggm-head">
          <span className="ggm-title">成员关系网</span>
          <span className="ggm-legend">
            <span><i className="gg-dot me" />我</span>
            <span><i className="ggm-line hi" />熟络高</span><span><i className="ggm-line mid" />中</span><span><i className="ggm-line lo" />低</span>
            <span className="gg-hint">悬停看依据 · 滚轮缩放</span>
          </span>
          <button className="ggm-close" onClick={onClose}>×</button>
        </div>
        <div className="ggm-host" ref={hostRef}>
          <ForceGraph2D ref={fgRef} width={dim.w} height={dim.h} graphData={graph} backgroundColor="rgba(0,0,0,0)"
            nodeCanvasObject={paint} nodeCanvasObjectMode={() => 'replace'} enableNodeDrag={true}
            nodePointerAreaPaint={(n, color, ctx) => { ctx.fillStyle = color; ctx.beginPath(); ctx.arc(n.x, n.y, radiusOf(n) + 4, 0, 2 * Math.PI); ctx.fill() }}
            nodeLabel={(n) => n.role ? `<div style="padding:6px 10px;font-size:12px;color:#edeff3;background:rgba(12,14,20,0.96);border:1px solid rgba(255,255,255,0.14);border-radius:8px">${n.is_me ? '我 · ' : ''}${n.name}<div style="font-size:10.5px;color:#9aa0aa">${n.role}</div></div>` : ''}
            linkColor={(l) => {
              const s = typeof l.source === 'object' ? l.source.id : l.source, t = typeof l.target === 'object' ? l.target.id : l.target
              if (hoverId) return (s === hoverId || t === hoverId) ? 'rgba(200,212,255,0.85)' : 'rgba(139,140,255,0.04)'
              return (CLR[l.closeness] || CLR['中']) + '85'
            }}
            linkWidth={(l) => CW[l.closeness] || 1.9}
            linkCurvature={0.13}
            linkDirectionalParticles={(l) => { const s = typeof l.source === 'object' ? l.source.id : l.source, t = typeof l.target === 'object' ? l.target.id : l.target; if (hoverId && s !== hoverId && t !== hoverId) return 0; return l.closeness === '高' ? 3 : l.closeness === '中' ? 2 : 0 }}
            linkDirectionalParticleWidth={(l) => l.closeness === '高' ? 2.6 : 2}
            linkDirectionalParticleSpeed={(l) => l.closeness === '高' ? 0.008 : 0.005}
            linkDirectionalParticleColor={(l) => CLR[l.closeness] || CLR['中']}
            linkLabel={(l) => l.why ? `<div style="padding:5px 9px;font-size:11.5px;color:#e6e9ef;background:rgba(12,14,20,0.96);border:1px solid rgba(255,255,255,0.12);border-radius:7px;max-width:260px">熟络度 ${l.closeness}：${l.why}</div>` : ''}
            onNodeHover={(n) => setHoverId(n ? n.id : null)}
            cooldownTicks={180} onEngineStop={() => fgRef.current && fgRef.current.zoomToFit(500, 70)} />
        </div>
      </div>
    </div>, document.body)
}

export default function GroupGraph({ data }) {
  const [modal, setModal] = useState(false)
  if (!data || !data.found) return <div className="gg-empty">这个群还没解析出成员关系</div>
  const members = data.members || []
  const edges = data.edges || []
  if (!members.length) return <div className="gg-empty">群里活跃发言的人太少,分析不出关系</div>

  const me = members.find((m) => m.is_me)
  const meName = me && me.name
  const roleOf = {}; members.forEach((m) => { roleOf[m.name] = m.role || '' })
  const mine = [], pairs = []
  edges.forEach((e) => {
    if (meName && (e.a === meName || e.b === meName)) mine.push({ name: e.a === meName ? e.b : e.a, closeness: e.closeness || '中', why: e.why || '' })
    else pairs.push({ a: e.a, b: e.b, closeness: e.closeness || '中', why: e.why || '' })
  })
  mine.sort((a, b) => (RANK[a.closeness] ?? 1) - (RANK[b.closeness] ?? 1))
  pairs.sort((a, b) => (RANK[a.closeness] ?? 1) - (RANK[b.closeness] ?? 1))

  return (
    <div className="ggl">
      <div className="ggl-top">
        <div className="ggl-sub">群里 <b>{members.length}</b> 人 · 熟络度来自真实聊天分析</div>
        {edges.length > 0 && <button className="ggl-graphbtn" onClick={() => setModal(true)}>展开关系图</button>}
      </div>

      {mine.length > 0 && (
        <div className="ggl-sec">
          <div className="ggl-h">你和群里谁最熟</div>
          {mine.map((m, i) => (
            <div key={i} className="ggl-row">
              <Badge c={m.closeness} />
              <div className="ggl-main">
                <div className="ggl-name">{m.name}{roleOf[m.name] ? <span className="ggl-role"> · {roleOf[m.name]}</span> : ''}</div>
                {m.why && <div className="ggl-why">{m.why}</div>}
              </div>
            </div>
          ))}
        </div>
      )}

      {pairs.length > 0 && (
        <div className="ggl-sec">
          <div className="ggl-h">群里成员之间</div>
          {pairs.map((p, i) => (
            <div key={i} className="ggl-row">
              <Badge c={p.closeness} />
              <div className="ggl-main">
                <div className="ggl-name">{p.a} <span className="ggl-amp">↔</span> {p.b}</div>
                {p.why && <div className="ggl-why">{p.why}</div>}
              </div>
            </div>
          ))}
        </div>
      )}

      {mine.length === 0 && pairs.length === 0 && <div className="gg-empty">没抽出明显的成员关系</div>}
      <div className="ggl-legend"><i style={{ background: CLR['高'] }} />熟络高<i style={{ background: CLR['中'] }} />中<i style={{ background: CLR['低'] }} />低</div>

      {modal && <GraphModal members={members} edges={edges} meName={meName} onClose={() => setModal(false)} />}
    </div>
  )
}
