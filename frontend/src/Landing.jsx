import React, { useEffect, useRef, useState } from 'react'
import { Form } from './Auth'
import { Logo } from './icons'

/* ---- 大脑星系 Canvas 背景:发光脑核 + 星环公转 + 金线随机"接上" ---- */
function StarField() {
  const ref = useRef()
  useEffect(() => {
    const cv = ref.current
    if (!cv) return
    const ctx = cv.getContext('2d')
    let raf, w, h, dpr, cx, cy, rMax
    const reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const COLORS = [[139, 140, 255], [139, 147, 248], [125, 211, 252], [251, 191, 36]]
    let nodes = []
    let dust = []
    let links = []          // 金线: {a, b, t0}
    let nextLink = 2.2
    let seed = 20260809
    const rnd = () => { seed = (seed * 1664525 + 1013904223) % 4294967296; return seed / 4294967296 }
    function build() {
      dpr = Math.min(window.devicePixelRatio || 1, 2)
      w = cv.clientWidth; h = cv.clientHeight
      cv.width = w * dpr; cv.height = h * dpr
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      const mobile = w < 640
      cx = mobile ? w * 0.5 : w * 0.58
      cy = h * 0.42
      rMax = Math.min(w, h) * (mobile ? 0.52 : 0.5)
      const N = mobile ? 34 : 62
      nodes = []
      for (let i = 0; i < N; i++) {
        // 星环分布:靠核密、靠外疏,略压扁成星系盘
        const ring = Math.pow(0.14 + rnd() * 0.86, 0.8)
        const r = rMax * ring
        const a0 = rnd() * Math.PI * 2
        const c = COLORS[(rnd() * (COLORS.length - (rnd() < 0.2 ? 1 : 2))) | 0] || COLORS[0]
        nodes.push({
          r, a0, c, squash: 0.62 + rnd() * 0.2,
          sz: 1.0 + rnd() * (ring < 0.4 ? 3.2 : 2.0),
          sp: (0.9 - ring * 0.5) * (rnd() < 0.42 ? -1 : 1),   // 内圈转得快
          tw: rnd() * Math.PI * 2,
        })
      }
      dust = []
      for (let i = 0; i < (mobile ? 46 : 96); i++) dust.push({ x: rnd() * w, y: rnd() * h, r: 0.3 + rnd() * 1.1, o: 0.05 + rnd() * 0.3 })
      links = []; nextLink = 2.2
    }
    const posOf = (n, el) => {
      const a = n.a0 + (reduce ? 0 : el * 0.05 * n.sp)
      return { x: cx + Math.cos(a) * n.r, y: cy + Math.sin(a) * n.r * n.squash }
    }
    let t0 = null
    function frame(t) {
      if (t0 == null) t0 = t
      const el = (t - t0) / 1000
      ctx.clearRect(0, 0, w, h)
      // 尘埃
      for (const d of dust) { ctx.beginPath(); ctx.arc(d.x, d.y, d.r, 0, 6.283); ctx.fillStyle = `rgba(200,214,240,${d.o})`; ctx.fill() }
      // 发光脑核(呼吸)
      const pulse = reduce ? 0.75 : 0.62 + 0.18 * Math.sin(el * 0.9)
      const coreR = rMax * 0.34
      let g = ctx.createRadialGradient(cx, cy, 0, cx, cy, coreR)
      g.addColorStop(0, `rgba(140,236,250,${0.30 * pulse})`)
      g.addColorStop(0.35, `rgba(110,196,247,${0.14 * pulse})`)
      g.addColorStop(0.7, `rgba(99,102,241,${0.06 * pulse})`)
      g.addColorStop(1, 'rgba(99,102,241,0)')
      ctx.beginPath(); ctx.arc(cx, cy, coreR, 0, 6.283); ctx.fillStyle = g; ctx.fill()
      g = ctx.createRadialGradient(cx, cy, 0, cx, cy, coreR * 0.16)
      g.addColorStop(0, `rgba(240,252,255,${0.9 * pulse})`)
      g.addColorStop(1, 'rgba(140,236,250,0)')
      ctx.beginPath(); ctx.arc(cx, cy, coreR * 0.16, 0, 6.283); ctx.fillStyle = g; ctx.fill()
      // 节点位置
      const pos = nodes.map((n) => ({ ...posOf(n, el), n }))
      // 邻近连线(靠核更亮)
      for (let i = 0; i < pos.length; i++) {
        for (let k = i + 1; k < pos.length; k++) {
          const dx = pos[i].x - pos[k].x, dy = pos[i].y - pos[k].y
          const dist = Math.hypot(dx, dy)
          if (dist < 138) {
            const near = 1 - Math.min(1, Math.hypot(pos[i].x - cx, pos[i].y - cy) / rMax)
            const o = (1 - dist / 138) * (0.13 + near * 0.14)
            const c = pos[i].n.c
            ctx.beginPath(); ctx.moveTo(pos[i].x, pos[i].y); ctx.lineTo(pos[k].x, pos[k].y)
            ctx.strokeStyle = `rgba(${c[0]},${c[1]},${c[2]},${o})`; ctx.lineWidth = 0.7; ctx.stroke()
          }
        }
      }
      // 金线:每隔几秒,两颗远星被"接上"(画 1s → 停 1.4s → 褪 0.8s)
      if (!reduce && el > nextLink && links.length < 2) {
        let a = (rnd() * nodes.length) | 0, b = (rnd() * nodes.length) | 0, tries = 0
        while (tries++ < 24) {
          b = (rnd() * nodes.length) | 0
          const pa = posOf(nodes[a], el), pb = posOf(nodes[b], el)
          if (Math.hypot(pa.x - pb.x, pa.y - pb.y) > rMax * 0.75) break
        }
        links.push({ a, b, t0: el })
        nextLink = el + 3.6 + rnd() * 2.4
      }
      for (let i = links.length - 1; i >= 0; i--) {
        const L = links[i]
        const age = el - L.t0
        if (age > 3.2) { links.splice(i, 1); continue }
        const pa = posOf(nodes[L.a], el), pb = posOf(nodes[L.b], el)
        const prog = Math.min(1, age / 1.0)
        const fade = age < 2.4 ? 1 : 1 - (age - 2.4) / 0.8
        const mx = (pa.x + pb.x) / 2, my = (pa.y + pb.y) / 2 - 46
        // 沿二次贝塞尔取点画到 prog 处
        ctx.beginPath(); ctx.moveTo(pa.x, pa.y)
        const STEPS = 26
        let ex = pa.x, ey = pa.y
        for (let s = 1; s <= STEPS * prog; s++) {
          const u = s / STEPS
          ex = (1 - u) * (1 - u) * pa.x + 2 * (1 - u) * u * mx + u * u * pb.x
          ey = (1 - u) * (1 - u) * pa.y + 2 * (1 - u) * u * my + u * u * pb.y
          ctx.lineTo(ex, ey)
        }
        ctx.strokeStyle = `rgba(251,191,36,${0.65 * fade})`
        ctx.lineWidth = 1.3
        ctx.shadowColor = 'rgba(251,191,36,0.8)'; ctx.shadowBlur = 7
        ctx.stroke()
        ctx.shadowBlur = 0
        // 线头亮点
        ctx.beginPath(); ctx.arc(ex, ey, 2.2, 0, 6.283)
        ctx.fillStyle = `rgba(255,225,140,${0.9 * fade})`; ctx.fill()
        // 两端点亮
        for (const p of [pa, pb]) {
          ctx.beginPath(); ctx.arc(p.x, p.y, 3.2, 0, 6.283)
          ctx.fillStyle = `rgba(251,191,36,${0.55 * fade})`; ctx.fill()
        }
      }
      // 节点
      for (const p of pos) {
        const n = p.n
        const tw = reduce ? 0.9 : 0.55 + 0.45 * Math.sin(el * 1.6 + n.tw)
        const [r, gg, b] = n.c
        const glow = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, n.sz * 6)
        glow.addColorStop(0, `rgba(${r},${gg},${b},${0.5 * tw})`)
        glow.addColorStop(1, `rgba(${r},${gg},${b},0)`)
        ctx.beginPath(); ctx.arc(p.x, p.y, n.sz * 6, 0, 6.283); ctx.fillStyle = glow; ctx.fill()
        ctx.beginPath(); ctx.arc(p.x, p.y, n.sz, 0, 6.283); ctx.fillStyle = `rgba(${r},${gg},${b},${0.85 * tw})`; ctx.fill()
      }
      raf = requestAnimationFrame(frame)
    }
    build()
    raf = requestAnimationFrame(frame)
    const onR = () => { t0 = null; build() }
    window.addEventListener('resize', onR)
    return () => { cancelAnimationFrame(raf); window.removeEventListener('resize', onR) }
  }, [])
  return <canvas className="lp-stars" ref={ref} aria-hidden="true" />
}

/* ---- 滚动淡入 ---- */
function useReveal() {
  useEffect(() => {
    const els = document.querySelectorAll('.lp-reveal')
    if (!('IntersectionObserver' in window)) { els.forEach((e) => e.classList.add('in')); return }
    // 01-BUG-07:滚动发生在 .lp 固定容器内(非 window),IO root 必须指向它,否则页顶所有元素一开就判"in"、淡入失效
    const scroller = document.querySelector('.lp') || null
    const io = new IntersectionObserver((ents) => {
      ents.forEach((e) => { if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target) } })
    }, { root: scroller, threshold: 0.16, rootMargin: '0px 0px -8% 0px' })
    els.forEach((e) => io.observe(e))
    return () => io.disconnect()
  }, [])
}

/* ---- 图标(承接 icons.jsx 双色调风格,24 网格)---- */
const St = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.7, strokeLinecap: 'round', strokeLinejoin: 'round' }
const fo = 0.2
const Ico = {
  ingest: () => (<svg viewBox="0 0 24 24"><path d="M4.5 13.5h4L9.5 15h5l1-1.5h4v4.5a2 2 0 0 1-2 2h-11a2 2 0 0 1-2-2z" fill="currentColor" opacity={fo} /><path d="M12 14.5V4M8.5 7.5 12 4l3.5 3.5" {...St} /><path d="M4.5 14v4a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2v-4" {...St} /></svg>),
  cite: () => (<svg viewBox="0 0 24 24"><path d="M4 6a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2H9l-4 3.5V14a2 2 0 0 1-1-2z" fill="currentColor" opacity={fo} /><path d="M4 6a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2H9l-4 3.5V14a2 2 0 0 1-1-2z" {...St} /><path d="M7.5 7.8h6M7.5 10.6h4" {...St} strokeWidth="1.4" /></svg>),
  remind: () => (<svg viewBox="0 0 24 24"><path d="M6.5 16.5c-.6 0-1-.7-.6-1.2C6.8 14 7 12.8 7 11a5 5 0 0 1 10 0c0 1.8.2 3 1.1 4.3.4.5 0 1.2-.6 1.2z" fill="currentColor" opacity={fo} /><path d="M6.5 16.5c-.6 0-1-.7-.6-1.2C6.8 14 7 12.8 7 11a5 5 0 0 1 10 0c0 1.8.2 3 1.1 4.3.4.5 0 1.2-.6 1.2z" {...St} /><path d="M10.2 19a2 2 0 0 0 3.6 0" {...St} /><circle cx="17.5" cy="6.5" r="2.3" fill="currentColor" opacity={fo} /><circle cx="17.5" cy="6.5" r="2.3" {...St} strokeWidth="1.4" /><path d="M17.5 5.4v1.3l.9.5" {...St} strokeWidth="1.3" /></svg>),
  media: () => (<svg viewBox="0 0 24 24"><rect x="3.5" y="5" width="12" height="10" rx="2" fill="currentColor" opacity={fo} /><rect x="3.5" y="5" width="12" height="10" rx="2" {...St} /><path d="M8 8.2l3 1.8-3 1.8z" fill="currentColor" /><path d="M18 8.5h3M18 12h3M18 15.5h3M3.5 19h13" {...St} strokeWidth="1.5" /></svg>),
  shield: () => (<svg viewBox="0 0 24 24"><path d="M12 3.2 19 6v5.5c0 4.4-3 7.4-7 8.8-4-1.4-7-4.4-7-8.8V6z" fill="currentColor" opacity={fo} /><path d="M12 3.2 19 6v5.5c0 4.4-3 7.4-7 8.8-4-1.4-7-4.4-7-8.8V6z" {...St} /><path d="m8.8 11.8 2.2 2.2 4-4.4" {...St} strokeWidth="1.6" /></svg>),
  film: () => (<svg viewBox="0 0 24 24"><rect x="3.5" y="4.5" width="17" height="15" rx="2.5" fill="currentColor" opacity={fo} /><rect x="3.5" y="4.5" width="17" height="15" rx="2.5" {...St} /><path d="M10.2 9.4l4.4 2.6-4.4 2.6z" fill="currentColor" /><path d="M3.5 8h17M3.5 16h17" {...St} strokeWidth="1.2" opacity="0.55" /></svg>),
  loop: () => (<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="7.2" fill="currentColor" opacity={fo} /><path d="M18.5 9A7.2 7.2 0 1 0 19 13" {...St} /><path d="M19 6v3.2h-3.2" {...St} /></svg>),
  grow: () => (<svg viewBox="0 0 24 24"><path d="M4 18v2h16" {...St} opacity="0.5" /><path d="M5 16l4-4 3 3 6.5-7" {...St} /><path d="M15 8h3.5V11.5" {...St} /><circle cx="9" cy="12" r="1.4" fill="currentColor" /><circle cx="12" cy="15" r="1.4" fill="currentColor" /></svg>),
  compound: () => (<svg viewBox="0 0 24 24"><path d="M11.6 4.6C16.6 4.6 19.4 8.6 18.6 12.4 17.7 16 14.2 18 11 17 8.2 16.2 6.8 13.4 7.5 11 8.1 8.9 10.1 7.8 12 8.5 13.5 9 14.2 10.6 13.7 12" {...St} strokeWidth="1.5" /><circle cx="11.6" cy="4.6" r="1" fill="currentColor" /><circle cx="18.6" cy="12.4" r="1.3" fill="currentColor" /><circle cx="11" cy="17" r="1.5" fill="currentColor" /><circle cx="13" cy="12" r="2" fill="currentColor" opacity={fo} /></svg>),
  desktop: () => (<svg viewBox="0 0 24 24"><rect x="3" y="4.5" width="18" height="12" rx="2" fill="currentColor" opacity={fo} /><rect x="3" y="4.5" width="18" height="12" rx="2" {...St} /><path d="M9.5 20h5M12 16.5V20" {...St} /></svg>),
  phone: () => (<svg viewBox="0 0 24 24"><rect x="7" y="3" width="10" height="18" rx="2.5" fill="currentColor" opacity={fo} /><rect x="7" y="3" width="10" height="18" rx="2.5" {...St} /><path d="M10.5 5.5h3" {...St} strokeWidth="1.4" /><circle cx="12" cy="17.8" r="1" fill="currentColor" /></svg>),
  spark: () => (<svg viewBox="0 0 24 24"><path d="M12 4l1.6 4.4L18 10l-4.4 1.6L12 16l-1.6-4.4L6 10l4.4-1.6z" fill="currentColor" opacity="0.9" /></svg>),
  camera: () => (<svg viewBox="0 0 24 24"><path d="M4 8.5a2 2 0 0 1 2-2h1.6l1-1.6h5l1 1.6H18a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z" fill="currentColor" opacity={fo} /><path d="M4 8.5a2 2 0 0 1 2-2h1.6l1-1.6h5l1 1.6H18a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z" {...St} /><circle cx="12" cy="12.5" r="3" {...St} /></svg>),
  mic: () => (<svg viewBox="0 0 24 24"><rect x="9" y="3" width="6" height="11" rx="3" fill="currentColor" opacity={fo} /><rect x="9" y="3" width="6" height="11" rx="3" {...St} /><path d="M6 11a6 6 0 0 0 12 0M12 17v3.5M9 20.5h6" {...St} /></svg>),
  pen: () => (<svg viewBox="0 0 24 24"><path d="M15.5 5.5 18.5 8.5 9 18l-4 1 1-4z" fill="currentColor" opacity={fo} /><path d="M15.5 5.5 18.5 8.5 9 18l-4 1 1-4zM14 7l3 3" {...St} /></svg>),
  cloud: () => (<svg viewBox="0 0 24 24"><path d="M7 18a4 4 0 0 1-.5-7.97A5 5 0 0 1 16 9.2 3.5 3.5 0 0 1 17.5 18z" fill="currentColor" opacity={fo} /><path d="M7 18a4 4 0 0 1-.5-7.97A5 5 0 0 1 16 9.2 3.5 3.5 0 0 1 17.5 18z" {...St} /></svg>),
  doc: () => (<svg viewBox="0 0 24 24"><path d="M6 3.5h7l5 5V20a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4.5a1 1 0 0 1 1-1z" fill="currentColor" opacity={fo} /><path d="M6 3.5h7l5 5V20a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4.5a1 1 0 0 1 1-1zM13 3.5V8.5h5" {...St} /></svg>),
  chat: () => (<svg viewBox="0 0 24 24"><path d="M4 6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H9l-4 3.5V16a2 2 0 0 1-1-2z" fill="currentColor" opacity={fo} /><path d="M4 6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H9l-4 3.5V16a2 2 0 0 1-1-2z" {...St} /></svg>),
  down: () => (<svg viewBox="0 0 24 24" {...St}><path d="M12 4v11M7 10.5 12 15.5l5-5M5 19.5h14" /></svg>),
  sndOff: () => (<svg viewBox="0 0 24 24"><path d="M4 9.5v5h3.5L12 18.5v-13L7.5 9.5z" fill="currentColor" opacity={fo} /><path d="M4 9.5v5h3.5L12 18.5v-13L7.5 9.5z" {...St} /><path d="M16 9.8l4.4 4.4M20.4 9.8 16 14.2" {...St} /></svg>),
  sndOn: () => (<svg viewBox="0 0 24 24"><path d="M4 9.5v5h3.5L12 18.5v-13L7.5 9.5z" fill="currentColor" opacity={fo} /><path d="M4 9.5v5h3.5L12 18.5v-13L7.5 9.5z" {...St} /><path d="M15.5 9.2a4 4 0 0 1 0 5.6M18.2 6.8a7.5 7.5 0 0 1 0 10.4" {...St} /></svg>),
}

/* ---- 真实产品截图:窗口框 + 辉光 ---- */
function Shot({ img, label, alt }) {
  const B = import.meta.env.BASE_URL
  return (
    <div className="lp-shot">
      <div className="lp-shot-bar">
        <span /><span /><span />
        <em>{label}</em>
        <i className="lp-shot-live"><b />真实界面</i>
      </div>
      <img src={B + 'lp/' + img} alt={alt} loading="lazy" />
    </div>
  )
}

/* 痛点:一天的真实生活流——好东西亮起,然后死在收藏夹 */
const DAY_ITEMS = [
  { t: '09:30', c: 'wechat', ico: 'chat', title: 'AI 行业深度报告.pdf', sub: '微信群 · 朋友转发「值得一看」', fate: '再没打开' },
  { t: '11:00', c: 'mic', ico: 'mic', title: '周会录音 47:12', sub: '说好回头整理成纪要', fate: '再没听过' },
  { t: '13:20', c: 'article', ico: 'doc', title: '长文《复利,时间的杠杆》', sub: '公众号 · 读到一半,点了收藏', fate: '沉入收藏夹' },
  { t: '15:40', c: 'shot', ico: 'camera', title: '灵感截图', sub: '开会时灵光一闪,随手一截', fate: '混进 8000 张照片' },
  { t: '19:00', c: 'video', ico: 'media', title: '课程视频 · 看到 32:15', sub: '微信收藏 · 「明天接着看」', fate: '进度再没动过' },
  { t: '23:00', c: 'note', ico: 'pen', title: '一个不错的念头', sub: '睡前记在备忘录最底下', fate: '第二天就忘了' },
]
function DayStream() {
  return (
    <div className="lp-day-wrap">
      <div className="lp-day">
        {DAY_ITEMS.map((d, i) => {
          const I = Ico[d.ico]
          return (
            <div key={d.t} className={'lp-dcard lp-dc-' + d.c} style={{ '--dl': i * 1.9 + 's', '--rot': (i % 3 - 1) * 1.2 + 'deg' }}>
              <span className="lp-dico"><I /></span>
              <span className="lp-dbody">
                <b>{d.title}</b>
                <p>{d.sub}</p>
              </span>
              <time>{d.t}</time>
              <em className="lp-dfate">{d.fate}</em>
            </div>
          )
        })}
      </div>
      <p className="lp-day-sum">这一天,<b>6 条</b>有价值的输入 —— <b className="lp-day-zero">0 条</b>,被再次用上。</p>
    </div>
  )
}

const ZIGS = [
  {
    n: '01', k: '每天替你发现', h: '你什么都没做,它先来找你。',
    d: '它通读你的全部资料,每天主动找出几件值得做的事:哪个目标立了三次该落地了,哪两份材料能一箭双雕,哪段录音放了一周正好复盘。每一条,都替你想好了下一步——你只需要说"好"。',
    img: 'lp_today.jpg', label: '今日 · 第二大脑替你发现了 4 件事', alt: '第二大脑每日主动发现',
  },
  {
    n: '02', k: '带出处的问答', h: '随口一问,答案带着页码来。',
    d: '每一句都标着来自哪本书、第几页、相似度多少——一点,就跳回你当初读到的原文,它从不凭空编。答完还能顺手生成 PPT、Word、Excel,从「问到」到「做出来」,一步。',
    img: 'lp_ask.jpg', label: '问答 · 每句都有来源', alt: '带出处的问答与一键生成',
  },
  {
    n: '03', k: '万物入库', h: '录音、视频、电子书……丢进去,就归好了。',
    d: 'PDF、PPT、表格、mp3 录音、mp4 视频、epub 电子书、随手截图——这位用户的 93 份文件,它自动按学科分好类,每一份都变成能问、能连、能用的知识。',
    img: 'lp_library.jpg', label: '文库 · 93 份文件自动归类', alt: '万物入库自动分类',
  },
  {
    n: '04', k: '知识星系', h: '93 份文件,自己连成了 421 条线。',
    d: '不同年份、不同类型的记忆被自动接上——去年的 PDF、上周的截图、三天前的念头,原来在说同一件事。这是你一个人翻收藏夹,永远做不到的。',
    img: 'lp_explore.jpg', label: '探索 · 93 文档 · 421 连线', alt: '知识星系图谱',
  },
  {
    n: '05', k: '你的画像', h: '它比任何人都清楚,你懂什么、缺什么。',
    d: '从你读过的每本书、记下的每个念头,长出一张你的知识画像:每个领域多少分、强在哪、下一步该补什么。像一面镜子,照见你自己的大脑。',
    img: 'lp_persona.jpg', label: '画像 · 你的知识地图', alt: '个人知识画像',
  },
]
const OUTCOMES = [
  { k: 'loop', t: '不再遗忘', d: '读过、记过、经历过的,都还在,并且随叫随到。你的记忆有了一层永不褪色的底片。' },
  { k: 'grow', t: '从「死收藏」变「活资产」', d: '收藏夹不再是坟场。躺着的每一篇都被连成网,在你需要时自己浮出来帮你。' },
  { k: 'compound', t: '每天几分钟,复利成长', d: '今天喂它一点,明天它多懂你一点。知识像利息一样滚起来,越用越聪明。' },
]

/* ===== 核心场景 ① 手机喂文件 → 电脑(家)里的大脑越长越丰富 ===== */
const FEED_FILES = [
  { i: 'doc', l: 'PDF' }, { i: 'camera', l: '照片' }, { i: 'mic', l: '录音' },
  { i: 'chat', l: '微信' }, { i: 'pen', l: '笔记' }, { i: 'media', l: '视频' },
]
function SceneFlow() {
  return (
    <div className="lp-home lp-reveal">
      <div className="lp-home-stage">
        {/* 手机(在外) */}
        <div className="lp-home-side">
          <div className="lp-phone">
            <div className="lp-phone-notch" />
            <div className="lp-phone-scr">
              {FEED_FILES.map((f, i) => {
                const I = Ico[f.i]
                return <span key={i} className="lp-phone-card" style={{ animationDelay: (i * 1.3).toFixed(2) + 's' }}><I />{f.l}</span>
              })}
            </div>
          </div>
          <span className="lp-home-tag"><Ico.phone />手机随手喂</span>
        </div>

        {/* 飞行文件 + 连线 */}
        <div className="lp-home-mid">
          <svg className="lp-home-path" viewBox="0 0 300 120" preserveAspectRatio="none" aria-hidden="true">
            <path d="M4 60 Q150 8 296 60" />
          </svg>
          <span className="lp-home-cloud"><Ico.cloud /><em>加密中转 · 不留存</em></span>
          {FEED_FILES.map((f, i) => {
            const I = Ico[f.i]
            return <span key={i} className="lp-home-fly" style={{ animationDelay: (i * 1.3).toFixed(2) + 's' }}><I /></span>
          })}
        </div>

        {/* 电脑(家)+ 逐渐丰富的大脑 */}
        <div className="lp-home-side">
          <div className="lp-pc">
            <div className="lp-pc-scr">
              <svg className="lp-braingrow" viewBox="0 0 120 90" aria-hidden="true">
                <g className="lp-bg-edges" stroke="url(#lgedge)" strokeWidth="1" strokeLinecap="round" fill="none">
                  <line x1="60" y1="45" x2="34" y2="26" style={{ animationDelay: '.3s' }} />
                  <line x1="60" y1="45" x2="88" y2="28" style={{ animationDelay: '1.6s' }} />
                  <line x1="60" y1="45" x2="30" y2="62" style={{ animationDelay: '2.9s' }} />
                  <line x1="60" y1="45" x2="90" y2="64" style={{ animationDelay: '4.2s' }} />
                  <line x1="34" y1="26" x2="30" y2="62" style={{ animationDelay: '5.5s' }} />
                  <line x1="88" y1="28" x2="90" y2="64" style={{ animationDelay: '6.8s' }} />
                </g>
                <circle className="lp-bg-core" cx="60" cy="45" r="6" fill="url(#lgcore)" />
                <circle className="lp-bg-node" cx="34" cy="26" r="3.2" fill="#8b8cff" style={{ animationDelay: '.3s' }} />
                <circle className="lp-bg-node" cx="88" cy="28" r="3.4" fill="#7dd3fc" style={{ animationDelay: '1.6s' }} />
                <circle className="lp-bg-node" cx="30" cy="62" r="3" fill="#818cf8" style={{ animationDelay: '2.9s' }} />
                <circle className="lp-bg-node" cx="90" cy="64" r="3.3" fill="#a5b4fc" style={{ animationDelay: '4.2s' }} />
                <circle className="lp-bg-node" cx="18" cy="44" r="2.6" fill="#fbbf24" style={{ animationDelay: '5.5s' }} />
                <circle className="lp-bg-node" cx="104" cy="46" r="2.8" fill="#8b8cff" style={{ animationDelay: '6.8s' }} />
                <defs>
                  <radialGradient id="lgcore" cx="40%" cy="34%" r="72%"><stop offset="0" stopColor="#c9f5fe" /><stop offset="0.45" stopColor="#8b8cff" /><stop offset="1" stopColor="#6366f1" /></radialGradient>
                  <linearGradient id="lgedge" x1="0" y1="0" x2="120" y2="90" gradientUnits="userSpaceOnUse"><stop offset="0" stopColor="#8b8cff" /><stop offset="1" stopColor="#818cf8" /></linearGradient>
                </defs>
              </svg>
            </div>
            <div className="lp-pc-foot" />
          </div>
          <span className="lp-home-tag"><i className="lp-live" />你家的电脑 · 常亮</span>
        </div>
      </div>
      <p className="lp-home-cap">电脑装在家里,手机随手喂——数据只落在你自己家里,<b className="lp-warm">你的第二大脑,一天天长大</b>。</p>
    </div>
  )
}

/* ===== 核心场景:跨时间·跨文件的细微链接(时间轴 + 扫描 + 金线) ===== */
const LK_CARDS = [
  { x: 60, y: 60, w: 190, tick: 150, dot: '#a78bfa', title: '周会录音.mp3', hl: 1 },
  { x: 330, y: 140, w: 190, tick: 430, dot: '#f87171', title: '行业报告.pdf · 第7页', hl: 2 },
  { x: 590, y: 48, w: 180, tick: 680, dot: '#38bdf8', title: '一张随手截图', hl: 1 },
  { x: 790, y: 140, w: 180, tick: 880, dot: '#fbbf24', title: '备忘录 · 一条笔记', hl: 1 },
]
const LK_TICKS = [
  { x: 150, l: '2023 · 春' }, { x: 430, l: '2024 · 冬' }, { x: 680, l: '上个月' }, { x: 880, l: '昨天' },
]
function SceneLink() {
  return (
    <div className="lp-link lp-reveal">
      <div className="lp-link-frame">
        <svg className="lp-link-svg" viewBox="0 0 1000 380" aria-hidden="true">
          <defs>
            <linearGradient id="lkscan" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0" stopColor="rgba(139, 140, 255,0)" />
              <stop offset="0.5" stopColor="rgba(139, 140, 255,0.16)" />
              <stop offset="1" stopColor="rgba(139, 140, 255,0)" />
            </linearGradient>
            <linearGradient id="lkgold" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0" stopColor="#fbbf24" /><stop offset="1" stopColor="#f59e0b" />
            </linearGradient>
          </defs>
          {/* 时间轴 */}
          <line className="lp-lk-axis" x1="40" y1="332" x2="960" y2="332" />
          {LK_TICKS.map((t) => (
            <g key={t.x}>
              <circle cx={t.x} cy="332" r="3" fill="rgba(200,214,240,0.5)" />
              <text className="lp-lk-tick" x={t.x} y="360" textAnchor="middle">{t.l}</text>
            </g>
          ))}
          {/* 文件卡 + 引线 */}
          {LK_CARDS.map((c, ci) => (
            <g key={ci}>
              <line className="lp-lk-stem" x1={c.tick} y1={c.y + 86} x2={c.tick} y2="330" />
              <rect className="lp-lk-card" x={c.x} y={c.y} width={c.w} height="86" rx="10" />
              <circle cx={c.x + 18} cy={c.y + 20} r="3.5" fill={c.dot} />
              <text className="lp-lk-title" x={c.x + 28} y={c.y + 24}>{c.title}</text>
              {[0, 1, 2].map((li) => (
                li === c.hl
                  ? <rect key={li} className={'lp-lk-hl lp-lk-hl-' + ci} x={c.x + 14} y={c.y + 36 + li * 16} width={c.w - 50} height="5" rx="2.5" fill="url(#lkgold)" />
                  : <rect key={li} x={c.x + 14} y={c.y + 36 + li * 16} width={(c.w - 40) * (li === 2 ? 0.6 : 0.92)} height="5" rx="2.5" fill="rgba(255,255,255,0.11)" />
              ))}
            </g>
          ))}
          {/* 金线:把四句连成一条线索 */}
          <path className="lp-lk-th lp-lk-th-0" d="M214,119 C 270,124 288,192 344,197" />
          <path className="lp-lk-th lp-lk-th-1" d="M470,197 C 528,190 548,112 604,107" />
          <path className="lp-lk-th lp-lk-th-2" d="M744,107 C 792,112 758,192 804,197" />
          {/* 扫描光束 */}
          <rect className="lp-lk-scan" x="-80" y="16" width="70" height="330" fill="url(#lkscan)" />
        </svg>
        <span className="lp-lk-label">同一条线索 · 横跨 2 年 · 4 种文件</span>
      </div>
      <p className="lp-link-cap">这些细微的联系,你早忘了——<b className="lp-warm">它记得,还替你接上</b>。</p>
    </div>
  )
}

/* ===== 常用场景:到了要用的那一刻,它替你把活儿干完 ===== */
function ScBuild() {
  return (
    <div className="lps-stage lps-build">
      {['《固定收益》· 第 81 页', '周会录音 · 23:14', '行业报告.pdf · 第 7 页'].map((s, i) => (
        <span key={i} className="lps-src" style={{ '--d': 0.4 + i * 0.9 + 's' }}>{s}</span>
      ))}
      <svg className="lps-arrow" viewBox="0 0 24 24"><path d="M4 12h14M13 6.5 19.5 12 13 17.5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /></svg>
      <div className="lps-doc">
        {[0, 1, 2, 3].map((i) => <i key={i} style={{ '--d': 4 + i * 0.35 + 's', width: (i === 3 ? 56 : 82 - i * 8) + '%' }} />)}
        <b className="lps-badge">PPT</b>
      </div>
    </div>
  )
}
function ScFind() {
  return (
    <div className="lps-stage lps-find">
      <div className="lps-q">那个夏普比率的公式,在哪本书来着?</div>
      <div className="lps-a">
        在这里——
        <span className="lps-page">667.epub · 第 1760 页</span>
      </div>
      <div className="lps-mini-doc"><i /><i className="lps-mini-hl" /><i style={{ width: '58%' }} /></div>
    </div>
  )
}
function ScBridge() {
  return (
    <div className="lps-stage lps-bridge">
      <div className="lps-bcard"><s>三个月前</s>一个没做完的念头</div>
      <svg className="lps-bline" viewBox="0 0 120 40" preserveAspectRatio="none"><path d="M4 20 C 40 4 80 36 116 20" fill="none" /></svg>
      <div className="lps-bcard lps-bcard-r"><s>今天</s>刚存的一篇文章</div>
      <span className="lps-blabel">其实是同一件事</span>
    </div>
  )
}
const SCENES = [
  {
    hook: '「明天就要交这份 PPT……素材我明明都存过。」',
    how: '它从你半年的积累里翻出所有相关的书页、录音、报告,拼好大纲,一键生成 PPT / Word。',
    old: '找一下午', neo: '20 分钟', anim: ScBuild,
  },
  {
    hook: '「这个公式我肯定看过,在哪本书来着?」',
    how: '随口一问,答案带着书名和页码回来。一点,直达你当初读到的那一行。',
    old: '翻半小时', neo: '3 秒', anim: ScFind,
  },
  {
    hook: '「总觉得这个新想法,以前琢磨过类似的……」',
    how: '它主动提醒你:三个月前你就想过这件事,还留了三份材料——现在,能接上了。',
    old: '灵感溜走', neo: '直接变成产出', anim: ScBridge,
  },
]

/* ---- 专辑短片:入视口静音自动播,可开声音 ---- */
function FilmCard({ src, poster, portrait }) {
  const ref = useRef(null)
  const [muted, setMuted] = useState(true)
  useEffect(() => {
    const v = ref.current
    if (!v) return
    const reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (reduce) return
    const io = new IntersectionObserver(([e]) => {
      if (e.isIntersecting) v.play().catch(() => {})
      else v.pause()
    }, { threshold: 0.35 })
    io.observe(v)
    return () => io.disconnect()
  }, [])
  const B = import.meta.env.BASE_URL
  return (
    <div className={'lp-case-frame' + (portrait ? ' lp-case-portrait' : '')}>
      <video ref={ref} src={B + src} poster={B + poster} muted={muted} loop playsInline preload="metadata" />
      <button className="lp-case-snd" aria-label={muted ? '打开声音' : '静音'}
        onClick={() => { setMuted((m) => !m); const v = ref.current; if (v && v.paused) v.play().catch(() => {}) }}>
        {muted ? <Ico.sndOff /> : <Ico.sndOn />}
      </button>
    </div>
  )
}
/* ---- 音乐专辑:CSS 黑胶封面 + 点击试听(同时只播一首) ---- */
const MUSIC = [
  { src: 'albums/song_a.mp3', t: '《最快的一单》', style: '摇滚 · 2:37', hue: '32' },
  { src: 'albums/song_hiphop.mp3', t: '《最快的一单》', style: '嘻哈 · 0:48', hue: '190' },
  { src: 'albums/song_ballad.mp3', t: '《最快的一单》', style: '抒情 · 1:50', hue: '265' },
]
let _curAudio = null
function MusicCard({ m }) {
  const ref = useRef(null)
  const [playing, setPlaying] = useState(false)
  const B = import.meta.env.BASE_URL
  const toggle = () => {
    const a = ref.current
    if (!a) return
    if (a.paused) {
      if (_curAudio && _curAudio !== a) _curAudio.pause()
      _curAudio = a
      a.play().catch(() => {})
    } else a.pause()
  }
  return (
    <div className={'lp-mus' + (playing ? ' lp-mus-on' : '')} style={{ '--mh': m.hue }} onClick={toggle}>
      <div className="lp-mus-cover">
        <div className="lp-mus-vinyl"><i /></div>
        <span className="lp-mus-play">
          {playing
            ? <svg viewBox="0 0 24 24"><path d="M8.5 6v12M15.5 6v12" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" /></svg>
            : <svg viewBox="0 0 24 24"><path d="M9 6.5l9 5.5-9 5.5z" fill="currentColor" /></svg>}
        </span>
        <span className="lp-mus-eq"><i /><i /><i /><i /><i /></span>
      </div>
      <b>{m.t}</b>
      <p>{m.style}</p>
      <audio ref={ref} src={B + m.src} preload="none"
        onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} onEnded={() => setPlaying(false)} />
    </div>
  )
}

export default function Landing({ onAuthed }) {
  useReveal()
  const [year] = useState(() => new Date().getFullYear())
  // 注册成功引导态持久化(P1-11:刷新不丢,已注册号不再误走注册撞报错)
  const _regInit = (() => { try { return JSON.parse(sessionStorage.getItem('reg_guide') || 'null') } catch { return null } })()
  const [registered, setRegistered] = useState(!!_regInit)
  const [regNick, setRegNick] = useState((_regInit && _regInit.nick) || '')
  const [regPhone, setRegPhone] = useState((_regInit && _regInit.phone) || '')
  const regPhoneMask = regPhone && regPhone.length === 11 ? regPhone.slice(0, 3) + '****' + regPhone.slice(7) : regPhone
  // 隐藏登录入口:网址带 ?login 才显示登录(普通访客只能注册)。用精确参数判定,避免 ?relogin/?xlogin 子串误命中
  const showLogin = typeof window !== 'undefined' && (new URLSearchParams(window.location.search).has('login') || window.location.hash === '#login')
  const toDownload = () => document.getElementById('lp-download')?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  return (
    <div className="lp">
      {/* 顶部导航 */}
      <header className="lp-nav">
        <div className="lp-nav-brand"><Logo /><span><b>Compound</b> · 第二大脑</span></div>
        <button className="lp-nav-dl" onClick={toDownload}><Ico.down />下载客户端</button>
      </header>

      {/* ① 首屏:左情感文案 + 右登录卡 */}
      <section className="lp-hero2">
        <div className="lp-aurora" />
        <StarField />
        <div className="lp-hero-veil" />
        <div className="lp-warmglow" />
        <div className="lp-hero2-grid">
          <div className="lp-hero2-copy">
            <div className="lp-hero-mark lp-up"><Logo /></div>
            <h1 className="lp-title lp-up" style={{ animationDelay: '.12s' }}><span className="lp-grad-warm lp-brandword">Compound</span><span className="lp-title-sub">你的第二大脑</span></h1>
            <p className="lp-sub lp-hero-one lp-up" style={{ animationDelay: '.26s' }}>微信聊天、邮件、文档随手喂,它实时帮你分析、记住、联想——养一个只属于你的大脑,数据永远不出你自己的电脑。</p>
            <div className="lp-hero-chips lp-up" style={{ animationDelay: '.4s' }}>
              <span><Ico.ingest />微信聊天实时分析</span>
              <span><Ico.cite />答案带页码</span>
              <span><Ico.remind />每天替你发现</span>
              <span><Ico.film />还会写歌做片</span>
            </div>
            <p className="lp-hero-proof lp-up" style={{ animationDelay: '.5s' }}>
              一位真实用户:<b>93</b> 份文件 · <b>421</b> 条自动连接 · 每天 <b>4</b> 个主动发现
            </p>
            {/* 漂浮的迷你产品卡:给首屏产品味和纵深 */}
            <div className="lp-hfloat lp-hf-1">
              <s className="lp-hf-tag"><i />今日 · 主动发现</s>
              <div className="lp-hf-roll">
                <b>「今年攒够 100 万」你立过三次,该动手了</b>
                <b>「减 20 斤」的计划,停在第 6 天了</b>
                <b>「读完这本书」你收藏了,一页没翻</b>
              </div>
            </div>
            <div className="lp-hfloat lp-hf-2">
              <span className="lp-hf-src"><em>来源</em>667.epub · 第 1760 页<u>72%</u></span>
            </div>
            <div className="lp-hfloat lp-hf-3">
              <span className="lp-hf-ppt"><svg viewBox="0 0 24 24"><path d="m5 12.5 4.5 4.5L19 7.5" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" /></svg>PPT 已生成</span>
            </div>
          </div>
          <div id="lp-login" className="lp-login2 glass lp-up" style={{ animationDelay: '.32s' }}>
            {registered ? (
              <div className="lp-reg-done">
                <div className="lp-reg-check"><svg viewBox="0 0 24 24"><path d="m5 12.5 4.5 4.5L19 7" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" /></svg></div>
                <h2>注册成功{regNick ? ',' + regNick : ''}!</h2>
                <p className="lp-reg-lead">第二大脑装在<b>你自己的电脑</b>里,数据从不上传。<br />下一步只有两件事:</p>
                <ol className="lp-reg-steps">
                  <li><span>1</span>下载并安装客户端(电脑常开,就是大脑的家)</li>
                  <li><span>2</span>用刚注册的手机号 <b>{regPhoneMask}</b> 在客户端里登录</li>
                </ol>
                <button className="btn btn-primary lp-reg-dl" onClick={toDownload}><Ico.down />下载客户端</button>
                <p className="lp-reg-note">手机 App 用来随手拍照、录音、记灵感,同样在设置里登录同一个手机号即可。</p>
              </div>
            ) : showLogin ? (
              <>
                <div className="lp-login2-head">
                  <Logo />
                  <div>
                    <h2>登录 Compound</h2>
                    <p>内部入口 · 直接进入体验</p>
                  </div>
                </div>
                <Form onAuthed={onAuthed} />
              </>
            ) : (
              <>
                <div className="lp-login2-head">
                  <Logo />
                  <div>
                    <h2>注册 Compound</h2>
                    <p>一个手机号就能注册 · 到客户端里开始使用</p>
                  </div>
                </div>
                <Form registerOnly onRegistered={(u) => { setRegNick(u.nickname || ''); setRegPhone(u.username || ''); setRegistered(true); try { sessionStorage.setItem('reg_guide', JSON.stringify({ nick: u.nickname || '', phone: u.username || '' })) } catch { /* noop */ } }} />
              </>
            )}
          </div>
        </div>
      </section>

      {/* ①.5 能力全景:它能吃下你的一切数据 + 三大主动引擎 + 隐私承诺 */}
      <section className="lp-sec lp-alldata">
        <div className="lp-reveal lp-sec-head">
          <p className="lp-kicker">你的一切数据,都能变成它的记忆</p>
          <h2 className="lp-h2">微信聊天 · 邮件 · 书籍 · 视频 · 语音 · 文档,<span className="lp-grad">全都吃</span></h2>
          <p className="lp-lead">导进来的每一份,它都读懂、连起来、随时待命 —— 而且<b>全程在你自己的电脑上完成,一个字都不上传</b>。</p>
        </div>
        <div className="lp-reveal lp-feed-grid">
          <div className="lp-feed-card"><b>微信聊天 · 实时</b><span>开着电脑版微信,你手机上聊的每一条,几秒内自动进大脑:谁答应了你什么、谁在等你回、报价数字,全被记住。</span></div>
          <div className="lp-feed-card"><b>邮件 · 全量</b><span>Gmail / QQ / 163 一次导入全部邮件,可搜可问,再也不用一封封翻。</span></div>
          <div className="lp-feed-card"><b>书籍 / 文档</b><span>PDF、EPUB、Word、PPT 整本吞下,答案带页码,随问随到。</span></div>
          <div className="lp-feed-card"><b>视频 / 语音</b><span>会议录音、播客、B 站视频自动转文字入库,一句话都不漏。</span></div>
        </div>
        {/* 微信聊天 → 大脑产出:实打实的对照演示 */}
        <div className="lp-reveal lp-wxdemo glass">
          <div className="lp-wxd-col chat">
            <div className="lp-wxd-t">你每天的聊天,看起来平平无奇</div>
            <div className="lp-wxd-bubble them">下周三之前把项目方案发我一下哈</div>
            <div className="lp-wxd-bubble me">好,周三前给你</div>
            <div className="lp-wxd-bubble them">我们园区下月空出 2000 平仓库,你那边有客户要租吗?</div>
            <div className="lp-wxd-bubble them">对了,上次说好的羽毛球什么时候打?</div>
          </div>
          <div className="lp-wxd-arrow" aria-hidden>
            <svg viewBox="0 0 40 24" width="40" height="24"><path d="M2 12h30m0 0-7-7m7 7-7 7" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>
            <span>第二大脑<br />实时分析</span>
          </div>
          <div className="lp-wxd-col out">
            <div className="lp-wxd-t">大脑替你挖出来的,全是真金白银</div>
            <div className="lp-wxd-card c1"><s>承诺雷达</s>你答应周三前发项目方案 —— 已进待办,到点提醒</div>
            <div className="lp-wxd-card c2"><s>供需撮合</s>他有 2000 平仓库要出租 —— 和你另一位联系人的仓储需求对上了,可牵线</div>
            <div className="lp-wxd-card c3"><s>人情账本</s>羽毛球之约搁了 12 天没回 —— 给你备好了自然的开场白</div>
            <div className="lp-wxd-card c4"><s>关系卡</s>此人近 3 月互动升温,最在意交付进度,雷区:别放鸽子</div>
          </div>
        </div>
        <p className="lp-reveal lp-wxd-punch">这些原本都躺在你的聊天记录里没人管。<b>你的微信,是一座还没开采的宝库。</b></p>

        <div className="lp-reveal lp-sec-head" style={{ marginTop: 52 }}>
          <p className="lp-kicker">不止是存 —— 它主动替你干活</p>
          <h2 className="lp-h2">三个引擎,<span className="lp-grad-warm">每天替你盯着</span></h2>
        </div>
        <div className="lp-reveal lp-feed-grid three">
          <div className="lp-feed-card engine">
            <b>人脉</b><span>每个联系人一张 AI 活档案:他是谁、聊到哪、答应过什么、雷区在哪。见面前 10 秒拿到简报。</span>
            <div className="lp-mock relcard">
              <div className="lp-mock-head"><i className="lp-mock-ava">陈</i><div><em>陈明远 · 星舟科技</em><u>市场部负责人 · 认识 2 年</u></div><s className="lp-mock-hot">升温中</s></div>
              <div className="lp-mock-row"><s>未了结</s>他在等你的合作报价单,已 3 天</div>
              <div className="lp-mock-row"><s>雷区</s>午休别打电话;决策要给他留台阶</div>
              <div className="lp-mock-foot">见面简报 · 深度分析 · 问 TA</div>
            </div>
          </div>
          <div className="lp-feed-card engine">
            <b>雷达</b><span>你答应的事、别人欠你的、谁手上有货谁在找 —— 承诺雷达、供需撮合、人情账本,主动提醒,别再靠脑子记。</span>
            <div className="lp-mock radar">
              <div className="lp-mock-ritem c1"><s>承诺</s>你答应周五前给李总活动方案<u>还剩 2 天</u></div>
              <div className="lp-mock-ritem c2"><s>撮合</s>王姐团队能接定制开发 · 正好赵总在找外包<u>可牵线</u></div>
              <div className="lp-mock-ritem c3"><s>人情</s>孙姐帮你改过简历,欠一顿饭<u>47 天</u></div>
              <div className="lp-mock-ritem c4"><s>降温</s>和老周 19 天没动静了<u>开场白已备好</u></div>
            </div>
          </div>
          <div className="lp-feed-card engine">
            <b>洞察</b><span>它发现你自己都忘了的联系:三个月前的邮件和昨天的聊天其实是同一件事,自动连起来推给你。</span>
            <div className="lp-mock insight">
              <div className="lp-mock-pair"><em>《Q3 行业研究.pdf》</em><i>⟷</i><em>与周凯的聊天</em><u>82%</u></div>
              <div className="lp-mock-why">两边说的是同一个并购标的:报告第 41 页的估值区间,正好回答了周凯上周问你的问题。</div>
              <div className="lp-mock-row"><s>建议</s>把这页发给周凯,顺势约个电话</div>
            </div>
          </div>
        </div>
        <div className="lp-reveal lp-privacy-bar">
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><rect x="4" y="10" width="16" height="10" rx="2.5" /><path d="M8 10V7.5a4 4 0 0 1 8 0V10" /></svg>
          隐私是底线:聊天解析在你自己电脑完成 · 读完即焚不留明文 · 我们连你的微信密码都接触不到 · 随时一键删除全部数据
        </div>
      </section>

      {/* ② 痛点共鸣:一天的生活流 */}
      <section className="lp-sec lp-pain">
        <div className="lp-reveal lp-pain-wrap">
          <p className="lp-kicker">你是不是也这样</p>
          <h2 className="lp-h2">收藏了,就等于<span className="lp-mute">再也不看</span>。</h2>
          <p className="lp-lead">
            微信里朋友转的报告、听了一半的课、47 分钟的会议录音、随手截下的灵感——<br />
            每天都有好东西经过你。你存下了它们,却<b>再也没有第二次见面</b>。
          </p>
          <DayStream />
          <p className="lp-pain-turn">它们本该都是你的资产。第二大脑,就是来接住它们的。</p>
        </div>
      </section>

      {/* ③ 核心能力:真实截图 + 场景文案 */}
      <section className="lp-sec lp-zigs">
        <div className="lp-reveal lp-sec-head">
          <p className="lp-kicker">真实界面 · 真实数据</p>
          <h2 className="lp-h2">别听我们讲理念——登录后,<span className="lp-grad">你得到的就是这些</span>。</h2>
          <p className="lp-lead">下面每一张都是产品的真实截图,来自一位真实用户的 93 份文件。<b>不是效果图。</b></p>
        </div>
        {ZIGS.map((z, i) => (
          <div key={z.n} className={'lp-zig lp-reveal' + (i % 2 ? ' lp-zig-rev' : '')}>
            <div className="lp-zig-txt">
              <p className="lp-zig-n">{z.n} · {z.k}</p>
              <h3>{z.h}</h3>
              <p className="lp-zig-d">{z.d}</p>
            </div>
            <Shot img={z.img} label={z.label} alt={z.alt} />
          </div>
        ))}
      </section>

      {/* ④ 杀手锏:跨时间·跨文件的细微链接(文字+动画) */}
      <section className="lp-sec lp-link-sec">
        <div className="lp-reveal lp-sec-head lp-center">
          <p className="lp-kicker">它最厉害的一件事</p>
          <h2 className="lp-h2">在浩如烟海的资料里,<span className="lp-grad-warm">替你找出细微的联系</span>。</h2>
          <p className="lp-lead lp-center-lead">两年前会议录音里的一句话、去年报告的第 7 页、上个月的一张截图、昨天的一条笔记——
            单看都不起眼,<b>连起来,才是答案</b>。人脑记不住这么多、隔这么久,它可以。</p>
        </div>
        <SceneLink />
      </section>

      {/* ④b 常用场景:它替你把活儿干完 */}
      <section className="lp-sec lp-scenes-sec">
        <div className="lp-reveal lp-sec-head">
          <p className="lp-kicker">这些时刻,你一定遇到过</p>
          <h2 className="lp-h2">到了要用的那一刻,<span className="lp-grad">它替你把活儿干完</span>。</h2>
        </div>
        <div className="lp-scenes">
          {SCENES.map((s, i) => {
            const A = s.anim
            return (
              <div key={i} className="lp-scene lp-reveal" style={{ transitionDelay: i * 90 + 'ms' }}>
                <p className="lp-scene-hook">{s.hook}</p>
                <A />
                <p className="lp-scene-how">{s.how}</p>
                <p className="lp-scene-res"><s>{s.old}</s><svg viewBox="0 0 24 24"><path d="M5 12h12M12.5 7 17.5 12 12.5 17" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /></svg><b>{s.neo}</b></p>
              </div>
            )
          })}
        </div>
      </section>

      {/* ⑤ 专辑案例 */}
      <section className="lp-sec lp-case">
        <div className="lp-reveal lp-sec-head lp-case-head">
          <p className="lp-kicker">它做出的专辑</p>
          <h2 className="lp-h2">你的记忆,被它做成<span className="lp-grad-warm">一部部专辑</span>。</h2>
          <p className="lp-lead">下面每一部,都是它从一个人的真实记录里——自己写脚本、自己作画、自己配乐,长出来的。</p>
        </div>
        <div className="lp-reveal">
          <FilmCard src="showcase_film.mp4" poster="showcase_poster.jpg" />
          <p className="lp-album-cap"><b>《深夜自学》</b>一段深夜苦读的日记,长成的铅笔片</p>
        </div>
        <div className="lp-reveal lp-mus-head">
          <p className="lp-kicker">它还会写歌</p>
          <h3 className="lp-mus-h">一段送外卖的真实经历,被它写成了主题曲——三个曲风,点开听。</h3>
        </div>
        <div className="lp-musics lp-reveal">
          {MUSIC.map((m) => <MusicCard key={m.src} m={m} />)}
        </div>
      </section>

      {/* ⑤ 你会得到什么 */}
      <section className="lp-sec lp-outcome-sec">
        <div className="lp-reveal lp-sec-head">
          <p className="lp-kicker">你会得到什么</p>
          <h2 className="lp-h2">让过去的每一分投入,<span className="lp-grad">在未来继续帮你</span>。</h2>
        </div>
        <div className="lp-outcomes">
          {OUTCOMES.map((o, i) => {
            const I = Ico[o.k]
            return (
              <div key={o.k} className="lp-outcome lp-reveal" style={{ transitionDelay: i * 90 + 'ms' }}>
                <div className="lp-outcome-ico"><I /></div>
                <div className="lp-outcome-txt">
                  <h3>{o.t}</h3>
                  <p>{o.d}</p>
                </div>
              </div>
            )
          })}
        </div>
      </section>

      {/* ⑥ 它怎么运作:手机采集 → 云中转 → 你的电脑大脑(数据本地) */}
      <section className="lp-sec lp-flow-sec">
        <div className="lp-reveal lp-sec-head lp-center">
          <p className="lp-kicker">它怎么运作</p>
          <h2 className="lp-h2">一个只属于你的大脑,<span className="lp-grad">养在你自己电脑里</span>。</h2>
          <p className="lp-lead lp-center-lead">别人的 AI 把你的数据收上云端;而它,把大脑留在你家。
            手机负责采集,我们只做加密中转,所有内容最终只落在<b>你自己的电脑</b>里。</p>
        </div>
        <SceneFlow />
      </section>

      {/* ⑦ 下载 */}
      <section id="lp-download" className="lp-sec lp-dl">
        <div className="lp-reveal lp-sec-head lp-dl-head">
          <p className="lp-kicker">装进日常</p>
          <h2 className="lp-h2">把它装进你的电脑,和口袋。</h2>
          <p className="lp-lead">一台常开的电脑,就是你第二大脑的家;手机随手一拍、随口一说,回家自动入库。</p>
        </div>
        <div className="lp-dl-cards">
          <div className="lp-dl-card lp-reveal">
            <div className="lp-dl-ico"><Ico.desktop /></div>
            <h3>桌面客户端</h3>
            <p>macOS · Windows<br />一键安装,开机常驻,内置 OCR 与本地模型</p>
            <span className="lp-dl-soon">内测打包中 · 即将开放</span>
          </div>
          <div className="lp-dl-card lp-reveal" style={{ transitionDelay: '90ms' }}>
            <div className="lp-dl-ico"><Ico.phone /></div>
            <h3>手机 App</h3>
            <p>iOS · Android<br />拍照、录音、随手记,走到哪记到哪</p>
            <span className="lp-dl-soon">内测打包中 · 即将开放</span>
          </div>
        </div>
        <p className="lp-dl-note lp-reveal">现在就想试?网页版已经可用——回到顶部,手机号登录即可。</p>
      </section>

      <footer className="lp-foot">
        <div className="lp-foot-brand"><Logo /><span>复利 Compound</span></div>
        <span>© {year} · 本地优先 · 隐私气隙 · 你的知识,复利成长</span>
      </footer>
    </div>
  )
}
