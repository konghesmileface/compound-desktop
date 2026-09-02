import React, { useState, useEffect, useRef } from 'react'
import { api } from './api'
import { Thinking } from './ui'
import { IconClose } from './icons'
import GroupGraph from './GroupGraph'
import RelationTimeline from './RelationTimeline'

// 轻量 markdown 渲染:**加粗** / 标题 / 列表 / `代码` / 【来源N】角标
function renderInline(text, ki, sources, onOpenDoc) {
  const nodes = []
  const re = /(\*\*(.+?)\*\*|【来源(\d+)】|`([^`]+)`)/g
  let last = 0, m, idx = 0
  while ((m = re.exec(text))) {
    if (m.index > last) nodes.push(text.slice(last, m.index))
    if (m[2] != null) nodes.push(<b key={ki + '-' + idx}>{m[2]}</b>)
    else if (m[3] != null) { /* 【来源N】内联角标去掉:常指向不到、点了没反应,底部"看聊天"已给出处 */ }
    else if (m[4] != null) nodes.push(<code key={ki + '-' + idx} className="md-code">{m[4]}</code>)
    last = m.index + m[0].length; idx++
  }
  if (last < text.length) nodes.push(text.slice(last))
  return nodes
}
export function renderRich(text, sources, onOpenDoc) {
  // 预处理:整行 --- 变分隔线标记
  text = String(text || '').replace(/^\s*-{3,}\s*$/gm, '―HR―')
  const lines = String(text || '').split('\n')
  const out = []
  let list = []
  const flush = () => { if (list.length) { out.push(<ul key={'ul' + out.length} className="md-ul">{list}</ul>); list = [] } }
  const isRow = (s) => /^\s*\|.*\|\s*$/.test(s)
  const isSep = (s) => /^[\s|:\-]+$/.test(s) && s.includes('-') && s.includes('|')
  const cells = (s) => s.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim())
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].replace(/\s+$/, '')
    // markdown 表格:当前行 |...| 且下一行是 |---|---| 分隔
    if (isRow(line) && i + 1 < lines.length && isSep(lines[i + 1])) {
      flush()
      const header = cells(line)
      const rows = []
      let j = i + 2
      while (j < lines.length && isRow(lines[j]) && !isSep(lines[j])) { rows.push(cells(lines[j])); j++ }
      out.push(
        <div key={'tw' + i} className="md-table-wrap"><table className="md-table">
          <thead><tr>{header.map((h, hi) => <th key={hi}>{renderInline(h, 't' + i + 'h' + hi, sources, onOpenDoc)}</th>)}</tr></thead>
          <tbody>{rows.map((r, ri) => <tr key={ri}>{header.map((_, ci) => <td key={ci}>{renderInline(r[ci] || '', 't' + i + 'r' + ri + 'c' + ci, sources, onOpenDoc)}</td>)}</tr>)}</tbody>
        </table></div>
      )
      i = j - 1
      continue
    }
    if (!line.trim()) { flush(); continue }
    const h = line.match(/^(#{1,4})\s+(.*)/)
    const b = line.match(/^\s*[-•*]\s+(.*)/)
    const n = line.match(/^\s*(\d+)[.、]\s+(.*)/)
    if (h) { flush(); out.push(<div key={i} className="md-h">{renderInline(h[2], i, sources, onOpenDoc)}</div>) }
    else if (b) { list.push(<li key={i}>{renderInline(b[1], i, sources, onOpenDoc)}</li>) }
    else if (n) { list.push(<li key={i}><span className="md-num">{n[1]}.</span> {renderInline(n[2], i, sources, onOpenDoc)}</li>) }
    else if (line.trim() === '―HR―') { flush(); out.push(<div key={i} className="md-hr" />) }
    else if (/^>\s?/.test(line)) { flush(); out.push(<div key={i} className="md-quote">{renderInline(line.replace(/^>\s?/, ''), i, sources, onOpenDoc)}</div>) }
    else { flush(); out.push(<p key={i} className="md-p">{renderInline(line, i, sources, onOpenDoc)}</p>) }
  }
  flush()
  return out
}

// 就地问答抽屉 + 联系人分析中枢:传 contact 时顶部出快捷(见面简报/深度分析/产出文档),输出都在对话里可见
export default function AskDrawer({ query, contact, initialAction, isGroup, onClose, onOpenDoc }) {
  const [turns, setTurns] = useState([])   // [{q, answer, sources, loading}]
  const [input, setInput] = useState('')
  const [docMenu, setDocMenu] = useState(false)   // 产出文档二级菜单
  const bodyRef = useRef(null)
  const inputRef = useRef(null)
  // 群聊给专属分析(成员画像/熟络度);显式 isGroup 优先,否则按名字兜底
  const isGrp = isGroup != null ? !!isGroup : (/(@chatroom|@openim)$/.test(contact || '') || /群/.test(contact || ''))

  const QUICK = !contact ? [] : (isGrp ? [
    ['群成员画像', `这是群聊「${contact}」。分析群里活跃的主要成员:每个人是谁、什么身份/角色、性格与说话风格。基于聊天原文,逐人列清单。`],
    ['成员熟络度·关系图', '__GROUP_GRAPH__'],
    ['群在聊什么', `群聊「${contact}」主要在聊什么?核心话题、达成的事、活跃时段、群的性质(工作/兴趣/…)。带日期。`],
    ['产出文档', '__DOC_MENU__'],
  ] : [
    ['见面简报', `给我一份和「${contact}」的**见面前简报**:他是谁、我们上次聊到哪、我答应过他什么/他答应过我什么、他的偏好和雷区、还有哪些悬而未决的事。基于聊天、带日期。`],
    ['深度分析', `**深度分析**我和「${contact}」这段关系:现在处于什么阶段、对方最在意什么、他靠不靠谱(承诺兑现情况)、我下一步最该做什么。要具体、基于聊天原文。`],
    ['关系走势·时间线', '__TIMELINE__'],
    ['产出文档', '__DOC_MENU__'],
    ['还有什么要跟进', `我和「${contact}」的聊天里,还有什么答应了没做、对方在等我回、或该跟进的?列出来。`],
  ])

  // 产出文档:按角色/目的产出不同类型;群聊和 1:1 各一套
  const DOC_TYPES = !contact ? [] : (isGrp ? [
    ['群成员性格分析', `针对群聊「${contact}」,为每位活跃成员做一份性格与沟通画像:性格、说话风格、在群里的角色、和其他人的关系。逐人写,基于聊天原文举证。`],
    ['成员关系熟络度', `为群聊「${contact}」做一份成员关系分析:两两之间的熟络程度、互动频率、谁和谁抱团、群里的核心人物与边缘人物、我和每个人的关系亲疏。用表格呈现熟络度(如高/中/低)。`],
    ['关键人物盘点', `盘点群聊「${contact}」里的关键人物:谁是核心/组织者、谁是意见领袖、谁是资源方、谁最活跃、谁值得重点维护。逐人一句说清角色和价值,基于聊天原文。`],
    ['群纪要', `整理群聊「${contact}」的纪要:按时间列出讨论的关键事项、决定、待办、重要信息。分节带日期。`],
    ['活动/事件梳理', `梳理群聊「${contact}」里提到的活动/事件:时间、内容、参与情况、结果。用列表或表格。`],
    ['群氛围与话题', `分析群聊「${contact}」的氛围与话题:这是个什么性质的群、聊得最多的话题、活跃时段、群文化/调性、以及它对我的价值。`],
    ['群里的机会', `从群聊「${contact}」里挖掘对我有用的机会:可对接的资源/人脉、潜在的合作或业务、值得跟进的线索。基于聊天原文,别硬凑。`],
    ['自定义…', null],
  ] : [
    ['往来纪要', `基于我和「${contact}」的全部聊天,整理一份**往来纪要**:按时间脉络列出聊过的关键事项、达成的共识、涉及的数字/报价/额度、各自的待办。分节、带日期,可用表格。`],
    ['关系分析', `基于我和「${contact}」的聊天,写一份**关系分析**报告:这段关系的性质与阶段、互动频率与走势、他对我的价值、我对他的价值、风险点、经营建议。基于聊天原文举证、带日期。`],
    ['性格分析', `基于我和「${contact}」的聊天,做一份**性格与沟通画像**:他的性格特点、沟通风格、决策方式、在意什么、雷区/禁忌、以及和他打交道的实操建议。每个判断从聊天原文举证。`],
    ['营销/攻单', `基于我和「${contact}」的聊天,做一份**营销/攻单文档**:他的需求与痛点、他在采购/决策里的角色、我能提供的价值点、他可能的异议及应对话术、下一步推进动作。基于聊天原文。`],
    ['谈判要点', `基于我和「${contact}」的聊天,列一份**谈判要点**:双方诉求、我的筹码与底线、对方可能的立场、可让步项与不可让步项、开场与推进策略。基于聊天原文。`],
    ['周报', `基于我和「${contact}」近期的聊天,帮我写一段可放进**周报**的内容:本周和TA的进展、达成/推进的事、待跟进项、需要的支持。简洁、条理清楚。`],
    ['自定义…', null],
  ])

  // prompt=发给LLM的完整指令;label=展示给用户的干净问题(快捷键用简短标签,别把带 ** 的长指令原样回显)
  const run = (prompt, label) => {
    if (!prompt || !prompt.trim()) return
    const idx = turns.length
    const q = label || prompt
    setTurns((t) => [...t, { q, prompt, loading: true }])
    const history = turns.flatMap((t) => t.answer ? [{ role: 'user', content: t.prompt || t.q }, { role: 'assistant', content: t.answer }] : [])
    api.ask(prompt, history, contact || '').then((r) => {   // ★带 contact:后端锁定到该群/联系人的聊天+关系卡检索,自由提问不再"不知道哪个群"
      setTurns((t) => t.map((x, i) => i === idx ? { ...x, loading: false, answer: r.answer || '', sources: r.sources || [] } : x))
    }).catch((e) => { const msg = String(e && e.message || ''); setTurns((t) => t.map((x, i) => i === idx ? { ...x, loading: false, answer: (msg.length > 8 ? msg : '出错了,换句话再试试') } : x)) })
  }

  // 群成员关系图:内联在对话流里渲染一张关系网(数据来自 LLM 对真实群聊的分析)
  const runGraph = () => {
    const idx = turns.length
    setTurns((t) => [...t, { q: '成员熟络度 · 关系图', kind: 'graph', loading: true }])
    api.groupGraph(contact).then((r) => {
      setTurns((t) => t.map((x, i) => i === idx ? { ...x, loading: false, graph: r } : x))
    }).catch(() => setTurns((t) => t.map((x, i) => i === idx ? { ...x, loading: false, graph: { found: false } } : x)))
  }
  // 关系随时间变化:内联时间线(月度互动强度 + 关键节点 + 走势)
  const runTimeline = () => {
    const idx = turns.length
    setTurns((t) => [...t, { q: '关系走势 · 时间线', kind: 'timeline', loading: true }])
    api.relationTimeline(contact).then((r) => {
      setTurns((t) => t.map((x, i) => i === idx ? { ...x, loading: false, timeline: r } : x))
    }).catch(() => setTurns((t) => t.map((x, i) => i === idx ? { ...x, loading: false, timeline: { found: false } } : x)))
  }

  useEffect(() => {
    setTurns([]); setDocMenu(false)
    if (query) { run(query); return }
    if (initialAction === '产出文档') { setDocMenu(true); return }   // 从聊天页点"产出文档"→直接展开选类型
    if (initialAction) {   // "深度分析"/"成员熟络度"等直接打开就自动跑,和抽屉里点 chip 完全一致
      const hit = QUICK.find(([label]) => label === initialAction || label.startsWith(initialAction))
      if (hit) {
        if (hit[1] === '__GROUP_GRAPH__') runGraph()
        else if (hit[1] === '__TIMELINE__') runTimeline()
        else if (hit[1] === '__DOC_MENU__') setDocMenu(true)
        else run(hit[1], hit[0])
      }
    }
    /* eslint-disable-next-line */
  }, [query, initialAction, contact])
  useEffect(() => { if (bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight }, [turns])

  return (
    <div className="drawer glass ask-drawer">
      <div className="x" onClick={onClose}><IconClose /></div>
      <div className="ask-dhead">第二大脑{contact ? <span className="ask-dhead-c">· {isGrp ? '群' : '与'} {contact}</span> : ''}</div>
      {QUICK.length > 0 && (
        <div className="ask-quick">
          {QUICK.map(([label, q], i) => (
            <button key={i} className={'ask-quick-btn' + (q === '__DOC_MENU__' && docMenu ? ' on' : '')}
              onClick={() => q === '__DOC_MENU__' ? setDocMenu((v) => !v) : (q === '__GROUP_GRAPH__' ? runGraph() : (q === '__TIMELINE__' ? runTimeline() : run(q, label)))}>
              {label}{q === '__DOC_MENU__' ? (docMenu ? ' ▴' : ' ▾') : ''}
            </button>
          ))}
        </div>
      )}
      {docMenu && DOC_TYPES.length > 0 && (
        <div className="ask-docmenu">
          <div className="ask-docmenu-t">想产出哪种文档?选一个,或点「自定义」自己说</div>
          <div className="ask-docmenu-chips">
            {DOC_TYPES.map(([label, q], i) => (
              <button key={i} className={'ask-doc-btn' + (q ? '' : ' custom')} onClick={() => {
                setDocMenu(false)
                if (q) run(q, '产出文档 · ' + label)
                else { setInput(`基于我和「${contact}」的聊天,帮我产出一份:`); if (inputRef.current) inputRef.current.focus() }
              }}>{label}</button>
            ))}
          </div>
        </div>
      )}
      <div className="ask-dbody" ref={bodyRef}>
        {turns.map((t, i) => (
          <div key={i} className="ask-turn">
            <div className="ask-q">{String(t.q || '').replace(/\*\*/g, '').replace(/^#{1,4}\s*/gm, '')}</div>
            {t.loading ? <Thinking phases={t.kind === 'graph' ? ['通读群里的真实互动…', '判断谁和谁熟…', '画成关系图…'] : (t.kind === 'timeline' ? ['数每个月的互动…', '找出关键转折…', '画成时间线…'] : ['在你的记忆里检索…', '读懂相关的人和事…', '组织答案…'])} hint="第二大脑在现读资料、现写答案 —— 简单问题几秒,复杂问题(要通读并列成表)约 30 秒~1 分钟,请稍候" /> : (
              t.kind === 'graph' ? <GroupGraph data={t.graph} /> : t.kind === 'timeline' ? <RelationTimeline data={t.timeline} onOpen={onOpenDoc} /> : (
              <div className="ask-a">
                <div className="ask-a-text">{renderRich(t.answer, t.sources, onOpenDoc)}</div>
                {(t.sources || []).filter((s) => s.doc_id != null).length > 0 && (
                  <div className="ask-src">
                    {(t.sources || []).filter((s) => s.doc_id != null).slice(0, 6).map((s, j) => (
                      <button key={j} className="ask-src-chip" onClick={() => onOpenDoc && onOpenDoc({ id: s.doc_id, page: s.page_no || 0 })} title={s.filename}>
                        {(s.filename || '').replace('微信_与', '').replace('.txt', '').replace('人脉档案·', '')}
                      </button>
                    ))}
                  </div>
                )}
              </div>
              )
            )}
          </div>
        ))}
      </div>
      <div className="ask-dinput">
        <input ref={inputRef} placeholder={contact ? '继续追问,或直接说你想要什么文档…' : '继续追问…'} value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && input.trim()) { run(input); setInput('') } }} />
        <button onClick={() => { if (input.trim()) { run(input); setInput('') } }} disabled={!input.trim()}>问</button>
      </div>
    </div>
  )
}
