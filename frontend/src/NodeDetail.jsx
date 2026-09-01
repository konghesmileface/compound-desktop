import React, { useState, useEffect } from 'react'
import { api, openExternal } from './api'
import { IconClose } from './icons'
import { Thinking } from './ui'

const EXT = {
  '.pdf': ['PDF', '#ef4444'], '.epub': ['电子书', '#a855f7'], '.mobi': ['电子书', '#a855f7'],
  '.fb2': ['电子书', '#a855f7'], '.docx': ['Word', '#3b82f6'], '.pptx': ['PPT', '#f97316'],
  '.xlsx': ['Excel', '#22c55e'], '.md': ['笔记', '#94a3b8'], '.txt': ['文本', '#94a3b8'],
  '.html': ['网页', '#38bdf8'], '.csv': ['数据', '#a3e635'], '.eml': ['邮件', '#f0abfc'],
}
const badge = (fn) => { const f = (fn || '').toLowerCase(); return EXT[f.slice(f.lastIndexOf('.'))] || ['文件', '#94a3b8'] }
const extOf = (f) => (f === 'word' ? 'docx' : f === 'excel' ? 'xlsx' : 'pptx')

// 微信聊天节点的高质量弹框内容:直接呈现已生成的关系卡 + 情报(不是通用文档摘要)
function renderChatCard(chat, d) {
  const c = chat.card || {}
  const it = chat.intel || {}
  const arr = (x) => (Array.isArray(x) ? x.filter((v) => v && (typeof v !== 'string' || v.trim())) : [])
  const facts = arr(c.facts), loops = arr(c.open_loops), favors = arr(c.favors)
  const commits = arr(it.commitments), nums = arr(it.numbers), mines = arr(it.landmines), warm = arr(it.warm_topics)
  const nothing = !c.identity && !c.summary && !facts.length && !loops.length && !favors.length && !commits.length && !nums.length && !mines.length && !warm.length
  if (nothing) {
    return chat.card === null && chat.intel === null
      ? <div className="nd-dim" style={{ marginTop: 14 }}>这位联系人的关系卡还在后台生成,稍后回来看。</div>
      : null
  }
  const Sec = ({ t, children }) => <><div className="nd-h">{t}</div>{children}</>
  return (
    <div className="cc">
      {(chat.tags || []).length > 0 && <div className="nd-topics" style={{ marginTop: 12 }}>{chat.tags.map((t, i) => <span key={i} className="nd-chip">{t}</span>)}</div>}
      {(c.identity || c.summary) && <Sec t="是谁 · 什么关系">
        {c.identity && <div className="nd-summary">{c.identity}</div>}
        {c.summary && c.summary !== c.identity && <div className="cc-note">{c.summary}</div>}
      </Sec>}
      {c.traits && <Sec t="这个人的特点"><div className="nd-summary">{c.traits}</div></Sec>}
      {(loops.length > 0 || commits.length > 0) && <Sec t="未了结 · 待办">
        <ul className="cc-list">
          {commits.map((x, i) => <li key={'c' + i}><b>{x.who === '我' || (x.who || '').startsWith('我') ? '我答应' : 'TA答应'}</b>{x.what}{x.due ? ` · ${x.due}` : ''}</li>)}
          {loops.map((x, i) => <li key={'l' + i}>{x}</li>)}
        </ul>
      </Sec>}
      {facts.length > 0 && <Sec t="关键事实"><ul className="cc-list">{facts.map((x, i) => <li key={i}>{x}</li>)}</ul></Sec>}
      {nums.length > 0 && <Sec t="关键数字"><ul className="cc-list">{nums.map((x, i) => <li key={i}><b>{x.item}</b>{x.value}{x.date ? ` · ${x.date}` : ''}</li>)}</ul></Sec>}
      {favors.length > 0 && <Sec t="人情账"><ul className="cc-list">{favors.map((x, i) => <li key={i}>{x}</li>)}</ul></Sec>}
      {mines.length > 0 && <Sec t="雷区 · 别踩"><ul className="cc-list cc-warn">{mines.map((x, i) => <li key={i}>{x}</li>)}</ul></Sec>}
      {warm.length > 0 && <Sec t="暖场话题"><div className="cc-tags">{warm.map((x, i) => <span key={i} className="cc-tag">{x}</span>)}</div></Sec>}
      {c.dynamics && <Sec t="关系近况"><div className="cc-note">{c.dynamics}</div></Sec>}
    </div>
  )
}

export default function NodeDetail({ docId, onClose, onOpenReader, onOpenNode }) {
  const [d, setD] = useState(null)      // { filename, pages, summary, topics }
  const [sim, setSim] = useState([])
  const [gen, setGen] = useState(null)  // { busy } | file
  const [conn, setConn] = useState(null) // { connections, spark } | 'loading'
  const [chat, setChat] = useState(null) // 微信聊天节点:关系卡 + 情报

  useEffect(() => {
    if (docId == null) return
    let alive = true
    setD(null); setSim([]); setGen(null); setConn('loading'); setChat(null)
    api.docSummary(docId).then((r) => alive && setD(r)).catch(() => alive && setD({ error: true }))
    api.similar(docId).then((r) => alive && setSim(r.similar || [])).catch(() => {})
    api.connections(docId).then((r) => alive && setConn(r)).catch(() => alive && setConn({ error: true }))
    api.chatNode(docId).then((r) => alive && setChat(r)).catch(() => {})
    return () => { alive = false }
  }, [docId])

  const isChat = chat && chat.is_chat

  if (docId == null) return null
  const [label, color] = badge(d && d.filename)

  async function makeGen(fmt) {
    if (gen && gen.busy) return
    setGen({ busy: true, fmt })
    try { const r = await api.generate('《' + (d.filename || '文档') + '》要点概要', fmt, 'deep'); setGen({ ...r, fmt }) }
    catch { setGen({ error: true }) }
  }

  return (
    <div className="nd-overlay" onClick={onClose}>
      <div className="nd-panel glass" onClick={(e) => e.stopPropagation()}>
        <div className="nd-x" onClick={onClose}><IconClose /></div>
        <span className="nd-badge" style={{ background: isChat ? '#22c55e' : color }}>{isChat ? '联系人' : label}</span>
        <h2 className="nd-title">{isChat ? chat.contact : ((d && d.filename) || '读取文档…')}</h2>
        {isChat
          ? <div className="nd-sub">{chat.last_date ? '最近联系 ' + chat.last_date : '微信聊天'}{d && d.pages != null ? ' · ' + d.pages + ' 页' : ''}</div>
          : (d && d.pages != null && <div className="nd-sub">{d.pages} 页</div>)}

        {isChat && renderChatCard(chat, d)}

        {!isChat && (<>
          <div className="nd-h">这份文档讲什么</div>
          {!d ? <div className="nd-loading"><span className="thinking-dots mini"><i /><i /><i /></span>AI 正在读它…</div>
            : d.error ? <div className="nd-dim">摘要暂不可用(可到设置检查模型)</div>
              : <div className="nd-summary">{d.summary}</div>}
          {d && d.topics && d.topics.length > 0 && (
            <div className="nd-topics">{d.topics.map((t, i) => <span key={i} className="nd-chip">{t}</span>)}</div>
          )}
        </>)}

        {/* 主动发现连接 —— 第二大脑的杀手锏 */}
        <div className="nd-h nd-h-star">✦ 第二大脑发现的连接</div>
        {conn === 'loading' ? <Thinking text="正在全库翻找你可能忘了的跨界关联…" hint="深度分析,约需半分钟" />
          : !conn || conn.error ? <div className="nd-dim">暂时连不出关联</div>
            : (<>
              {(conn.connections || []).length === 0 && !conn.spark ? <div className="nd-dim">还没找到能连起来的其它文档,多喂点东西给它。</div> : null}
              {(conn.connections || []).map((c, i) => (
                <div key={i} className="nd-conn" onClick={() => onOpenNode(c.doc_id)}>
                  <div className="nd-conn-insight">{c.insight}</div>
                  <div className="nd-conn-fn">↳ 《{c.filename}》</div>
                </div>
              ))}
              {conn.spark && <div className="nd-spark"><span className="nd-spark-i">灵感</span>{conn.spark}</div>}
            </>)}

        {sim.length > 0 && (<>
          <div className="nd-h">相关文档</div>
          <div className="nd-rel">{sim.slice(0, 6).map((s, i) => (
            <div key={i} className="nd-rel-item" onClick={() => onOpenNode(s.doc_id)}>
              <span className="nd-rel-fn">{s.filename}</span>
              <span className="nd-rel-sc num">{(s.score * 100).toFixed(0)}%</span>
            </div>))}
          </div>
        </>)}

        <div className="nd-actions">
          <button className="btn btn-primary" onClick={() => onOpenReader(docId)}>打开阅读</button>
        </div>
        <div className="nd-gen-h">基于它一键生成</div>
        <div className="nd-gen-row">
          {[['ppt', 'PPT'], ['word', 'Word'], ['excel', 'Excel']].map(([f, lbl]) => (
            <button key={f} className="btn nd-gen-btn" disabled={gen && gen.busy} onClick={() => makeGen(f)}>
              {gen && gen.busy && gen.fmt === f ? '深度撰写中…' : lbl}
            </button>
          ))}
        </div>
        {gen && gen.busy && (
          <div className="nd-gen-hint"><span className="spinner spinner-xs" /> 正在用深度模型通读资料、逐页撰写,约 1–2 分钟,请稍候…</div>
        )}
        {gen && gen.file && <button type="button" className="gen-dl" style={{ marginTop: 12 }} onClick={() => openExternal(gen.url)}>⬇ 下载《{gen.title}》.{extOf(gen.fmt || gen.format)}</button>}
        {gen && gen.error && <div className="nd-dim" style={{ marginTop: 10 }}>生成失败,请到设置检查模型/key</div>}
      </div>
    </div>
  )
}
