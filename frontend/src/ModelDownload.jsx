import { useEffect, useState, useRef } from 'react'
import * as api from './api'

// ★首启模型下载页(Windows 瘦身版:安装器小,首次启动下核心模型)。
//   科幻精致:深空星云底 + 神经核心脉冲 + 能力模块逐个点亮 + 进度环 + 预估时间 + 安抚等待。
//   "下这些解锁那些":每个模型标清它解锁的功能,让客户明白等待的意义。

// 能力模块:名称 · 解锁的功能 · 体积(展示用;真实进度由后端 /api/model_status 给)
const MODULES = [
  { key: 'bge-m3', name: '语义大脑核心', unlock: '语义搜索 · 智能问答 · 星图 · 承诺雷达 · 人脉图谱', size: '2.3G',
    icon: 'M12 2a3 3 0 0 1 3 3 3 3 0 0 1 3 3 3 3 0 0 1 0 6 3 3 0 0 1-3 3 3 3 0 0 1-6 0 3 3 0 0 1-3-3 3 3 0 0 1 0-6 3 3 0 0 1 3-3 3 3 0 0 1 3-3z' },
  { key: 'sensevoice', name: '语音转写引擎', unlock: '音视频入库 · 语音/视频自动转文字', size: '0.9G',
    icon: 'M12 3v18M8 7v10M16 7v10M4 10v4M20 10v4' },
  { key: 'speaker', name: '说话人识别', unlock: '多人对话分角色 · 谁在说什么', size: '0.2G',
    icon: 'M9 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM17 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM3 20v-1a5 5 0 0 1 5-5h2M14 14h2a5 5 0 0 1 5 5v1' },
]

export default function ModelDownload({ onDone }) {
  const [st, setSt] = useState({ modules: {}, overall_pct: 0, eta: '', speed: '', done: false })
  const cvs = useRef(null)

  // 轮询后端下载进度
  useEffect(() => {
    let alive = true
    const tick = async () => {
      try {
        const s = await api.modelStatus()
        if (!alive) return
        setSt(s)
        if (s.done) { setTimeout(() => onDone && onDone(), 1200); return }
      } catch { /* 后端未就绪,继续轮询 */ }
      if (alive) setTimeout(tick, 1500)
    }
    tick()
    return () => { alive = false }
  }, [])

  // 深空星云 + 星尘漂移(canvas,轻量)
  useEffect(() => {
    const c = cvs.current; if (!c) return
    const ctx = c.getContext('2d'); let raf, t = 0
    const resize = () => { c.width = c.offsetWidth * 2; c.height = c.offsetHeight * 2 }
    resize(); window.addEventListener('resize', resize)
    const stars = Array.from({ length: 90 }, () => ({
      x: Math.random(), y: Math.random(), r: Math.random() * 2 + 0.4,
      s: Math.random() * 0.4 + 0.1, ph: Math.random() * 6.28,
    }))
    const draw = () => {
      t += 0.016; const W = c.width, H = c.height
      ctx.clearRect(0, 0, W, H)
      // 星云底光
      const g = ctx.createRadialGradient(W / 2, H * 0.42, 0, W / 2, H * 0.42, W * 0.5)
      g.addColorStop(0, 'rgba(94,120,255,0.10)'); g.addColorStop(0.5, 'rgba(139,80,255,0.05)'); g.addColorStop(1, 'rgba(0,0,0,0)')
      ctx.fillStyle = g; ctx.fillRect(0, 0, W, H)
      // 星尘
      for (const p of stars) {
        const yy = (p.y + t * p.s * 0.02) % 1
        const a = 0.35 + 0.35 * Math.sin(t * 1.5 + p.ph)
        ctx.beginPath(); ctx.arc(p.x * W, yy * H, p.r * 2, 0, 6.28)
        ctx.fillStyle = `rgba(180,200,255,${a})`; ctx.fill()
      }
      raf = requestAnimationFrame(draw)
    }
    draw()
    return () => { cancelAnimationFrame(raf); window.removeEventListener('resize', resize) }
  }, [])

  const overall = Math.round(st.overall_pct || 0)
  const R = 54, C = 2 * Math.PI * R, off = C * (1 - overall / 100)

  return (
    <div className="mdl-root">
      <canvas ref={cvs} className="mdl-bg" />
      <div className="mdl-inner">
        {/* 神经核心 + 进度环 */}
        <div className="mdl-core">
          <svg viewBox="0 0 140 140" className="mdl-ring">
            <circle cx="70" cy="70" r={R} className="mdl-ring-bg" />
            <circle cx="70" cy="70" r={R} className="mdl-ring-fg"
              style={{ strokeDasharray: C, strokeDashoffset: off }} />
          </svg>
          <div className="mdl-core-glow" />
          <div className="mdl-pct">{overall}<span>%</span></div>
        </div>

        <h1 className="mdl-title">正在唤醒你的第二大脑</h1>
        <p className="mdl-sub">
          首次启动需下载核心模型(约 <b>3.4G</b>)。下完后<b>全部离线可用</b>,以后秒开。
          {st.eta ? <> 预计还需 <b className="mdl-eta">{st.eta}</b>{st.speed ? ` · ${st.speed}` : ''}。</> : ' 正在连接模型源…'}
          <br />请<b>保持联网、耐心等待</b>,这一步只有一次。
        </p>

        {/* 能力模块逐个点亮 */}
        <div className="mdl-mods">
          {MODULES.map(m => {
            const p = st.modules[m.key] || {}
            const pct = Math.round(p.pct || 0)
            const state = p.done ? 'done' : (pct > 0 ? 'active' : 'wait')
            return (
              <div key={m.key} className={`mdl-mod ${state}`}>
                <div className="mdl-mod-ic">
                  <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                    <path d={m.icon} />
                  </svg>
                </div>
                <div className="mdl-mod-body">
                  <div className="mdl-mod-head">
                    <span className="mdl-mod-name">{m.name}</span>
                    <span className="mdl-mod-size">{state === 'done' ? '✓ 就绪' : `${pct}% · ${m.size}`}</span>
                  </div>
                  <div className="mdl-mod-unlock">解锁：{m.unlock}</div>
                  <div className="mdl-mod-bar"><i style={{ width: pct + '%' }} /></div>
                </div>
              </div>
            )
          })}
        </div>

        <div className="mdl-foot">全程只在你自己电脑 · 模型来自开源社区 · 下完即离线</div>
      </div>
    </div>
  )
}
