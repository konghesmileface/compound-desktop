import React, { useRef, useState, useEffect, useMemo, useCallback } from 'react'
import ForceGraph2D from 'react-force-graph-2d'
import { api } from './api'
import { Empty } from './ui'
import { IconNetwork } from './icons'

// 仅聊天·人脉关系网:每个联系人一颗星,按社区上色(Obsidian 式);
// 机构/项目做成◆枢纽节点,把围着它的人聚在一起。
const COMM_COLORS = ['#7c8bff', '#ff6b8b', '#22c9ff', '#28e0a8', '#ffc63d', '#b57bff', '#ff8bd4', '#00d9c0', '#ff9445', '#b6e635', '#4aa8ff', '#ff7ac2']
const ENT_COL = '#ffd166'   // 机构枢纽统一暖金,和人区分

let _graphCache = null   // 模块级缓存:切 tab 重挂时复用,避免每次重拉 407 节点(P1-17)
export default function ContactGraph({ onOpen }) {
  const [graph, setGraph] = useState(_graphCache)
  const [showEnt, setShowEnt] = useState(true)
  const hostRef = useRef()
  const fgRef = useRef()
  const [dim, setDim] = useState({ w: 800, h: 520 })
  const [hoverId, setHoverId] = useState(null)
  // B1:页面不可见时让 ForceGraph 暂停重绘(可见时保持连续重绘=呼吸动画照旧)
  const [pageHidden, setPageHidden] = useState(false)
  useEffect(() => {
    const onVis = () => setPageHidden(!!document.hidden)
    document.addEventListener('visibilitychange', onVis)
    return () => document.removeEventListener('visibilitychange', onVis)
  }, [])

  useEffect(() => {
    if (_graphCache) return   // 已有缓存,本次挂载不再重拉
    api.relGraph().then((g) => { _graphCache = g; setGraph(g) }).catch(() => setGraph({ nodes: [], edges: [] }))
  }, [])
  // 力导调参:加大斥力 + 拉长连线,把挤成一团的节点摊开
  useEffect(() => {
    const fg = fgRef.current
    if (!fg || !graph) return
    try {
      // 407 个节点:强斥力 + 宽作用域 → 圈子互相推开摊成 Obsidian 那种舒展布局(治"全挤中间")
      fg.d3Force('charge').strength(-320).distanceMax(620)
      const link = fg.d3Force('link'); if (link) link.distance(64).strength(0.14)
      const c = fg.d3Force('center'); if (c && c.strength) c.strength(0.02)   // 几乎不向心,靠斥力铺开
      fg.d3ReheatSimulation()
    } catch (e) { /* noop */ }
  }, [graph])
  useEffect(() => {
    const el = hostRef.current
    if (!el) return
    const ro = new ResizeObserver(() => setDim({ w: el.clientWidth || 800, h: el.clientHeight || 520 }))
    ro.observe(el)
    return () => ro.disconnect()
  }, [graph])

  const data = useMemo(() => {
    if (!graph) return { nodes: [], links: [] }
    const rawNodes = (graph.nodes || []).filter((n) => showEnt || n.kind !== 'entity')
    const nodes = rawNodes.map((n) => ({
      id: n.name, name: n.label || n.name, kind: n.kind || 'person',
      degree: n.degree || 0, community: n.community || 0, doc_id: n.doc_id,
    }))
    const ids = new Set(nodes.map((n) => n.id))
    const commOf = {}; nodes.forEach((n) => { commOf[n.id] = n.community })
    const links = (graph.edges || []).filter((e) => ids.has(e.a) && ids.has(e.b))
      .map((e) => ({ source: e.a, target: e.b, value: e.strength || 1, kind: 'person',
        comm: commOf[e.a] === commOf[e.b] ? commOf[e.a] : -1 }))
    if (showEnt) {
      (graph.ent_links || []).filter((e) => ids.has(e.a) && ids.has(e.b))
        .forEach((e) => links.push({ source: e.a, target: e.b, value: 1, kind: 'entity', comm: commOf[e.b] }))
    }
    // 孤立点(无任何连线)钉成外围一圈"星环":不挤中间、不参与力学,主体网络独占中心舞台
    const linked = new Set()
    links.forEach((l) => { linked.add(l.source); linked.add(l.target) })
    const iso = nodes.filter((n) => !linked.has(n.id))
    iso.forEach((n, i) => {
      const a = (i / Math.max(iso.length, 1)) * Math.PI * 2
      const r = 560 + (i % 3) * 46   // 三圈错开,别叠成一条线
      n.fx = Math.cos(a) * r; n.fy = Math.sin(a) * r
    })
    return { nodes, links }   // 保留所有联系人(孤立点固定在外环),数据一个不删
  }, [graph, showEnt])

  // 撑开布局:默认斥力太弱,大团全缩在中心叠成一坨字(用户两次反馈)。数据一到就调力参数并重热。
  useEffect(() => {
    const fg = fgRef.current
    if (!fg || !data.nodes.length) return
    const ch = fg.d3Force('charge'); if (ch) { ch.strength(-320); ch.distanceMax && ch.distanceMax(700) }
    const lf = fg.d3Force('link'); if (lf) { lf.distance((l) => l.kind === 'entity' ? 130 : 90); lf.strength && lf.strength(0.25) }
    // 碰撞力:节点不再叠成一坨(半径+2 的安全间距)
    import('d3-force-3d').then((d3) => {
      fg.d3Force('collide', d3.forceCollide((n) => radiusOf(n) + 2.5).iterations(2))
      fg.d3ReheatSimulation && fg.d3ReheatSimulation()
    }).catch(() => { fg.d3ReheatSimulation && fg.d3ReheatSimulation() })
    // 初始取景:引擎常开不再触发 onEngineStop,定时收一次全景
    const t = setTimeout(() => fg.zoomToFit && fg.zoomToFit(600, 40), 6500)
    return () => clearTimeout(t)
  }, [data])

  const nbr = useMemo(() => {
    const m = new Map()
    data.links.forEach((l) => {
      const s = typeof l.source === 'object' ? l.source.id : l.source
      const t = typeof l.target === 'object' ? l.target.id : l.target
      if (!m.has(s)) m.set(s, new Set()); if (!m.has(t)) m.set(t, new Set())
      m.get(s).add(t); m.get(t).add(s)
    })
    return m
  }, [data])

  const radiusOf = (n) => n.kind === 'entity'
    ? Math.max(4, Math.min(10, 4 + (n.degree || 0) * 0.5))
    : Math.max(3, Math.min(10, 3 + (n.degree || 0) * 0.16))

  const paint = useCallback((n, ctx, scale) => {
    const isEnt = n.kind === 'entity'
    const r = radiusOf(n)
    // 生命感:绘制层做小幅椭圆漂移(不扰动物理布局)。幅度换算成"屏幕恒定 ~4.5px",任何缩放都看得见在动
    const _t = Date.now() / 1150, _ph = (n.id.charCodeAt(0) || 0) * 0.7, _amp = Math.min(11, 4.5 / Math.max(0.4, scale))
    n = { ...n, x: n.x + Math.sin(_t + _ph) * _amp, y: n.y + Math.cos(_t * 0.82 + _ph) * _amp }
    const col = isEnt ? ENT_COL : COMM_COLORS[(n.community || 0) % COMM_COLORS.length]
    const active = hoverId && (n.id === hoverId || (nbr.get(hoverId) || new Set()).has(n.id))
    ctx.globalAlpha = hoverId && !active ? 0.13 : 1
    ctx.beginPath()
    if (isEnt) {   // 机构=菱形,和人的圆区分
      ctx.moveTo(n.x, n.y - r); ctx.lineTo(n.x + r, n.y); ctx.lineTo(n.x, n.y + r); ctx.lineTo(n.x - r, n.y); ctx.closePath()
    } else {
      ctx.arc(n.x, n.y, r, 0, 2 * Math.PI)
    }
    // 干净实心点(Obsidian式),不发光糊成一片;只有悬停高亮的点才给一点辉光聚焦
    ctx.fillStyle = col
    if (active) { ctx.shadowColor = col; ctx.shadowBlur = 14 }
    ctx.fill(); ctx.shadowBlur = 0
    ctx.lineWidth = (isEnt ? 0.9 : 0.7) / scale
    ctx.strokeStyle = isEnt ? 'rgba(255,255,255,0.55)' : 'rgba(0,0,0,0.35)'
    ctx.stroke()
    // 只显:悬停的那一个节点(不再连它所有邻居一起画字→治"悬停后名字堆成团")、放大后、或极少数大枢纽
    if (n.id === hoverId || scale > 1.9 || (scale > 0.85 && ((isEnt && (n.degree || 0) >= 22) || (!isEnt && (n.degree || 0) >= 50)))) {
      const label = String(n.name).slice(0, isEnt ? 9 : 10)
      const fs = Math.max(6, (isEnt ? 11 : 11.5) / scale)
      ctx.font = `${isEnt ? 700 : 600} ${fs}px -apple-system, "SF Pro Text", sans-serif`
      ctx.textAlign = 'center'; ctx.textBaseline = 'top'
      const tw = ctx.measureText(label).width
      const pad = 4 / scale, ly = n.y + r + 4 / scale, h = fs + pad
      ctx.fillStyle = 'rgba(9,11,17,0.78)'   // 深色半透明底,让字在花花绿绿里可读
      const x0 = n.x - tw / 2 - pad, w = tw + pad * 2, rr = 3 / scale
      ctx.beginPath()
      if (ctx.roundRect) { ctx.roundRect(x0, ly - pad * 0.4, w, h, rr) } else { ctx.rect(x0, ly - pad * 0.4, w, h) }
      ctx.fill()
      ctx.fillStyle = isEnt ? '#ffdd8f' : '#f2f4fa'
      ctx.fillText(label, n.x, ly)
    }
    ctx.globalAlpha = 1
  }, [hoverId, nbr])

  if (!graph) return <div className="cg-host"><Empty loading title="正在生成人脉关系网" sub="AI 在通读你的聊天,识别圈子、机构与关系" /></div>
  if (!data.nodes.length) return <div className="cg-host"><Empty icon={<IconNetwork />} title="还没有人脉关系网" sub="导入微信聊天后,这里会长出你的人脉关系网——每颗星是一个人,连线是共同的机构 / 项目 / 事" /></div>

  const entN = (graph.nodes || []).filter((n) => n.kind === 'entity').length

  return (
    <div className="cg-host" ref={hostRef}>
      {entN > 0 && (
        <button className={'cg-toggle' + (showEnt ? ' on' : '')} onClick={() => setShowEnt((v) => !v)}>
          {showEnt ? '◆ 机构枢纽 · 显示中' : '◆ 显示机构枢纽'}
        </button>
      )}
      <button className="cg-reset" onClick={() => fgRef.current && fgRef.current.zoomToFit(400, 40)}>回到全景</button>
      <ForceGraph2D
        ref={fgRef} width={dim.w} height={dim.h} graphData={data}
        backgroundColor="rgba(0,0,0,0)"
        nodeCanvasObject={paint} nodeCanvasObjectMode={() => 'replace'}
        nodePointerAreaPaint={(n, color, ctx) => { ctx.fillStyle = color; ctx.beginPath(); ctx.arc(n.x, n.y, radiusOf(n) + 3, 0, 2 * Math.PI); ctx.fill() }}
        enableNodeDrag={true}
        nodeLabel={(n) => n.kind === 'entity'
          ? `<div style="padding:6px 10px;font-size:12px;font-weight:600;color:#ffd166;background:rgba(12,14,20,0.95);border:1px solid rgba(255,209,102,0.35);border-radius:8px">${n.name}<div style="font-size:10.5px;font-weight:400;color:#9aa0aa;margin-top:1px">机构/项目枢纽 · ${n.degree} 人共有</div></div>`
          : `<div style="padding:6px 10px;font-size:12px;font-weight:600;color:#edeff3;background:rgba(12,14,20,0.95);border:1px solid rgba(255,255,255,0.12);border-radius:8px">${n.name}<div style="font-size:10.5px;font-weight:400;color:#9aa0aa;margin-top:1px">${n.degree} 个关联 · 点击看聊天</div></div>`}
        linkColor={(l) => {
          const s = typeof l.source === 'object' ? l.source.id : l.source
          const t = typeof l.target === 'object' ? l.target.id : l.target
          if (hoverId) return (s === hoverId || t === hoverId) ? 'rgba(180,200,255,0.65)' : 'rgba(139,140,255,0.025)'
          if (l.kind === 'entity') return 'rgba(255,209,102,0.14)'
          // 同社区内的边染成社区色(Obsidian 招牌),跨社区淡灰
          if (l.comm >= 0) { const c = COMM_COLORS[l.comm % COMM_COLORS.length]; return c + '2e' }
          return 'rgba(150,155,175,0.07)'
        }}
        linkWidth={(l) => l.kind === 'entity' ? 0.6 : Math.min(3.5, (l.value || 1) * 0.35)}
        linkDirectionalParticles={(l) => (l.kind !== 'entity' && (l.value || 1) >= 2) ? 1 : 0}
        linkDirectionalParticleWidth={1.8}
        linkDirectionalParticleSpeed={0.005}
        linkDirectionalParticleColor={(l) => {
          const s = typeof l.source === 'object' ? l.source.id : l.source
          const t = typeof l.target === 'object' ? l.target.id : l.target
          return (hoverId && (s === hoverId || t === hoverId)) ? 'rgba(190,210,255,0.95)' : 'rgba(150,165,230,0.5)'
        }}
        onNodeHover={(n) => setHoverId(n ? n.id : null)}
        onNodeClick={(n) => n.kind !== 'entity' && n.doc_id != null && onOpen && onOpen(n.doc_id)}
        cooldownTicks={300}
        cooldownTime={22000}
        d3AlphaDecay={0.02}
        autoPauseRedraw={pageHidden}
        enablePanInteraction={false}
        onEngineTick={() => {
          // 向心力 + 半径硬约束:主体和小分量都圈在星环内,取景永远居中(孤立点已钉外环)
          for (const n of data.nodes) {
            if (n.x == null || n.fx != null) continue
            n.vx = (n.vx || 0) - n.x * 0.0045; n.vy = (n.vy || 0) - n.y * 0.0045
            const r = Math.hypot(n.x, n.y)
            if (r > 470) { const k = 470 / r; n.x *= k; n.y *= k }
          }
        }}
        onEngineStop={() => fgRef.current && fgRef.current.zoomToFit(500, 40)}
      />
    </div>
  )
}
