import React, { useEffect, useRef, useState, useMemo } from 'react'
import { api } from './api'

const initial = (s) => ([...(s || '?')][0] || '?').toUpperCase()
const hue = (s) => { let h = 0; for (let i = 0; i < (s || '').length; i++) h = (h * 31 + s.charCodeAt(i)) | 0; return Math.abs(h) % 360 }

// 领域聚类 → 星团配色
const CLUSTERS = {
  crypto: { color: '#f2a35a', re: /加密|defi|链|币|web3/i },
  human: { color: '#f9a8d4', re: /创作|诗|社群|运营|连接|设计|内容/i },
  tech: { color: '#8b93f8', re: /量化|机器学习|工程|代码|python|系统|研究|模型|数据/i },
  finance: { color: '#67e8f9', re: /./ },
}
function clusterOf(p) {
  const t = ((p.tags || []).join(' ') + ' ' + (p.one_liner || '') + ' ' + (p.display || ''))
  for (const k of ['crypto', 'human', 'tech', 'finance']) if (CLUSTERS[k].re.test(t)) return k
  return 'finance'
}

// 头像后面拖的一行介绍:MBTI · 一句话(截断)
function subOf(p) {
  const bits = []
  if (p.mbti) bits.push(p.mbti)
  const one = (p.one_liner || '').trim()
  if (one) bits.push(one.length > 14 ? one.slice(0, 14) + '…' : one)
  else if ((p.tags || []).length) bits.push(p.tags.slice(0, 2).join(' · '))
  return bits.join(' · ')
}

const golden = 2.399963229728653   // 黄金角,散布避免成行

export default function StarCloud({ people, onSelect, dim, me }) {
  const hostRef = useRef(); const svgRef = useRef(); const meRef = useRef()
  const nodeRefs = useRef({}); const lineRefs = useRef({}); const rafRef = useRef()
  const [imgs, setImgs] = useState({})
  const [q, setQ] = useState('')

  useEffect(() => {
    let alive = true
    const names = [me, ...people.map((p) => p.username)].filter(Boolean).join(',')
    api.getAvatars(names).then(({ avatars }) => { if (alive) setImgs(avatars || {}) }).catch(() => {})
    return () => { alive = false }
  }, [people, me])

  // 按契合度排序 → 分三层:核心(近大,带拖尾气泡)/ 中圈(头像+名字)/ 星尘(远小暗)
  const layered = useMemo(() => {
    const sorted = [...people].sort((a, b) => (b.compat || 0) - (a.compat || 0))
    const CORE = Math.min(3, sorted.length)
    const MID = Math.min(30, Math.max(0, sorted.length - CORE))
    return sorted.map((p, i) => {
      const tier = i < CORE ? 'core' : i < CORE + MID ? 'mid' : 'dust'
      return { p, tier, idx: i, color: CLUSTERS[clusterOf(p)].color }
    })
  }, [people])

  const top = people.length ? Math.max(...people.map((p) => p.compat || 0)) : 0
  // 命定星唯一:并列最高时也只认一颗(排序后第一个,且 compat>0),避免多颗都连粉线(P1-22)
  const loveKey = useMemo(() => {
    if (!people.length) return null
    const best = [...people].sort((a, b) => (b.compat || 0) - (a.compat || 0))[0]
    return best && (best.compat || 0) > 0 ? best.username : null
  }, [people])
  const ql = q.trim().toLowerCase()
  const matches = (p) => ql && ((p.display || '') + (p.one_liner || '') + (p.mbti || '') + (p.tags || []).join('')).toLowerCase().includes(ql)

  useEffect(() => {
    const host = hostRef.current; if (!host) return
    const w = dim.w || host.clientWidth, h = dim.h || host.clientHeight
    const cx = w / 2
    // 椭圆贴合屏幕:中心下移避开顶部导航/搜索框,横向用满宽度 → 自由散布铺满又不飘出/不被遮
    const marginX = 72, marginTop = 128, marginBottom = 48
    const cyEff = marginTop + (h - marginTop - marginBottom) / 2
    const rx = Math.max(140, w / 2 - marginX)
    const ry = Math.max(140, Math.min(cyEff - marginTop, (h - marginBottom) - cyEff))
    let sd = 20250809; const rnd = () => { sd = (sd * 1664525 + 1013904223) % 4294967296; return sd / 4294967296 }
    const maxC = layered.reduce((m, l) => Math.max(m, l.p.compat || 0), 1)
    // 归一化半径 rn(0..1):核心=近中心;其余=角度随机、相似度越高越近、sqrt面积均匀铺满
    const place = []
    let ci = 0
    const nCore = layered.filter((l) => l.tier === 'core').length
    layered.forEach(({ p, tier, color }) => {
      let ang, rn
      if (tier === 'core') {
        // 3 个带气泡的核心:120° 错开 + 较大半径,气泡向外展开不重叠
        ang = (ci / Math.max(1, nCore)) * Math.PI * 2 - Math.PI / 2
        rn = 0.42
        ci++
      } else {
        const sim = (p.compat || 0) / maxC
        ang = rnd() * Math.PI * 2
        rn = 0.32 + 0.66 * (0.4 * (1 - sim) + 0.6 * Math.sqrt(rnd()))
      }
      place.push({ p, tier, color, ang, rn, phase: rnd() * 6.28 })
    })

    // 背景微星
    const svg = svgRef.current
    if (svg) {
      svg.setAttribute('viewBox', `0 0 ${w} ${h}`)
      ;[...svg.querySelectorAll('.oc-star')].forEach((e) => e.remove())
      let sd = 20250809; const rnd = () => { sd = (sd * 1664525 + 1013904223) % 4294967296; return sd / 4294967296 }
      for (let i = 0; i < 70; i++) {
        const s = document.createElementNS('http://www.w3.org/2000/svg', 'circle')
        s.setAttribute('class', 'oc-star'); s.setAttribute('cx', rnd() * w); s.setAttribute('cy', rnd() * h)
        s.setAttribute('r', 0.4 + rnd() * 1.0); s.setAttribute('opacity', 0.06 + rnd() * 0.24); svg.appendChild(s)
      }
    }
    if (meRef.current) meRef.current.style.transform = `translate(${cx}px,${cyEff}px) translate(-50%,-50%)`

    let start = null
    const frame = (t) => {
      if (start == null) start = t
      const el = (t - start) / 1000
      const rot = el * 0.018   // 整体极缓公转
      place.forEach(({ p, tier, ang, rn, phase }) => {
        const a = ang + rot * (tier === 'dust' ? 0.6 : 1)
        const fx = Math.sin(el * 0.5 + phase) * (tier === 'dust' ? 3 : 6)   // 轻微漂浮
        const fy = Math.cos(el * 0.42 + phase) * (tier === 'dust' ? 3 : 6)
        const x = cx + Math.cos(a) * rn * rx + fx, y = cyEff + Math.sin(a) * rn * ry + fy
        const node = nodeRefs.current[p.username]
        if (node) node.style.transform = `translate(${x}px,${y}px) translate(-50%,-50%)`
        const ln = lineRefs.current[p.username]
        if (ln) {
          ln.setAttribute('x1', cx); ln.setAttribute('y1', cyEff); ln.setAttribute('x2', x); ln.setAttribute('y2', y)
        }
      })
      rafRef.current = requestAnimationFrame(frame)
    }
    rafRef.current = requestAnimationFrame(frame)
    return () => cancelAnimationFrame(rafRef.current)
  }, [layered, dim])

  const avatar = (u, disp, sz) => imgs[u]
    ? <img className="oc-img" src={imgs[u]} alt="" style={{ width: sz, height: sz, borderRadius: '50%' }} />
    : <span className="oc-letter" style={{ background: `linear-gradient(145deg, hsl(${hue(u)} 52% 58%), hsl(${hue(u)} 56% 40%))`, width: sz, height: sz, borderRadius: '50%', fontSize: Math.round(sz * 0.44) }}>{initial(disp)}</span>

  return (
    <div className="oc-host" ref={hostRef}>
      <div className="oc-well" />
      <svg className="oc-svg" ref={svgRef}>
        {/* 只连命定星一条粉线,其余好友纯漂浮(不结蛛网) */}
        {layered.filter((l) => l.p.username === loveKey).map(({ p }) => (
          <line key={p.username} ref={(el) => { lineRefs.current[p.username] = el }}
            className="oc-line love" stroke="#f9a8d4" style={{ strokeWidth: 1.4, strokeOpacity: 0.6 }} />
        ))}
      </svg>

      {/* 搜索:飞到/高亮某颗星 */}
      <div className="oc-search glass">
        <svg viewBox="0 0 24 24" width="15" height="15"><circle cx="11" cy="11" r="6.5" fill="none" stroke="currentColor" strokeWidth="1.7" /><path d="m16 16 4 4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" /></svg>
        <input placeholder={`搜好友 · 共 ${people.length} 位同频者`} value={q} onChange={(e) => setQ(e.target.value)} />
        {q && <button className="oc-search-x" onClick={() => setQ('')}>×</button>}
      </div>

      <div className="oc-node oc-me" ref={meRef}>
        <div className="oc-av oc-av-me">{avatar(me, '你', 40)}</div>
        <div className="oc-me-tag">你</div>
      </div>

      {(() => {
        const nCore = layered.filter((l) => l.tier === 'core').length
        let coreSeen = 0
        return layered.map(({ p, tier, color }) => {
        const c = p.username === loveKey ? '#f9a8d4' : color
        const hit = matches(p)
        const dim2 = ql && !hit
        // 核心气泡朝向:左半屏朝左展开,右半屏朝右(避免向中心挤压)
        let openLeft = false
        if (tier === 'core') { const ang = (coreSeen / Math.max(1, nCore)) * Math.PI * 2 - Math.PI / 2; openLeft = Math.cos(ang) < -0.12; coreSeen++ }
        if (tier === 'dust') {
          const sz = 3 + Math.round((p.compat || 0) / 100 * 4)
          return (
            <button key={p.username} className={'oc-node oc-dust' + (hit ? ' oc-hit' : '') + (dim2 ? ' oc-dim' : '')}
              ref={(el) => { nodeRefs.current[p.username] = el }} onClick={() => onSelect(p)} title={`${p.display} · ${p.compat}%`}>
              <span className="oc-dot" style={{ width: sz, height: sz, borderRadius: '50%', background: c, boxShadow: `0 0 ${sz * 2.4}px ${c}, 0 0 ${sz}px #fff8` }} />
            </button>
          )
        }
        if (tier === 'mid') {
          const sz = 26
          return (
            <button key={p.username} className={'oc-node oc-mid' + (hit ? ' oc-hit' : '') + (dim2 ? ' oc-dim' : '')}
              ref={(el) => { nodeRefs.current[p.username] = el }} onClick={() => onSelect(p)}>
              <div className="oc-ringwrap" style={{ borderRadius: '50%', boxShadow: `0 0 10px ${c}2a` }}>
                <div className="oc-av" style={{ width: sz, height: sz, borderRadius: '50%' }}>{avatar(p.username, p.display, sz)}</div>
              </div>
              <div className="oc-mininame">{p.display}</div>
            </button>
          )
        }
        // core:头像 + 拖尾精致介绍气泡
        const sz = 38
        const sub = subOf(p)
        return (
          <button key={p.username} className={'oc-node oc-core' + (openLeft ? ' oc-core-left' : '') + (p.username === loveKey ? ' oc-love' : '') + (hit ? ' oc-hit' : '') + (dim2 ? ' oc-dim' : '')}
            ref={(el) => { nodeRefs.current[p.username] = el }} onClick={() => onSelect(p)}>
            <div className="oc-ringwrap oc-ringwrap-lg" style={{ borderRadius: '50%', boxShadow: `0 0 16px ${c}33` }}>
              <div className="oc-av" style={{ width: sz, height: sz, borderRadius: '50%' }}>{avatar(p.username, p.display, sz)}</div>
            </div>
            <div className="oc-card">
              <div className="oc-card-top"><span className="oc-card-name">{p.display}</span><span className="oc-card-compat" style={{ color: c }}>{p.compat}%</span></div>
              {sub && <div className="oc-card-sub">{sub}</div>}
            </div>
            {p.compat === top && <span className="oc-love-tag">命定星</span>}
          </button>
        )
      })
      })()}
    </div>
  )
}
