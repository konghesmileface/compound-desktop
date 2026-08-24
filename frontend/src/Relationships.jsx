import React, { useState, useEffect, useMemo, useRef } from 'react'
import { api } from './api'
import { Thinking, toast, confirmDialog, Empty } from './ui'
import { IconSearch, IconClose, IconNetwork } from './icons'
import ReportPanel from './ReportPanel'

// 卡片操作图标(悬浮有 title 提示)
const IC = {
  brief: <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round"><rect x="4" y="3" width="16" height="18" rx="2" /><path d="M8 7h8M8 11h8M8 15h5" /></svg>,
  doc: <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round"><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z" /><path d="M14 3v6h6M9 15h6M12 18v-6" /></svg>,
  spark: <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round"><path d="M12 3l1.9 4.6L18.5 9.5 13.9 11.4 12 16l-1.9-4.6L5.5 9.5l4.6-1.9z" /><path d="M19 14.5l.7 1.8 1.8.7-1.8.7-.7 1.8-.7-1.8-1.8-.7 1.8-.7z" /></svg>,
  ask: <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /><path d="M9.6 9a2.4 2.4 0 0 1 4.4 1.3c0 1.4-1.8 1.8-1.8 2.4M12 16h.01" /></svg>,
  chat: <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round"><path d="M21 11.5a8.5 8.5 0 0 1-12.3 7.6L3 21l1.9-5.7A8.5 8.5 0 1 1 21 11.5z" /><path d="M8 10h8M8 14h5" /></svg>,
  spin: <svg className="rel-ic-spin" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><path d="M12 3a9 9 0 1 0 9 9" /></svg>,
}

// 人脉 · 关系操作系统:替你记住每个人、每件没了结的事、谁欠谁人情
export default function Relationships({ onOpen, onAsk, onAskContact }) {
  const [cards, setCards] = useState(null)
  const [err, setErr] = useState(false)
  const [q, setQ] = useState('')
  const [sort, setSort] = useState('recent')   // recent | loops | msgs | name
  const [kind, setKind] = useState('all')      // all | chat | group
  const [refreshing, setRefreshing] = useState(false)
  const [graph, setGraph] = useState(null)     // 人脉关系网
  const [pathA, setPathA] = useState('')
  const [pathB, setPathB] = useState('')
  const [pathRes, setPathRes] = useState(null)
  const [brief, setBrief] = useState(null)   // 见面简报 modal
  const [showAllLoops, setShowAllLoops] = useState(false)
  const [dismissedLoops, setDismissedLoops] = useState(() => new Set())   // 用户删掉的待了结(本地即时隐藏)
  const [dismissedReach, setDismissedReach] = useState(() => new Set())   // 从"该联系了"移除的人
  const gridRef = useRef(null)
  const [cols, setCols] = useState(3)   // 卡片瀑布流列数(按宽度自适应)
  const [netOpen, setNetOpen] = useState(false)   // 人脉关系网默认收起
  const [deepening, setDeepening] = useState(null)   // 正在 pro 深度分析的 contact
  const [reportContact, setReportContact] = useState(null)   // 打开产出文档面板的 contact
  const [destroying, setDestroying] = useState({})   // 正在销毁动画的 contact

  const removeCard = async (contact) => {
    if (!(await confirmDialog('删除「' + contact + '」的关系卡?\n只删卡片,聊天记录不会删除,以后还能重新分析生成。', '删除卡片'))) return
    setDestroying((d) => ({ ...d, [contact]: true }))
    api.deleteCard(contact).catch(() => {})
    setTimeout(() => {
      setCards((cs) => (cs || []).filter((c) => c.contact !== contact))
      toast('已删除卡片(聊天记录保留)', 'ok')
    }, 520)
  }

  const deepen = (contact) => {
    setDeepening(contact)
    toast('正在用 pro 深度分析(约1分钟)…', 'info')
    api.deepen(contact).then((r) => {
      if (r && r.card) setCards((cs) => (cs || []).map((c) => c.contact === contact ? { ...c, ...r.card } : c))
      setDeepening(null); toast('深度分析完成', 'ok')
    }).catch(() => { setDeepening(null); toast('深度分析失败,请重试', 'err') })
  }

  const openBrief = (contact) => {
    setBrief({ contact, loading: true })
    api.briefing(contact).then((b) => setBrief({ contact, ...b, loading: false })).catch(() => setBrief({ contact, found: false, loading: false }))
  }

  const load = (refresh) => {
    if (refresh) setRefreshing(true)
    api.relationships(refresh).then((r) => { setCards(r.cards || []); setRefreshing(false) }).catch(() => { setErr(true); setRefreshing(false) })
  }
  useEffect(() => { load(false) }, [])
  useEffect(() => { api.relGraph().then(setGraph).catch(() => {}) }, [])

  const findPath = () => {
    if (!pathA || !pathB || pathA === pathB) return
    setPathRes({ loading: true })
    api.relPath(pathA, pathB).then(setPathRes).catch(() => setPathRes({ found: false }))
  }

  const totalLoops = useMemo(() => (cards || []).reduce((s, c) => s + (c.open_loops || []).length, 0), [cards])
  const totalFavors = useMemo(() => (cards || []).reduce((s, c) => s + (c.favors || []).length, 0), [cards])

  // 从待了结文本里抠出日期(如 "2026年7月10日…" / "2026-07-10"),用于时间维度
  const loopDate = (txt) => {
    const m = String(txt || '').match(/(\d{4})[年.\-/](\d{1,2})[月.\-/](\d{1,2})/)
    if (!m) return null
    const d = new Date(+m[1], +m[2] - 1, +m[3])
    return isNaN(d.getTime()) ? null : d.getTime()
  }
  // 全部未了结的事(跨人聚合)—— 新→旧排序,已删的剔除;最有行动价值的一屏
  const allLoops = useMemo(() => {
    const out = []
    for (const c of cards || []) for (const o of (c.open_loops || [])) {
      const key = c.contact + '|' + o
      if (dismissedLoops.has(key)) continue
      out.push({ contact: c.contact, doc_id: c.doc_id, text: o, ts: loopDate(o), key })
    }
    out.sort((a, b) => (a.ts == null ? 1 : 0) - (b.ts == null ? 1 : 0) || (b.ts || 0) - (a.ts || 0))
    return out
  }, [cards, dismissedLoops])
  // 默认只看近一个月(用户点"查看全部"才展开)
  const recentLoops = useMemo(() => {
    const cut = Date.now() - 35 * 86400000
    return allLoops.filter((l) => l.ts != null && l.ts >= cut)
  }, [allLoops])
  // 删除一条待了结(不打算做的)——只隐藏,聊天原文不动
  const dismissLoop = (l) => {
    setDismissedLoops((s) => { const n = new Set(s); n.add(l.key); return n })
    api.dismissLoop(l.contact, l.text).catch(() => {})
  }

  // 该联系了:很久没联系的人(按 days_ago 降序),排除用户手动移除的
  const toReach = useMemo(() =>
    (cards || []).filter((c) => c.days_ago != null && c.days_ago >= 14 && !c.reach_hidden && !dismissedReach.has(c.contact))
      .sort((a, b) => b.days_ago - a.days_ago).slice(0, 8), [cards, dismissedReach])
  const dismissReach = (contact) => {
    setDismissedReach((s) => { const n = new Set(s); n.add(contact); return n })
    api.dismissReach(contact).catch(() => {})
  }

  const view = useMemo(() => {
    let list = (cards || [])
    if (kind === 'group') list = list.filter((c) => c.is_group)
    else if (kind === 'chat') list = list.filter((c) => !c.is_group)
    if (q.trim()) {
      const kw = q.trim().toLowerCase()
      list = list.filter((c) => (c.contact + ' ' + (c.identity || '') + ' ' + (c.facts || []).join(' ') + ' ' + (c.open_loops || []).join(' ')).toLowerCase().includes(kw))
    }
    const arr = [...list]
    // 最近联系:days_ago 小的(近)在前,时间未知的沉底
    if (sort === 'recent') arr.sort((a, b) => (a.days_ago == null ? 1 : 0) - (b.days_ago == null ? 1 : 0) || (a.days_ago ?? 1e9) - (b.days_ago ?? 1e9))
    else if (sort === 'loops') arr.sort((a, b) => ((b.open_loops || []).length + (b.favors || []).length) - ((a.open_loops || []).length + (a.favors || []).length) || (b.msgcount || 0) - (a.msgcount || 0))
    else if (sort === 'msgs') arr.sort((a, b) => (b.msgcount || 0) - (a.msgcount || 0))
    else arr.sort((a, b) => (a.contact || '').localeCompare(b.contact || ''))
    return arr
  }, [cards, q, sort, kind])

  // 卡片列数随容器宽度自适应(瀑布流用)
  useEffect(() => {
    const el = gridRef.current
    if (!el) return
    const calc = () => setCols(Math.max(1, Math.min(4, Math.floor((el.clientWidth + 14) / (322 + 14)))))
    calc()
    const ro = new ResizeObserver(calc)
    ro.observe(el)
    return () => ro.disconnect()
  }, [cards])

  if (err) return <div className="view"><Empty icon={<IconNetwork />} title="还没有人脉卡" sub="把微信聊天导入,第二大脑会替你把每个人整理成一张活档案" /></div>
  if (cards === null) return <div className="view"><Thinking phases={['正在读懂你和每个人的聊天…', '提炼关键事实与未了结的事…', '整理人情账本…']} hint="第二大脑在为你的人脉建档,稍等" /></div>
  if (!cards.length) return <div className="view"><Empty icon={<IconNetwork />} title="还没有人脉卡" sub="去「入库」导入微信聊天记录,这里就会长出你的人脉档案" /></div>

  return (
    <div className="view rel-view">
      <div className="view-head rel-vhead">
        <div>
          <h1>人脉</h1>
          <p>替你记住每个人、每件没了结的事、谁欠谁人情 —— {cards.length} 个人 · {totalLoops} 件事等你了结 · {totalFavors} 笔人情。</p>
        </div>
        <button className={'rel-refresh' + (refreshing ? ' spin' : '')} onClick={() => load(true)} disabled={refreshing} title="重新分析">{refreshing ? '分析中…' : '重新分析'}</button>
      </div>

      {/* 未了结汇总 —— 默认近一个月,可查看全部,可逐条删除(不打算做的) */}
      {allLoops.length > 0 && (() => {
        const shown = showAllLoops ? allLoops : recentLoops
        return (
        <div className="rel-todo glass">
          <div className="rel-todo-head">
            <span className="rel-todo-hl"><span className="rel-todo-dot" />等你了结的事 · {showAllLoops ? `全部 ${allLoops.length} 件` : `近一个月 ${recentLoops.length} 件`}</span>
            {allLoops.length > recentLoops.length && (
              <button className="rel-todo-toggle" onClick={() => setShowAllLoops((v) => !v)}>
                {showAllLoops ? '只看近一个月' : `查看全部 ${allLoops.length} 件`}
              </button>
            )}
          </div>
          <div className="rel-todo-list">
            {shown.length === 0 && <div className="rel-todo-empty">近一个月没有待了结的事</div>}
            {shown.map((l) => (
              <div key={l.key} className="rel-todo-item" onClick={() => l.doc_id != null && onOpen && onOpen(l.doc_id)}>
                <span className="rel-todo-who" title={l.contact}>{l.contact}</span>
                <span className="rel-todo-txt">{l.text}</span>
                <button className="rel-todo-del" title="删除(不打算做,只隐藏不删聊天)"
                  onClick={(e) => { e.stopPropagation(); dismissLoop(l) }}>✕</button>
              </div>
            ))}
          </div>
        </div>
        )
      })()}

      {/* 该联系了 —— 主动:很久没联系的人 */}
      {toReach.length > 0 && (
        <div className="rel-reach glass">
          <div className="rel-reach-head"><span className="rel-reach-dot" />该联系了 —— 有阵子没聊了</div>
          <div className="rel-reach-list">
            {toReach.map((c, i) => (
              <div key={i} className="rel-reach-item" onClick={() => onAsk && onAsk('我和' + c.contact + '有阵子没联系了,回顾下我们上次聊到哪、有什么该跟进的,帮我想个开场白')}>
                <span className="rel-reach-name">{c.contact}</span>
                <span className="rel-reach-days">{c.days_ago} 天没联系</span>
                <button className="rel-reach-del" title="不用提醒联系TA(卡片和聊天都保留)"
                  onClick={(e) => { e.stopPropagation(); dismissReach(c.contact) }}>✕</button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 智能分析入口 —— 覆盖 找线索/找人/跨时间/找关联/分析/总结 */}
      {onAsk && (
        <div className="rel-intel">
          <div className="rel-intel-head"><span className="rel-intel-dot" />问第二大脑 · 一点即分析</div>
          <div className="rel-intel-chips">
            {[
              ['找线索', '我答应过谁什么、还没做的?一条条列清楚,注明是和谁、大概什么时候的'],
              ['人情账本', '谁帮过我、我欠谁人情、谁欠我?分"我欠的/欠我的"两栏列出来'],
              ['找人', '我微信里认识哪些做银行同业/存单/资产业务的人?各自是谁、什么机构'],
              ['跨时间', '过去几个月我主要在忙什么?按时间线把我聊天里的大事讲一遍'],
              ['找关联', '我的微信联系人和我的文档资料、目标卡片有哪些关联?串起来看'],
              ['关系分析', '我最近哪些关系在升温、哪些在变冷?谁我回复得最少、谁最主动找我'],
              ['该联系谁', '有哪些重要的人我很久没联系了、或者有事没回复的?提醒我'],
              ['待办生成', '把我聊天里所有该跟进的事,整理成一份带对象和时间的待办清单'],
            ].map(([lab, q], i) => (
              <button key={i} className="rel-chip" onClick={() => onAsk(q)}>{lab}</button>
            ))}
          </div>
        </div>
      )}

      {/* 人脉关系网 —— 联系人之间的关联 */}
      {graph && graph.edge_count > 0 && (
        <div className="rel-net glass">
          <div className="rel-net-head clickable" onClick={() => setNetOpen((v) => !v)}>
            <span className="rel-net-dot" />人脉关系网 · {graph.contact_count} 人 · {graph.edge_count} 条关联
            <span className="rel-net-chev">{netOpen ? '收起 ▾' : '展开 ▸'}</span>
          </div>

          {netOpen && (<>
          {graph.hubs && graph.hubs.filter((h) => h.degree > 0).length > 0 && (
            <div className="rel-net-hubs">
              <div className="rel-net-sub">人脉枢纽(连接最多圈子的人)</div>
              <div className="rel-hub-row">
                {graph.hubs.filter((h) => h.degree > 0).slice(0, 6).map((h, i) => (
                  <button key={i} className="rel-hub" onClick={() => onAsk && onAsk('我和' + h.name + '的关系是什么?TA把我的哪些联系人/圈子连起来了?')}>
                    <span className="rel-hub-name">{h.name}</span>
                    <span className="rel-hub-deg">连接 {h.degree} 人</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="rel-net-edges">
            <div className="rel-net-sub">最强关联(共享同一公司/人/项目)</div>
            {graph.edges.slice(0, 10).map((e, i) => (
              <div key={i} className="rel-edge">
                <span className="rel-edge-pair"><b>{e.a}</b><span className="rel-edge-link">↔</span><b>{e.b}</b></span>
                <span className="rel-edge-why">共享 {e.shared.join('、')}</span>
                <span className="rel-edge-score">{e.score}</span>
              </div>
            ))}
          </div>

          {/* 关系路径:A 通过谁认识 C */}
          <div className="rel-path">
            <div className="rel-net-sub">找关系路径 —— 我想认识某人,该通过谁</div>
            <div className="rel-path-bar">
              <select value={pathA} onChange={(e) => setPathA(e.target.value)}>
                <option value="">从…</option>
                {(graph.nodes || []).map((n, i) => <option key={i} value={n.name}>{n.name}</option>)}
              </select>
              <span className="rel-path-arrow">→</span>
              <select value={pathB} onChange={(e) => setPathB(e.target.value)}>
                <option value="">到…</option>
                {(graph.nodes || []).map((n, i) => <option key={i} value={n.name}>{n.name}</option>)}
              </select>
              <button className="rel-path-go" onClick={findPath} disabled={!pathA || !pathB}>找路径</button>
            </div>
            {pathRes && !pathRes.loading && (
              pathRes.found ? (
                <div className="rel-path-res">
                  <div className="rel-path-chain">{pathRes.path.map((p, i) => (
                    <span key={i}>{i > 0 && <span className="rel-path-sep">→</span>}<span className="rel-path-node">{p}</span></span>
                  ))}</div>
                  {(pathRes.why || []).map((w, i) => (
                    <div key={i} className="rel-path-why">{w.from} 和 {w.to} 都涉及:{(w.shared || []).join('、') || '共同联系'}</div>
                  ))}
                </div>
              ) : <div className="rel-path-none">这两人之间暂时没有可发现的关联路径</div>
            )}
          </div>
          </>)}
        </div>
      )}

      {/* 搜索 + 排序 */}
      <div className="rel-bar">
        <div className="rel-search">
          <IconSearch />
          <input placeholder="搜人名 / 事情 / 关键词" value={q} onChange={(e) => setQ(e.target.value)} />
          {q && <button className="rel-clear" onClick={() => setQ('')}><IconClose /></button>}
        </div>
        <div className="rel-sorts">
          {[['all', '全部'], ['chat', '对话'], ['group', '群聊']].map(([k, lab]) => (
            <button key={k} className={kind === k ? 'on' : ''} onClick={() => setKind(k)}>{lab}</button>
          ))}
        </div>
        <div className="rel-sorts">
          {[['recent', '最近联系'], ['loops', '未了结优先'], ['msgs', '聊得最多'], ['name', '按名字']].map(([k, lab]) => (
            <button key={k} className={sort === k ? 'on' : ''} onClick={() => setSort(k)}>{lab}</button>
          ))}
        </div>
      </div>

      <div className="rel-grid" ref={gridRef}>
        {Array.from({ length: cols }, (_, ci) => (
          <div key={ci} className="rel-col">
            {view.filter((_, i) => i % cols === ci).map((c) => (
          <div key={c.contact} className={'rel-card glass' + (destroying[c.contact] ? ' destroying' : '')}>
            <button className="rel-del" title="删除卡片(聊天记录保留)" onClick={(e) => { e.stopPropagation(); removeCard(c.contact) }}>×</button>
            <div className="rel-head" onClick={() => c.doc_id != null && onOpen && onOpen(c.doc_id)} title="点击看原始聊天">
              <span className="rel-avatar">{[...(c.contact || '?')][0] || '?'}</span>
              <span className="rel-name">{c.contact}</span>
              {c.deep && <span className="rel-deep-badge" title="已用 pro 深度分析">深度</span>}
              <span className="rel-count">{c.msgcount} 条</span>
            </div>
            {c.identity && <div className="rel-identity">{c.identity}</div>}
            {c.traits && <div className="rel-traits"><span className="rel-traits-l">特点</span>{c.traits}</div>}
            {(c.tags || []).length > 0 && (
              <div className="rel-tags">{c.tags.slice(0, 6).map((t, j) => (
                <span key={j} className="rel-tag" onClick={() => onAsk && onAsk('我认识的人里,和「' + t + '」有关的都有谁?')}>{t}</span>
              ))}</div>
            )}
            {(c.open_loops || []).length > 0 && (
              <div className="rel-block rel-loops">
                <div className="rel-btitle">未了结 · {c.open_loops.length}</div>
                {c.open_loops.slice(0, 3).map((o, j) => <div key={j} className="rel-loop">{o}</div>)}
              </div>
            )}
            {(c.favors || []).length > 0 && (
              <div className="rel-block rel-favors">
                <div className="rel-btitle">人情账本</div>
                {c.favors.slice(0, 3).map((f, j) => <div key={j} className="rel-favor">{f}</div>)}
              </div>
            )}
            {(c.facts || []).length > 0 && (
              <div className="rel-block rel-facts">
                <div className="rel-btitle">关键事实</div>
                {c.facts.slice(0, 3).map((f, j) => <div key={j} className="rel-fact">{f}</div>)}
              </div>
            )}
            <div className="rel-actions">
              <button className="rel-ic pro" title="问TA · 见面简报 / 深度分析 / 产出文档 / 跟进 / 自由提问,都在这里" onClick={() => onAskContact && onAskContact(c.contact, undefined, c.is_group)}>{IC.spark}</button>
              {c.doc_id != null && <button className="rel-ic" title="看原始聊天" onClick={() => onOpen && onOpen(c.doc_id)}>{IC.chat}</button>}
            </div>
          </div>
            ))}
          </div>
        ))}
      </div>

      {reportContact && <ReportPanel contact={reportContact} onClose={() => setReportContact(null)} onAsk={onAsk} />}

      {/* 见面前简报 modal */}
      {brief && (
        <div className="brief-overlay" onClick={() => setBrief(null)}>
          <div className="brief-modal glass" onClick={(e) => e.stopPropagation()}>
            <div className="brief-head">
              <div><span className="brief-title">见面前简报</span><span className="brief-name">{brief.contact}</span></div>
              <button className="brief-close" onClick={() => setBrief(null)}>×</button>
            </div>
            {brief.loading ? <div className="brief-loading">正在为你准备作战情报…</div> : (
              !brief.found ? <div className="brief-loading">还没有这个人的聊天数据</div> : (
                <div className="brief-body">
                  {brief.reliability && brief.reliability.total > 0 && (
                    <div className="brief-rel">
                      <span className="brief-sec-t">履约信用</span>
                      <span className="brief-rel-txt">承诺 {brief.reliability.total} 次 · 兑现 {brief.reliability.kept} 次{brief.reliability.broken > 0 ? ' · 爽约 ' + brief.reliability.broken + ' 次' : ''}{brief.reliability.avg_delay > 0 ? ' · 平均拖 ' + brief.reliability.avg_delay + ' 天' : ''}</span>
                      {(brief.reliability.broken > 0 || brief.reliability.avg_delay > 3) && <span className="brief-rel-warn">报价请留余量</span>}
                    </div>
                  )}
                  {(brief.open_commitments || []).length > 0 && (
                    <div className="brief-sec">
                      <div className="brief-sec-t">未了结(见面要提)</div>
                      {brief.open_commitments.map((c, i) => <div key={i} className="brief-li"><b>{(c.who || '').startsWith('我') ? '我' : 'TA'}</b>：{c.what}{c.due ? ' （' + c.due + '）' : ''}</div>)}
                    </div>
                  )}
                  {(brief.landmines || []).length > 0 && (
                    <div className="brief-sec">
                      <div className="brief-sec-t warn">雷区(别踩)</div>
                      {brief.landmines.map((l, i) => <div key={i} className="brief-li">{l}</div>)}
                    </div>
                  )}
                  {(brief.warm_topics || []).length > 0 && (
                    <div className="brief-sec">
                      <div className="brief-sec-t good">暖场话题</div>
                      {brief.warm_topics.map((t, i) => <div key={i} className="brief-li">{t}</div>)}
                    </div>
                  )}
                  {(brief.key_numbers || []).length > 0 && (
                    <div className="brief-sec">
                      <div className="brief-sec-t">关键数字</div>
                      {brief.key_numbers.map((n, i) => <div key={i} className="brief-li"><b>{n.item}</b> {n.value}{n.date ? ' （' + n.date + '）' : ''}</div>)}
                    </div>
                  )}
                  {!(brief.reliability && brief.reliability.total > 0) && !(brief.open_commitments || []).length && !(brief.landmines || []).length && !(brief.warm_topics || []).length && !(brief.key_numbers || []).length && (
                    <div className="brief-empty">你和 TA 的聊天还太浅,还没沉淀出承诺、雷区、暖场话题或关键数字 —— 多聊几次、把往来做实,这份见面情报就会长出来。也可以点下面让第二大脑基于现有信息先帮你聊一层。</div>
                  )}
                  {onAsk && <button className="brief-ask" onClick={() => { onAsk('我马上要见' + brief.contact + ',给我一份完整的见面准备:我们的关系、他的性格、这次该聊什么、要注意什么'); setBrief(null) }}>让第二大脑再帮我深聊一层</button>}
                </div>
              )
            )}
          </div>
        </div>
      )}
    </div>
  )
}
