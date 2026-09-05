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

  // ★AI 欠费/key 错误:即使没有正在进行的活儿,也要冒出来提示(否则用户永远不知道后台因欠费停了)
  const llmErr = st && st.llm_error
  // 啥都没有就不显示
  if (!acts.length && !analyzing && !llmErr) return null

  // 胶囊主文案:欠费优先报警,其次导入,再次分析
  const pillText = llmErr ? (llmErr.kind === 'quota' ? 'AI 余额不足' : 'AI key 无效')
    : acts.length ? acts[0].title : ('分析中 ' + (st ? st.overall_pct : 0) + '%')
  const pillColor = llmErr ? '#f87171' : acts.length ? acts[0].color : '#8b8cff'

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

          {/* ★AI 额度/key 错误:后台建卡/情报调 LLM 失败(尤其余额不足),醒目提示而非无限转圈 */}
          {st && st.llm_error && (
            <div className="anz-llm-err" style={{ margin: '4px 0 10px', padding: '11px 13px', borderRadius: 10, background: 'rgba(239,68,68,.12)', border: '1px solid rgba(239,68,68,.4)', color: '#fca5a5', fontSize: 13, lineHeight: 1.55 }}>
              <b style={{ color: '#f87171' }}>{st.llm_error.kind === 'quota' ? 'AI 账户余额不足 / 额度用尽' : 'AI key 无效'}</b>
              <div style={{ marginTop: 3 }}>{st.llm_error.msg}</div>
              <div style={{ marginTop: 4, opacity: .85 }}>承诺雷达 / 人脉图谱要用 AI,{st.llm_error.kind === 'quota' ? '充值后' : '改好 key 后'}会自动继续,已入库的聊天不受影响。</div>
            </div>
          )}

          {/* 深挖分析进度 */}
          {analyzing && (
            <>
              {acts.length > 0 && <div className="anz-divider" />}
              <div className="anz-sub-h">深挖分析 · {st.overall_pct}%</div>
              <div className="anz-layers">
                {layers.map((l, i) => (
                  <div key={i} className={'anz-layer' + (l.pct >= 100 ? ' done' : l.needs_key ? ' needkey' : running && running.key === l.key ? ' active' : '')}>
                    <div className="anz-l-top">
                      <span className="anz-l-name">{l.label}{l.pct >= 100 && <span className="anz-l-tick">✓</span>}</span>
                      <span className="anz-l-n">{l.needs_key ? '需配 AI key' : `${l.done}/${l.total}`}</span>
                    </div>
                    <div className="anz-l-bar"><i style={{ width: l.pct + '%' }} /></div>
                    {l.needs_key ? <div className="anz-l-hint" style={{ color: '#fbbf24' }}>这一层要用 AI 分析 —— 去「设置」填一个 AI key 就会自动开始跑</div>
                      : (running && running.key === l.key && <div className="anz-l-hint">{l.hint}</div>)}
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
