import React, { useState, useEffect, useRef } from 'react'
import { api } from './api'

// 右下角常驻状态胶囊:
//   ① 正在导入/同步(文件入库 / 微信实时 / iPhone 历史)—— 有活动就实时冒出来
//   ② 第二大脑深挖进度(嵌入/关系卡/人脉图谱)—— 后台慢分析时告诉用户在干活
const IOS_STAGES = ['连接手机', '备份聊天', '解析数据', '识别联系人', '写入大脑']
function iosStageIdx(p) { return p < 15 ? 0 : p < 58 ? 1 : p < 64 ? 2 : p < 70 ? 3 : 4 }

export default function AnalysisStatus() {
  const [st, setSt] = useState(null)        // 分析进度
  const [rt, setRt] = useState(null)        // 实时同步状态
  const [prog, setProg] = useState(null)    // 入库进度(文件+iOS)
  const [open, setOpen] = useState(false)
  const timer = useRef(null)

  const refresh = () => {
    api.analysisStatus().then(setSt).catch(() => {})
    api.realtimeStatus().then(setRt).catch(() => {})
    api.ingestProgress().then(setProg).catch(() => {})
  }
  useEffect(() => {
    refresh()
    timer.current = setInterval(refresh, 5000)
    return () => clearInterval(timer.current)
  }, [])

  // ── 汇总"正在进行的活儿" ──
  const items = (prog && prog.items) || []
  const nowSec = Date.now() / 1000
  const fresh = (x) => (nowSec - (x.ts || 0) < 120)

  // iPhone 导入
  const iosAll = items.find((x) => x.job_id === 'iphone-import')
  const iosRunning = items.some((x) => (x.job_id || '').startsWith('iphone') && x.state !== 'done' && x.state !== 'failed' && fresh(x))
  const iosPct = iosAll ? (iosAll.percent || 0) : 0

  // 普通文件/网页入库(非 iOS)
  const fileActive = items.filter((x) => !(x.job_id || '').startsWith('iphone') && x.state !== 'done' && x.state !== 'failed' && fresh(x))

  // 微信实时:刚有新消息进来
  const rtLive = !!(rt && rt.enabled && rt.running && rt.fresh)
  const rtPending = (rt && rt.pending) || 0

  // 组装活动列表(有则显示在最上,优先级:iOS导入 > 文件入库 > 微信实时增量)
  const acts = []
  if (iosRunning) acts.push({ key: 'ios', color: '#38bdf8', title: '正在从 iPhone 导入历史', sub: IOS_STAGES[iosStageIdx(iosPct)] + ' · ' + iosPct + '%', pct: iosPct })
  if (fileActive.length) acts.push({ key: 'file', color: '#a78bfa', title: '正在入库 ' + fileActive.length + ' 个文件', sub: (fileActive[0].contact || fileActive[0].name || '处理中') + '…' })
  if (rtLive && rtPending > 0) acts.push({ key: 'rt', color: '#34d399', title: '微信实时同步中', sub: '正在接收 ' + rtPending + ' 条新消息' })

  const analyzing = st && !st.done
  const layers = (st && st.layers) || []
  const running = layers.find((l) => l.pct < 100)

  // 啥都没有就不显示
  if (!acts.length && !analyzing) return null

  // 胶囊主文案:有导入活动优先报导入,否则报分析
  const pillText = acts.length ? acts[0].title : ('分析中 ' + (st ? st.overall_pct : 0) + '%')
  const pillColor = acts.length ? acts[0].color : '#8b8cff'

  return (
    <div className={'anz' + (open ? ' open' : '')}>
      {open ? (
        <div className="anz-card glass">
          <div className="anz-head">
            <span className="anz-orb" style={{ color: pillColor }}><span className="anz-orb-c" /></span>
            <div className="anz-title">第二大脑 · 实时状态</div>
            <button className="anz-min" title="收起成小胶囊" onClick={() => setOpen(false)}>—</button>
          </div>

          {/* 导入/同步活动 */}
          {acts.length > 0 && (
            <div className="anz-acts">
              {acts.map((a) => (
                <div key={a.key} className="anz-act">
                  <span className="anz-act-dot" style={{ background: a.color, boxShadow: '0 0 8px ' + a.color }} />
                  <div className="anz-act-body">
                    <div className="anz-act-t">{a.title}</div>
                    <div className="anz-act-s">{a.sub}</div>
                    {a.pct != null && <div className="anz-act-bar"><i style={{ width: a.pct + '%', background: a.color }} /></div>}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* 深挖分析进度 */}
          {analyzing && (
            <>
              {acts.length > 0 && <div className="anz-divider" />}
              <div className="anz-sub-h">深挖分析 · {st.overall_pct}%</div>
              <div className="anz-layers">
                {layers.map((l, i) => (
                  <div key={i} className={'anz-layer' + (l.pct >= 100 ? ' done' : running && running.key === l.key ? ' active' : '')}>
                    <div className="anz-l-top">
                      <span className="anz-l-name">{l.label}{l.pct >= 100 && <span className="anz-l-tick">✓</span>}</span>
                      <span className="anz-l-n">{l.done}/{l.total}</span>
                    </div>
                    <div className="anz-l-bar"><i style={{ width: l.pct + '%' }} /></div>
                    {running && running.key === l.key && <div className="anz-l-hint">{l.hint}</div>}
                  </div>
                ))}
              </div>
              <div className="anz-note"><b>全程后台进行,不影响你正常使用</b>,完成后图谱/画像/标签自动点亮。</div>
            </>
          )}
        </div>
      ) : (
        <button className="anz-pill glass" onClick={() => setOpen(true)}>
          <span className="anz-orb sm" style={{ color: pillColor }}><span className="anz-orb-c" /></span>
          {pillText}
        </button>
      )}
    </div>
  )
}
