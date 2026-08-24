import React, { useEffect, useState, useCallback } from 'react'
import { api } from './api'
import { IconClose } from './icons'
import { Thinking } from './ui'
import ReportPanel from './ReportPanel'

const PAGE = 40

// 微信聊天:把 [时间] 谁: 内容 解析成消息,渲染成对话气泡
const WX_LINE = /^\[(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})(?::\d{2})?\]\s*([^:：]{1,24}?)[:：]\s*([\s\S]*)$/
function parseWx(pages) {
  const text = pages.map((p) => p.text || '').join('\n')
  const msgs = []
  let cur = null
  for (const raw of text.split('\n')) {
    const line = raw.replace(/\r$/, '')
    const m = line.match(WX_LINE)
    if (m) {
      if (cur) msgs.push(cur)
      const sender = m[3].trim()
      cur = { day: m[1], time: m[2], sender, isMe: sender === '我', content: m[4] }
    } else if (cur && line.trim()) {
      cur.content += '\n' + line
    }
  }
  if (cur) msgs.push(cur)
  return msgs
}
const PLACEHOLDER = /^\s*\[(图片|表情|视频|语音|文件|链接|位置|转账|红包|动画表情|链接\/文件)\]\s*$/
const IMG_URL = /(https?:\/\/[^\s]+\.(?:jpg|jpeg|png|gif|webp)(?:\?[^\s]*)?)/i
// 占位符类型 → 图标(内联SVG, 无emoji)+ 标签
const PH_ICONS = {
  图片: <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="18" height="18" rx="2" /><circle cx="8.5" cy="8.5" r="1.5" /><path d="M21 15l-5-5L5 21" /></svg>,
  语音: <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2"><rect x="9" y="2" width="6" height="12" rx="3" /><path d="M5 10a7 7 0 0 0 14 0M12 17v4" /></svg>,
  视频: <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2"><rect x="2" y="5" width="14" height="14" rx="2" /><path d="M22 8l-6 4 6 4V8z" /></svg>,
  文件: <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><path d="M14 2v6h6" /></svg>,
  表情: <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10" /><path d="M8 14s1.5 2 4 2 4-2 4-2M9 9h.01M15 9h.01" /></svg>,
}
function phIcon(type) {
  return PH_ICONS[type] || PH_ICONS[({ 动画表情: '表情', 视频: '视频', 语音: '语音', 文件: '文件', 图片: '图片' })[type]] || null
}
function renderBubble(content) {
  const c = (content || '').trim()
  const im = c.match(IMG_URL)   // 新版工具会带图片URL → 直接显示图
  if (im && c.length < 400) return <img className="wx-img" src={im[1]} alt="图片" loading="lazy" />
  const pm = c.match(/^\[([^\]]+)\]$/)
  if (pm) {
    const ic = phIcon(pm[1])
    if (ic) return <span className="wx-ph-chip">{ic}<span>{pm[1]}</span></span>
  }
  return content
}
function ChatView({ msgs }) {
  if (!msgs || !msgs.length) return <div className="empty" style={{ padding: 40 }}><div className="spinner" /></div>
  let lastDay = null
  return (
    <div className="wx-chat">
      {msgs.map((m, i) => {
        const showDay = m.day !== lastDay
        lastDay = m.day
        const ph = PLACEHOLDER.test(m.content)
        return (
          <React.Fragment key={i}>
            {showDay && <div className="wx-day"><span>{m.day}</span></div>}
            <div className={'wx-msg' + (m.isMe ? ' me' : '')}>
              {!m.isMe && <div className="wx-sender">{m.sender}</div>}
              <div className="wx-row">
                <div className={'wx-bubble' + (ph ? ' ph' : '')}>{renderBubble(m.content)}</div>
                <div className="wx-time">{m.time}</div>
              </div>
            </div>
          </React.Fragment>
        )
      })}
    </div>
  )
}

export default function Reader({ docId, targetPage, onClose, onOpen, onAsk, onAskContact }) {
  const [meta, setMeta] = useState(null)
  const [pages, setPages] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [similar, setSimilar] = useState([])
  const [showSim, setShowSim] = useState(false)
  const [ms, setMs] = useState(null)
  const [msLoad, setMsLoad] = useState(false)
  const [hl, setHl] = useState(0)   // #1 高亮的来源页
  const [wxMsgs, setWxMsgs] = useState(null)   // 微信消息(按时间倒序)
  const [wxTotal, setWxTotal] = useState(0)
  const [wxLoading, setWxLoading] = useState(false)
  const [reportOpen, setReportOpen] = useState(false)

  const isWx = !!(meta && /^微信_与/.test(meta.filename || ''))
  // PDF/EPUB 原始提取常是"一词一行"(目录页尤甚),重排成流式段落:空行仍分段,段内换行并成一行
  const bookish = !!(meta && /\.(pdf|epub)$/i.test(meta.filename || ''))
  const reflow = (t) => String(t || '').split(/\n{2,}/).map((par) =>
    par.replace(/\s*\n\s*/g, '\u0001').replace(/([\u4e00-\u9fff])\u0001(?=[\u4e00-\u9fff])/g, '$1').replace(/\u0001/g, ' ')
  ).join('\n\n')
  const contact = isWx ? String(meta.filename).replace('微信_与', '').replace('.txt', '') : null
  const isGrpChat = !!contact && (/(@chatroom|@openim)$/.test(contact) || /群/.test(contact))

  // 微信聊天:用按时间排序的端点(最近在最上),治页存储顺序不统一
  useEffect(() => {
    if (!isWx || !contact) return
    setWxLoading(true)
    api.wechatMessages(contact, 0, 300).then((r) => { setWxMsgs(r.messages || []); setWxTotal(r.total || 0) })
      .catch(() => setWxMsgs([])).finally(() => setWxLoading(false))
  }, [isWx, contact])
  const loadEarlier = () => {
    if (!contact) return
    setWxLoading(true)
    api.wechatMessages(contact, (wxMsgs || []).length, 300)
      .then((r) => setWxMsgs((prev) => [...(prev || []), ...(r.messages || [])]))
      .catch(() => {}).finally(() => setWxLoading(false))
  }

  const loadPage = useCallback(async (docId, offset) => {
    setLoading(true)
    try {
      const d = await api.doc(docId, offset, PAGE)
      setMeta({ filename: d.filename, pages: d.pages, backend: d.backend, ingested_at: d.ingested_at })
      setTotal(d.total_pages || d.pages || 0)
      setPages((prev) => (offset === 0 ? d.content : [...prev, ...d.content]))
    } catch { /* noop */ }
    setLoading(false)
  }, [])

  useEffect(() => {
    setMeta(null); setPages([]); setSimilar([]); setShowSim(false); setMs(null)
    setWxMsgs(null); setWxTotal(0); setReportOpen(false)
    loadPage(docId, 0)
    api.similar(docId).then((r) => setSimilar(r.similar || [])).catch(() => {})
  }, [docId, loadPage])

  // 音视频文档:加载 AI 结构化纪要(章节/待办/脑图,#6)
  useEffect(() => {
    if (meta && (meta.backend || '').startsWith('asr:')) {
      setMsLoad(true)
      api.mediaStructure(docId).then((r) => setMs(r)).catch(() => { }).finally(() => setMsLoad(false))
    }
  }, [meta, docId])

  // #1 引用回溯:滚动到来源页并高亮(targetPage 来自答案的【来源N】)
  useEffect(() => {
    if (!targetPage || !pages.length) return
    const el = document.getElementById('pg-' + targetPage)
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' })
      setHl(targetPage)
      const t = setTimeout(() => setHl(0), 1800)
      return () => clearTimeout(t)
    } else if (pages.length < total) {
      loadPage(docId, pages.length)   // 还没加载到该页 → 继续加载
    }
  }, [pages, targetPage, total, docId, loadPage])

  return (
    <div className="drawer glass">
      <div className="x" onClick={onClose}><IconClose /></div>
      {!meta ? (
        <div className="empty"><div className="spinner" /></div>
      ) : (
        <>
          {isWx ? (
            <>
              <h2>与 {contact} 的聊天</h2>
              <div className="d-meta">微信聊天记录{wxTotal ? ' · 共 ' + wxTotal + ' 条 · 最近在最上' : ''}</div>
              {/* 和「问TA」抽屉完全统一的快捷 chip;点了关闭本页、打开问TA中枢并自动跑对应分析 */}
              <div className="ask-quick rd-quick">
                {[['问TA', null], ['见面简报', '见面简报'], ['深度分析', '深度分析'], ['产出文档', '产出文档']].map(([label, action]) => (
                  <button key={label} className="ask-quick-btn" onClick={() => {
                    onClose()
                    if (onAskContact) onAskContact(contact, action, isGrpChat)
                    else if (onAsk) onAsk('总结一下我和' + contact + '的聊天')
                  }}>{label}</button>
                ))}
              </div>
            </>
          ) : (
            <>
              <h2>{meta.filename}</h2>
              <div className="d-meta">共 {total} 页 · {meta.backend} · {meta.ingested_at}</div>
            </>
          )}

          {/* 音视频 AI 纪要(#6):章节/待办/脑图 */}
          {(meta.backend || '').startsWith('asr:') && (msLoad || ms) && (
            <div className="glass" style={{ margin: '14px 0', padding: 14, borderRadius: 12 }}>
              <div style={{ fontWeight: 600, marginBottom: 8 }}>AI 纪要</div>
              {msLoad && !ms ? (
                <Thinking text="正在提炼章节 / 待办 / 脑图…" hint="AI 在通读整段转写" />
              ) : ms ? (
                <>
                  {ms.chapters && ms.chapters.length > 0 && (
                    <div style={{ marginBottom: 12 }}>
                      <div style={{ fontSize: 12, opacity: .6, marginBottom: 4 }}>章节</div>
                      {ms.chapters.map((c, i) => (
                        <div key={i} style={{ display: 'flex', gap: 8, padding: '3px 0' }}>
                          <span style={{ color: 'var(--accent)', fontVariantNumeric: 'tabular-nums', minWidth: 46 }}>{c.time}</span>
                          <span><b>{c.title}</b>{c.summary ? <span style={{ opacity: .7 }}> — {c.summary}</span> : null}</span>
                        </div>
                      ))}
                    </div>
                  )}
                  {ms.todos && ms.todos.length > 0 && (
                    <div style={{ marginBottom: 12 }}>
                      <div style={{ fontSize: 12, opacity: .6, marginBottom: 4 }}>待办 / 决议</div>
                      {ms.todos.map((t, i) => (
                        <div key={i} style={{ padding: '2px 0' }}>· {t.text}{t.owner ? <span style={{ opacity: .6 }}> [{t.owner}]</span> : null}</div>
                      ))}
                    </div>
                  )}
                  {ms.mindmap && ms.mindmap.branches && ms.mindmap.branches.length > 0 && (
                    <div>
                      <div style={{ fontSize: 12, opacity: .6, marginBottom: 4 }}>脑图 · {ms.mindmap.topic}</div>
                      {ms.mindmap.branches.map((b, i) => (
                        <div key={i} style={{ padding: '2px 0' }}><b>{b.name}</b>{b.points && b.points.length ? <span style={{ opacity: .7 }}>:{b.points.join('、')}</span> : null}</div>
                      ))}
                    </div>
                  )}
                </>
              ) : null}
            </div>
          )}

          {/* 原文(主角):微信聊天走气泡视图(按时间倒序,最近在最上),其他走分页文本 */}
          {isWx ? (
            <>
              {wxLoading && !wxMsgs ? <div className="empty" style={{ padding: 40 }}><div className="spinner" /></div> : <ChatView msgs={wxMsgs} />}
              {wxMsgs && wxMsgs.length < wxTotal && (
                <button className="btn" style={{ width: '100%', marginTop: 8 }} disabled={wxLoading} onClick={loadEarlier}>
                  {wxLoading ? '加载中…' : `加载更早(还有 ${wxTotal - wxMsgs.length} 条)`}
                </button>
              )}
            </>
          ) : (
            <>
              {pages.map((p) => (
                <div key={p.page_no} id={'pg-' + p.page_no} className="page-block"
                     style={p.page_no === hl ? { boxShadow: '0 0 0 2px var(--accent)', borderRadius: 8, transition: 'box-shadow .5s' } : undefined}>
                  <div className="p-no">第 {p.page_no} 页</div>
                  <div className="p-text">{p.text ? (bookish ? reflow(p.text) : p.text) : '(本页无文本)'}</div>
                </div>
              ))}
              {pages.length < total && (
                <button className="btn" style={{ width: '100%', marginTop: 4 }}
                        disabled={loading} onClick={() => loadPage(docId, pages.length)}>
                  {loading ? '加载中…' : `加载更多(还有 ${total - pages.length} 页)`}
                </button>
              )}
            </>
          )}

          {/* 语义相关(收在下面,可展开) */}
          {similar.length > 0 && (
            <div style={{ marginTop: 26, borderTop: '1px solid var(--border)', paddingTop: 18 }}>
              <div className="similar-title" style={{ cursor: 'pointer' }} onClick={() => setShowSim((s) => !s)}>
                语义相关 {similar.length} 篇 {showSim ? '▾' : '▸'}
              </div>
              {showSim && similar.slice(0, 8).map((s) => (
                <div key={s.doc_id} className="similar-item glass" onClick={() => onOpen(s.doc_id)}>
                  <span>{s.filename}</span>
                  <span className="s-score">{(s.score * 100).toFixed(0)}%</span>
                </div>
              ))}
            </div>
          )}
        </>
      )}
      {reportOpen && contact && <ReportPanel contact={contact} onClose={() => setReportOpen(false)} onAsk={onAsk} />}
    </div>
  )
}
