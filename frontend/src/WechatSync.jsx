import React, { useState, useEffect, useRef } from 'react'
import { api } from './api'
import { SYNC_DL } from './Guide'

// ===== 「数据入脑 · 神经流」canvas 场景 =====
// 左=信源(你的微信) 右=大脑核心(同心环+辉光呼吸) 中间=粒子数据流
// live: 青绿粒子持续流入,抵达时大脑泛起脉冲环;新消息到来爆发一簇
// detect: 淡蓝雷达扫描线绕大脑旋转;waiting: 琥珀粒子在信源端打转过不了桥;off: 熄灭
const NEURAL_COLORS = {
  live: { p: '#2dd4bf', core: '#34d399', ring: 'rgba(52,211,153,', src: '#4ade80' },
  detect: { p: '#38bdf8', core: '#38bdf8', ring: 'rgba(56,189,248,', src: '#38bdf8' },
  waiting: { p: '#f59e0b', core: '#f59e0b', ring: 'rgba(245,158,11,', src: '#f59e0b' },
  off: { p: '#3a4150', core: '#3a4150', ring: 'rgba(90,98,114,', src: '#3a4150' },
}

function SyncNeural({ mode, burstKey }) {
  const hostRef = useRef(null)
  const modeRef = useRef(mode)
  const burstRef = useRef(0)
  useEffect(() => { modeRef.current = mode }, [mode])
  useEffect(() => { if (burstKey) burstRef.current = 14 }, [burstKey])   // 新消息 → 爆发一簇粒子

  useEffect(() => {
    const host = hostRef.current
    if (!host) return
    const cv = document.createElement('canvas')
    cv.style.cssText = 'width:100%;height:100%;display:block'
    host.appendChild(cv)
    const ctx = cv.getContext('2d')
    const dpr = Math.min(2, window.devicePixelRatio || 1)
    let W = 0, H = 0, raf = 0, alive = true
    const fit = () => { W = host.clientWidth; H = host.clientHeight; cv.width = W * dpr; cv.height = H * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0) }
    fit()
    const ro = new ResizeObserver(fit); ro.observe(host)

    const parts = []   // {t, y0, speed, orbit}
    let lastSpawn = 0, sweep = 0
    const bez = (t, y0) => {   // 信源→大脑 的弧线
      const x0 = W * 0.13, x1 = W * 0.87, cx = W * 0.5, cy = H * 0.5 + y0 * 2.2
      const y0p = H * 0.5 + y0, y1 = H * 0.5
      const u = 1 - t
      return [u * u * x0 + 2 * u * t * cx + t * t * x1, u * u * y0p + 2 * u * t * cy + t * t * y1]
    }

    const draw = (now) => {
      if (!alive) return
      const m = modeRef.current
      const C = NEURAL_COLORS[m] || NEURAL_COLORS.off
      const T = now / 1000
      ctx.clearRect(0, 0, W, H)
      const bx = W * 0.87, by = H * 0.5, sx = W * 0.13, sy = H * 0.5

      // —— 桥(暗轨道,waiting 时断为虚线)——
      ctx.save()
      ctx.strokeStyle = m === 'off' ? 'rgba(255,255,255,0.04)' : C.ring + '0.10)'
      ctx.lineWidth = 1
      if (m === 'waiting') ctx.setLineDash([3, 7])
      ctx.beginPath()
      for (let i = 0; i <= 40; i++) { const [x, y] = bez(i / 40, 0); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y) }
      ctx.stroke()
      ctx.restore()

      // —— 粒子 ——
      if (m === 'live' || m === 'waiting') {
        const rate = burstRef.current > 0 ? 40 : (m === 'live' ? 200 : 420)
        if (now - lastSpawn > rate) {
          lastSpawn = now
          if (burstRef.current > 0) burstRef.current--
          parts.push({ t: 0, y0: (Math.random() - 0.5) * H * 0.36, speed: 0.004 + Math.random() * 0.004, orbit: Math.random() * Math.PI * 2 })
        }
      }
      for (let i = parts.length - 1; i >= 0; i--) {
        const p = parts[i]
        if (m === 'waiting') {
          // 过不了桥:在信源附近打转
          p.orbit += 0.03
          const r = 16 + 7 * Math.sin(p.orbit * 1.7)
          const x = sx + Math.cos(p.orbit) * r, y = sy + Math.sin(p.orbit) * r * 0.75
          ctx.globalAlpha = 0.5; ctx.fillStyle = C.p
          ctx.beginPath(); ctx.arc(x, y, 1.4, 0, 7); ctx.fill()
          if (parts.length > 26) parts.splice(i, 1)
          continue
        }
        p.t += p.speed
        if (p.t >= 1) { parts.splice(i, 1); continue }
        const [x, y] = bez(p.t, p.y0)
        ctx.globalAlpha = 0.25 + 0.75 * p.t
        ctx.fillStyle = C.p
        ctx.shadowColor = C.p; ctx.shadowBlur = 6
        ctx.beginPath(); ctx.arc(x, y, 1.7, 0, 7); ctx.fill()
        ctx.shadowBlur = 0
        // 拖尾
        const [tx, ty] = bez(Math.max(0, p.t - 0.05), p.y0)
        ctx.globalAlpha = 0.16; ctx.strokeStyle = C.p; ctx.lineWidth = 1
        ctx.beginPath(); ctx.moveTo(tx, ty); ctx.lineTo(x, y); ctx.stroke()
      }
      ctx.globalAlpha = 1

      // —— 信源节点(你的微信)——
      const spulse = 1 + 0.1 * Math.sin(T * 2.4)
      ctx.fillStyle = C.src; ctx.globalAlpha = m === 'off' ? 0.35 : 0.9
      ctx.shadowColor = C.src; ctx.shadowBlur = m === 'off' ? 0 : 10
      ctx.beginPath(); ctx.arc(sx, sy, 5 * spulse, 0, 7); ctx.fill()
      ctx.shadowBlur = 0; ctx.globalAlpha = 1
      ctx.strokeStyle = C.ring + '0.35)'; ctx.lineWidth = 1
      ctx.beginPath(); ctx.arc(sx, sy, 11, 0, 7); ctx.stroke()

      // —— 大脑核心(多环+旋转刻度+呼吸+双抵达脉冲)——
      const breathe = 1 + 0.06 * Math.sin(T * 1.8)
      for (let ri = 4; ri >= 1; ri--) {
        ctx.strokeStyle = C.ring + (m === 'off' ? 0.07 : 0.12 * ri) + ')'
        ctx.lineWidth = ri === 1 ? 1.5 : 1
        ctx.beginPath(); ctx.arc(bx, by, (9 + ri * 7) * breathe, 0, 7); ctx.stroke()
      }
      // 旋转刻度环(科技感)
      if (m !== 'off') {
        ctx.save(); ctx.translate(bx, by); ctx.rotate(T * 0.5)
        ctx.strokeStyle = C.ring + '0.4)'; ctx.lineWidth = 1.4
        for (let a = 0; a < 12; a++) { const an = a / 12 * Math.PI * 2; const r0 = 30 * breathe, r1 = 34 * breathe
          ctx.beginPath(); ctx.moveTo(Math.cos(an) * r0, Math.sin(an) * r0); ctx.lineTo(Math.cos(an) * r1, Math.sin(an) * r1); ctx.stroke() }
        ctx.restore()
      }
      ctx.fillStyle = C.core
      ctx.globalAlpha = m === 'off' ? 0.4 : 1
      ctx.shadowColor = C.core; ctx.shadowBlur = m === 'off' ? 0 : 22
      ctx.beginPath(); ctx.arc(bx, by, 7 * breathe, 0, 7); ctx.fill()
      ctx.shadowBlur = 0; ctx.globalAlpha = 1
      // live: 双周期扩散脉冲环
      if (m === 'live') {
        for (const off of [0, 0.5]) {
          const pt = ((T + off * 1.6) % 1.6) / 1.6
          ctx.strokeStyle = C.ring + (0.5 * (1 - pt)) + ')'
          ctx.lineWidth = 1.5
          ctx.beginPath(); ctx.arc(bx, by, 12 + pt * 34, 0, 7); ctx.stroke()
        }
      }
      // detect: 雷达扫描线
      if (m === 'detect') {
        sweep += 0.045
        ctx.save()
        ctx.translate(bx, by); ctx.rotate(sweep)
        const g = ctx.createLinearGradient(0, 0, 34, 0)
        g.addColorStop(0, C.ring + '0.55)'); g.addColorStop(1, C.ring + '0)')
        ctx.strokeStyle = g; ctx.lineWidth = 2
        ctx.beginPath(); ctx.moveTo(0, 0); ctx.lineTo(34, 0); ctx.stroke()
        ctx.restore()
      }

      raf = requestAnimationFrame(draw)
    }
    raf = requestAnimationFrame(draw)
    return () => { alive = false; cancelAnimationFrame(raf); ro.disconnect(); host.removeChild(cv) }
  }, [])

  return <div className="wx-neural" ref={hostRef} />
}

// 微信聊天同步控制台:
//   · 实时同步 → 呼吸状态球(检测/实时中/等待/关闭 四态,颜色+动效各异)
//   · iPhone 历史导入 → 蓝色五段式进度(连接→备份→解析→认人→写入),当前段高亮
// 数据来自桌面客户端上报的 /api/realtime/* 与 /api/ingest/progress。
const STATE_LABEL = {
  queued: '排队中', uploading: '上传中', parsing: '解析中',
  matching_contacts: '认人中', embedding: '嵌入中', done: '完成', failed: '失败',
}
const STATE_PCT = { queued: 5, uploading: 25, parsing: 50, matching_contacts: 70, embedding: 90, done: 100, failed: 100 }

// iPhone 一次性导入的阶段(按总进度百分比点亮),对应 import_iphone.py 的上报节点
const IOS_STAGES = ['连接手机', '备份聊天', '解析数据', '识别联系人', '写入大脑']
function iosStageIndex(pct) {
  // 对齐 import_iphone.py 各阶段上报的百分比:连接5-10 / 备份15-55 / 解析58-62 / 认人66 / 抽取+上传70-98
  if (pct < 15) return 0
  if (pct < 58) return 1
  if (pct < 64) return 2
  if (pct < 70) return 3
  return 4
}

export default function WechatSync({ onGuide }) {
  const [rt, setRt] = useState(null)          // realtime status
  const [prog, setProg] = useState(null)      // ingest progress
  const [toggling, setToggling] = useState(false)
  const timer = useRef(null)

  const refresh = () => {
    api.realtimeStatus().then(setRt).catch(() => {})
    api.ingestProgress().then(setProg).catch(() => {})
  }
  useEffect(() => {
    refresh()
    timer.current = setInterval(refresh, 4000)
    return () => clearInterval(timer.current)
  }, [])

  const toggle = () => {
    if (!rt) return
    setToggling(true)
    api.realtimeToggle(!rt.enabled).then((r) => { setRt((s) => ({ ...s, enabled: r.enabled })); setToggling(false); setTimeout(refresh, 500) }).catch(() => setToggling(false))
  }

  const items = (prog && prog.items) || []
  const nowSec = Date.now() / 1000

  // ── iPhone 导入(job_id 以 iphone 开头)──────────────────────────
  const iosItems = items.filter((x) => (x.job_id || '').startsWith('iphone'))
  const iosOverall = items.find((x) => x.job_id === 'iphone-import')
  const iosSessions = iosItems.filter((x) => x.job_id !== 'iphone-import')
  const iosDone = !!iosOverall && iosOverall.state === 'done'
  const iosFailed = !!iosOverall && iosOverall.state === 'failed'
  const iosRunning = iosItems.some((x) => x.state !== 'done' && x.state !== 'failed' && (nowSec - (x.ts || 0) < 120))
  const showIos = iosRunning || (!!iosOverall && (nowSec - (iosOverall.ts || 0) < 45)) // 刚完成也留展示片刻
  const iosPct = iosDone ? 100 : (iosOverall ? (iosOverall.percent || 0) : 0)
  const iosStage = iosDone ? IOS_STAGES.length : iosStageIndex(iosPct)

  // ── 实时同步四态 ───────────────────────────────────────────────
  const live = !!(rt && rt.enabled && rt.running && rt.fresh)
  const waiting = !!(rt && rt.enabled && !live)
  const mode = !rt ? 'detect' : live ? 'live' : waiting ? 'waiting' : 'off'
  const badgeText = { detect: '检测中', live: '实时同步中', waiting: '等待客户端', off: '已关闭' }[mode]

  // ── 常规实时入库进度(排除 iOS 那批)───────────────────────────
  const rtItems = items.filter((x) => !(x.job_id || '').startsWith('iphone'))
  const active = rtItems.filter((x) => x.state !== 'done' && x.state !== 'failed')
  const recentDone = rtItems.filter((x) => x.state === 'done').slice(0, 6)

  // Tab:实时同步 / iPhone 历史导入;iOS 正在跑时自动切过去
  const [tab, setTab] = useState('live')
  useEffect(() => { if (showIos && !iosDone) setTab('ios') }, [showIos, iosDone])

  return (
    <div className={'wx-console2 glass wxm-' + mode}>
      <div className="wx-grid-bg" aria-hidden />

      {/* 顶部:标题 + Tab 切换 + 状态徽章 */}
      <div className="wx-c2-head">
        <div className="wx-c2-title"><span className="wx-c2-dot" />微信数据 · 同步中枢</div>
        <div className="wx-c2-tabs">
          <button className={tab === 'live' ? 'on' : ''} onClick={() => setTab('live')}>实时同步</button>
          <button className={tab === 'ios' ? 'on' : ''} onClick={() => setTab('ios')}>iPhone 导入历史{showIos && !iosDone && <i className="wx-tab-live" />}</button>
        </div>
        {tab === 'live'
          ? <div className={'wx-badge ' + mode}><span className="wxb-dot" />{badgeText}</div>
          : <div className={'wx-badge ' + (showIos ? (iosDone ? 'live' : 'detect') : 'off')}><span className="wxb-dot" />{showIos ? (iosDone ? '导入完成' : '导入中') : '未在导入'}</div>}
      </div>

      {/* ===== TAB 1:实时同步 ===== */}
      {tab === 'live' && (
        <div className="wx-c2-body">
          <div className="wx-neural-wrap">
            <SyncNeural mode={mode} burstKey={(rt && (String(rt.last_synced || '') + '|' + (rt.pending || 0))) || ''} />
            <div className="wxn-endpoint l">
              <i className="wxne-ic wx"><svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><path d="M9 4C4.9 4 1.5 6.9 1.5 10.4c0 2 1.1 3.7 2.9 4.9L3.6 18l2.8-1.4c.5.1 1 .2 1.5.3a5.6 5.6 0 0 1-.2-1.5c0-3.4 3.3-6.1 7.3-6.1.3 0 .5 0 .8.1C16.5 6.3 13.1 4 9 4z"/><path d="M22.5 15.1c0-2.8-2.8-5.1-6.2-5.1S10 12.3 10 15.1s2.8 5.1 6.2 5.1c.7 0 1.4-.1 2.1-.3l2.2 1.1-.6-1.9c1.6-1 2.6-2.5 2.6-4z"/></svg></i>
              <b>你的微信</b><u>本地 · 你自己的电脑</u>
            </div>
            <div className="wxn-endpoint r">
              <i className="wxne-ic brain"><svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" strokeWidth="1.4"><circle cx="12" cy="12" r="2.3" fill="currentColor" stroke="none"/><circle cx="5" cy="7" r="1.5" fill="currentColor" stroke="none"/><circle cx="19" cy="7" r="1.5" fill="currentColor" stroke="none"/><circle cx="5" cy="17" r="1.5" fill="currentColor" stroke="none"/><circle cx="19" cy="17" r="1.5" fill="currentColor" stroke="none"/><path d="M6.3 7.7 10 10.8M17.7 7.7 14 10.8M6.3 16.3 10 13.2M17.7 16.3 14 13.2"/></svg></i>
              <b>第二大脑</b><u>实时接收 · 秒级入库</u>
            </div>
          </div>
          <div className="wx-c2-status">
            {mode === 'detect' && <>正在探测你电脑上的同步助手…<em>打开助手即接通</em></>}
            {mode === 'live' && <>第二大脑<b>正在实时接收</b>你的新消息{rt.last_synced ? ' · 最近 ' + rt.last_synced : ''}{rt.pending ? <em>待入库 {rt.pending} 条</em> : null}</>}
            {mode === 'waiting' && <>通道已就绪,数据在源头等待<em>去电脑打开同步助手即接通</em></>}
            {mode === 'off' && <>实时同步已暂停 · 打开后你在手机上聊的每条都会自动进大脑</>}
          </div>

          <div className="wx-switch-box">
            <label className="wx-toggle2">
              <input type="checkbox" checked={!!(rt && rt.enabled)} disabled={toggling || !rt} onChange={toggle} />
              <span className="wx-toggle-track"><span className="wx-toggle-knob" /></span>
              <span className="wx-toggle-label">{rt && rt.enabled ? '同步总开关 · 已允许接收' : '同步总开关 · 已暂停'}</span>
            </label>
            <div className="wx-switch-note">
              在电脑上<b>打开「微信同步助手」并保持运行</b>,这里就会<b>自动接通</b> —— 几秒内徽章亮起"实时同步中",无需在网页做任何操作。这个开关是总闸,可随时暂停 / 继续接收。
              {mode !== 'live' && <span className="wx-switch-cta" onClick={() => onGuide && onGuide('realtime')}> 助手还没开?看怎么启动 →</span>}
            </div>
          </div>

          {(active.length > 0 || recentDone.length > 0) && (
            <div className="wx-prog">
              <div className="wx-prog-head">实时入库{active.length > 0 ? ' · ' + active.length + ' 个进行中' : ''}</div>
              {active.map((it, i) => (
                <div key={i} className="wx-prog-row">
                  <span className="wx-prog-name">{it.contact || '聊天'}</span>
                  <span className="wx-prog-track"><span className="wx-prog-fill" style={{ width: (it.percent || STATE_PCT[it.state] || 0) + '%' }} /></span>
                  <span className={'wx-prog-state' + (it.state === 'failed' ? ' fail' : '')}>{STATE_LABEL[it.state] || it.state}</span>
                </div>
              ))}
              {recentDone.map((it, i) => (
                <div key={'d' + i} className="wx-prog-row done">
                  <span className="wx-prog-name">{it.contact || '聊天'}</span>
                  <span className="wx-prog-track"><span className="wx-prog-fill full" style={{ width: '100%' }} /></span>
                  <span className="wx-prog-state ok">已入库</span>
                </div>
              ))}
            </div>
          )}

          <div className="wx-dlbox">
            <div className="wx-dlbox-head">
              <span className="wx-dlbox-t">第一次用?先下载「微信同步助手」</span>
              <button className="wx-dlbox-how" onClick={() => onGuide && onGuide('realtime')}>怎么装?看图文 →</button>
            </div>
            <div className="wx-dlbox-grid">
              {SYNC_DL.map((d, i) => (
                <a key={i} className="wx-dlbox-btn" href={'/dl/' + encodeURIComponent(d.file)} download>
                  <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M12 3v12m0 0 4-4m-4 4-4-4M4 19h16"/></svg>
                  <span className="wx-dlbox-l">{d.label}</span>
                  <span className="wx-dlbox-h">{d.hint}</span>
                </a>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ===== TAB 2:iPhone 导入历史 ===== */}
      {tab === 'ios' && (
        <div className="wx-c2-body">
          {!showIos ? (
            <div className="wx-ios-idle">
              <div className="wx-ios-idle-ic">
                <svg viewBox="0 0 24 24" width="30" height="30" fill="none" stroke="currentColor" strokeWidth="1.4"><rect x="6.5" y="2.5" width="11" height="19" rx="2.6"/><path d="M10.5 5.5h3"/></svg>
              </div>
              <div className="wx-ios-idle-t">把电脑版登录<b>之前</b>的老聊天,一次性补进来</div>
              <div className="wx-ios-idle-s">用数据线把 iPhone 连上电脑,在同步助手里点「连手机导入历史」,这里就会实时显示进度。做一次即可,平时不用连。</div>
              <button className="btn btn-primary" onClick={() => onGuide && onGuide('ios')}>看 iPhone 导入图文步骤 →</button>
            </div>
          ) : (
            <>
              <div className="wx-ios2-head">
                <span className="wx-ios2-title">{iosDone ? 'iPhone 历史导入完成' : iosFailed ? 'iPhone 导入失败,请重试' : '正在从 iPhone 导入历史聊天'}</span>
                <span className="wx-ios2-pct">{iosPct}<i>%</i></span>
              </div>
              <div className="wx-pipe">
                <svg className="wx-pipe-svg" viewBox="0 0 500 56" preserveAspectRatio="none">
                  <defs>
                    <linearGradient id="wxpg" x1="0" y1="0" x2="1" y2="0">
                      <stop offset="0" stopColor="#38bdf8" stopOpacity="0" /><stop offset="0.5" stopColor="#38bdf8" /><stop offset="1" stopColor="#2dd4bf" />
                    </linearGradient>
                  </defs>
                  <line x1="20" y1="28" x2="480" y2="28" stroke="rgba(255,255,255,0.08)" strokeWidth="2" />
                  <line x1="20" y1="28" x2={20 + 4.6 * iosPct} y2="28" stroke="url(#wxpg)" strokeWidth="2.5" />
                  <line x1="20" y1="28" x2={20 + 4.6 * iosPct} y2="28" stroke="#aef3ff" strokeWidth="2.5" className="wx-pipe-pulse" />
                </svg>
                <div className="wx-pipe-nodes">
                  {IOS_STAGES.map((s, i) => {
                    const st = iosDone ? 'ok' : i < iosStage ? 'ok' : i === iosStage ? 'cur' : 'todo'
                    return (
                      <div key={i} className={'wx-pipe-node ' + st}>
                        <span className="wpn-halo" /><span className="wpn-dot" /><span className="wpn-name">{s}</span>
                      </div>
                    )
                  })}
                </div>
              </div>
              {iosOverall && iosOverall.message && !iosDone && !iosFailed && <div className="wx-ios-msg">{iosOverall.message}</div>}
              {iosSessions.filter((x) => x.state !== 'done').slice(0, 4).map((it, i) => (
                <div key={i} className="wx-ios-sess">
                  <span className="wis-c">{it.contact || '会话'}</span>
                  <span className={'wis-s' + (it.state === 'failed' ? ' fail' : '')}>{STATE_LABEL[it.state] || it.state}</span>
                </div>
              ))}
              {iosDone && <div className="wx-ios-msg ok">历史聊天已进第二大脑 · 现在就能搜索 / 提问 / 生成人脉卡</div>}
            </>
          )}
        </div>
      )}
    </div>
  )
}
