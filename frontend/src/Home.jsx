import React, { useState, useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import { api } from './api'
import { IconSearch, IconClose } from './icons'
import { toast, confirmDialog, Thinking } from './ui'
import { renderRich } from './AskDrawer'
import { MoodIcon, MOOD_META } from './MoodIcons'

// 今日发现卡循环配色(科技冷 + 暖色,呼应画像页)
const INS_COLORS = ['#6ee7f7', '#a78bfa', '#fbbf24', '#fb7185', '#34d399', '#38bdf8']

// 新闻日期:把 "2026-08-08T10:18:07+08:00" 这种 ISO 收成干净的 "8月8日";解析不了就原样截断
function fmtNewsDate(s) {
  if (!s) return ''
  const d = new Date(s)
  if (isNaN(d.getTime())) return String(s).slice(0, 16)
  return (d.getMonth() + 1) + '月' + d.getDate() + '日'
}

// 两种卡片:目标(可执行,有日期,AI 主动跟踪推进) / 日记(反思随记,AI 主动陪聊发现)
const TYPES = [
  {
    key: 'goal', name: '目标', color: '#8b8cff', verb: '我要达成',
    tip: '一个你想做成的事(可以有期限)。建好之后,AI 会主动翻你的全部历史,发现能推进它的下一步、到点提醒你。',
    ph: '例如:下个月做一次关于债券的分享 / 考下 CFA',
    fields: { deadline: '期限', why: '为什么对我重要' },
  },
  {
    key: 'diary', name: '日记', color: '#f0abfc', verb: '此刻',
    tip: '随手记此刻的想法、心情、灵感。AI 会主动接话,把它和你的过往串起来。',
    ph: '今天发生了什么、想到了什么…',
    fields: { mood: '心情' },
  },
]
// 旧的 4 类归并到 2 类:任务→目标,笔记→日记
const NORM = { goal: 'goal', task: 'goal', diary: 'diary', note: 'diary', markdown: 'diary' }
const tconf = (k) => TYPES.find((t) => t.key === (NORM[k] || 'diary')) || TYPES[0]
const extOf = (f) => (f === 'word' ? 'docx' : f === 'excel' ? 'xlsx' : 'pptx')
const MOODS = ['开心', '平静', '充实', '疲惫', '低落', '焦虑', '兴奋']
const PRIOS = ['高', '中', '低']
const myUser = () => { try { const a = JSON.parse(localStorage.getItem('auth') || 'null'); return a ? a.username : '' } catch { return '' } }
const today = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}` }

// 把结构化表单序列化成一段自然文本(后端只存文本,无需改库)
function buildContent(ct, f) {
  const body = (f.text || '').trim()
  const meta = []
  if (ct === 'goal') {
    if (f.deadline) meta.push(`期限:${f.deadline}`)
    if ((f.why || '').trim()) meta.push(`为什么:${f.why.trim()}`)
  } else if (ct === 'diary') {
    const head = `${f.date || today()}${f.mood ? ' · 心情' + f.mood : ''}`
    return `${head}\n${body}`
  } else if (ct === 'note') {
    if ((f.tags || '').trim()) meta.push(`标签:${f.tags.trim()}`)
  } else if (ct === 'task') {
    if (f.due) meta.push(`截止:${f.due}`)
    if (f.prio) meta.push(`轻重:${f.prio}`)
  }
  return meta.length ? `${body}\n${meta.map((m) => '· ' + m).join('\n')}` : body
}

// 卡片列表上要显示的那枚小徽标(每种类型不一样)
// 从卡片(标题或内容)里认出日记心情 —— 用于卡片上那枚动画小脸
function cardMood(c) {
  if (c.ctype !== 'diary') return null
  const m = ((c.title || '') + ' ' + (c.content || '')).match(/心情(开心|平静|充实|疲惫|低落|焦虑|兴奋)/)
  return m ? m[1] : null
}
function cardMeta(c) {
  const t = c.content || ''
  if (c.ctype === 'diary') { const m = t.match(/^(\d{4}-\d{2}-\d{2})/); const mood = t.match(/心情(\S+)/); return [m && m[1], mood && ('心情' + mood[1])].filter(Boolean) }
  if (c.ctype === 'goal') { const d = t.match(/期限:(\S+)/); return [d && ('期限 ' + d[1])].filter(Boolean) }
  if (c.ctype === 'task') { const d = t.match(/截止:(\S+)/); const p = t.match(/轻重:(\S+)/); return [d && ('截止 ' + d[1]), p && (p[1] + '优先')].filter(Boolean) }
  if (c.ctype === 'note') { const g = t.match(/标签:(\S+)/); return [g && g[1]].filter(Boolean) }
  return []
}

function renderAnswer(text, sources, onOpen) {
  return String(text).split(/(【来源\d+】)/g).map((p, i) => {
    const m = p.match(/【来源(\d+)】/)
    if (m) { const n = +m[1], s = sources && sources[n - 1]; return <sup key={i} className="cite" onClick={() => s && onOpen(s.doc_id)}>{n}</sup> }
    return <span key={i}>{p}</span>
  })
}

const PPT_THEMES = [['deep', '深空'], ['clean', '简约'], ['warm', '暖阳'], ['forest', '松林']]

function GenBar({ topic }) {
  const [busy, setBusy] = useState(null); const [file, setFile] = useState(null)
  const [theme, setTheme] = useState('deep'); const [preview, setPreview] = useState(false)
  async function gen(fmt) {
    setBusy(fmt); setFile(null); setPreview(false)
    try { const r = await api.generate(topic, fmt, theme); setFile(r) } catch { toast('生成失败,请到「设置」检查模型/key', 'err') }
    setBusy(null)
  }
  return (
    <div className="gen-bar">
      <span className="gen-label">产出交付物</span>
      {[['ppt', 'PPT'], ['word', 'Word'], ['excel', 'Excel']].map(([f, n]) => (
        <button key={f} className="btn gen-btn" disabled={!!busy} onClick={() => gen(f)}>{busy === f ? '深度撰写中…' : '生成 ' + n}</button>
      ))}
      {busy && <span className="gen-hint"><span className="spinner spinner-xs" /> 深度模型撰写中,约 1–2 分钟…</span>}
      <span className="gen-theme">
        <span className="gen-theme-label">PPT 模板</span>
        {PPT_THEMES.map(([k, n]) => (
          <button key={k} type="button" className={'theme-dot theme-' + k + (theme === k ? ' on' : '')} title={n} onClick={() => setTheme(k)}>{theme === k ? n : ''}</button>
        ))}
      </span>
      {file && file.preview && <button className="btn gen-btn" onClick={() => setPreview(true)}>预览</button>}
      {file && <a className="gen-dl" href={file.url} download>下载《{file.title}》.{extOf(file.format)}</a>}
      {preview && file && file.preview && (
        <div className="guide-overlay" onClick={() => setPreview(false)}>
          <div className="prev-modal glass" onClick={(e) => e.stopPropagation()}>
            <div className="prev-head"><span>预览 · {file.title}</span><span className="x" onClick={() => setPreview(false)}><IconClose /></span></div>
            <iframe className="prev-frame" src={((typeof window !== 'undefined' && window.__COMPOUND_API_BASE__) || '') + '/api/preview/' + file.preview} title="preview" />
          </div>
        </div>
      )}
    </div>
  )
}

// 每种类型不同的结构化表单
function ComposeForm({ ct, form, set }) {
  const t = tconf(ct)
  return (
    <>
      <textarea className="compose-area" autoFocus placeholder={t.ph} value={form.text || ''} onChange={(e) => set({ text: e.target.value })} />
      {ct === 'goal' && (<div className="cf-fields">
        <label className="cf-field"><span>{t.fields.deadline}(可选)</span><input type="date" value={form.deadline || ''} onChange={(e) => set({ deadline: e.target.value })} /></label>
        <label className="cf-field"><span>{t.fields.why}(可选)</span><input placeholder="想清楚动机,更容易坚持" value={form.why || ''} onChange={(e) => set({ why: e.target.value })} /></label>
      </div>)}
      {ct === 'diary' && (<div className="cf-fields">
        <div className="cf-date">{form.date || today()}</div>
        <div className="cf-chips mood-chips"><span className="cf-clabel">心情</span>{MOODS.map((m) => (
          <button key={m} type="button" className={'chip mood-chip' + (form.mood === m ? ' on' : '')} style={{ '--mood-c': MOOD_META[m].color }} onClick={() => set({ mood: form.mood === m ? '' : m })}>
            <span className="mood-ic"><MoodIcon mood={m} /></span><span className="mood-lb">{m}</span>
          </button>))}</div>
      </div>)}
      {ct === 'note' && (<div className="cf-fields">
        <label className="cf-field"><span>{t.fields.tags}(可选,空格分隔)</span><input placeholder="债券 估值 灵感" value={form.tags || ''} onChange={(e) => set({ tags: e.target.value })} /></label>
      </div>)}
      {ct === 'task' && (<div className="cf-fields">
        <label className="cf-field"><span>{t.fields.due}(可选)</span><input type="date" value={form.due || ''} onChange={(e) => set({ due: e.target.value })} /></label>
        <div className="cf-chips"><span className="cf-clabel">轻重</span>{PRIOS.map((p) => (
          <button key={p} type="button" className={'chip' + (form.prio === p ? ' on' : '')} onClick={() => set({ prio: form.prio === p ? '' : p })}>{p}</button>))}</div>
      </div>)}
    </>
  )
}

export default function Home({ onOpen, onUnread }) {
  const [cards, setCards] = useState([])
  const [compose, setCompose] = useState(null); const [form, setForm] = useState({})
  const [open, setOpen] = useState(null)
  const [gq, setGq] = useState(''); const [gloading, setGloading] = useState(false)
  // 底部问答=持久对话流(用户不删就一直在;localStorage 按账号存,刷新不丢)
  const THREAD_KEY = 'home_thread_' + myUser()
  const [thread, setThread] = useState(() => { try { return JSON.parse(localStorage.getItem(THREAD_KEY) || '[]') } catch { return [] } })
  const saveThread = (t) => { setThread(t); try { localStorage.setItem(THREAD_KEY, JSON.stringify(t.slice(-40))) } catch { /* noop */ } }
  const [cq, setCq] = useState(''); const [cloading, setCloading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [todayFeed, setTodayFeed] = useState(null)
  const [links, setLinks] = useState(null)
  const [entLinks, setEntLinks] = useState(null)
  const [news, setNews] = useState(null)
  const [editing, setEditing] = useState(false); const [editText, setEditText] = useState('')
  const endRef = useRef()
  const ansRef = useRef()

  const load = () => api.cards().then((r) => { setCards(r.cards || []); onUnread && onUnread(r.unread_total || 0) }).catch(() => {})
  useEffect(() => { load(); api.today().then((r) => setTodayFeed(r.items || [])).catch(() => {}); api.links().then((r) => setLinks(r.links || [])).catch(() => {}); api.entityLinks().then((r) => setEntLinks(r.links || [])).catch(() => {}); api.news().then((r) => setNews(r)).catch(() => {}) }, [])

  // 从「人脉」页点"问TA/分析入口"跳来:自动带着问题问一次
  useEffect(() => {
    let pf = null
    try { pf = localStorage.getItem('rel_ask'); if (pf) localStorage.removeItem('rel_ask') } catch { /* noop */ }
    if (!pf) return
    askDirect(pf)
  }, [])
  useEffect(() => { endRef.current && endRef.current.scrollIntoView({ behavior: 'smooth' }) }, [open && open.chat, cloading])

  const setF = (patch) => setForm((f) => ({ ...f, ...patch }))
  function startCompose(ctype) { setForm({ date: today() }); setCompose({ ctype }) }

  async function saveCard() {
    const content = buildContent(compose.ctype, form).trim()
    if (!(form.text || '').trim()) { toast('写点内容吧', 'err'); return }
    setSaving(true)
    try { await api.createCard({ ctype: compose.ctype, content }); setForm({}); setCompose(null); load(); toast('已保存并联想历史', 'ok') }
    catch { toast('保存失败,请到设置检查模型/key', 'err') }
    setSaving(false)
  }
  async function delCard(id, e) {
    e.stopPropagation()
    if (!(await confirmDialog('确定删除这张卡片?', '删除', true))) return
    try { await api.deleteCard(id); if (open && open.id === id) setOpen(null); load(); toast('已删除', 'ok') }
    catch { toast('删除失败', 'err') }
  }
  async function toggleDone() {
    const next = open.status === 'done' ? 'doing' : 'done'
    try { await api.cardStatus(open.id, next); setOpen((o) => ({ ...o, status: next })); load(); toast(next === 'done' ? '已标记完成' : '已恢复进行中', 'ok') }
    catch { toast('操作失败', 'err') }
  }
  function startEdit() { setEditText(open.content || ''); setEditing(true) }
  async function saveEdit() {
    const c = editText.trim(); if (!c) { toast('内容不能为空', 'err'); return }
    try { const r = await api.cardEdit(open.id, c); setOpen((o) => ({ ...o, content: c, title: r.title })); setEditing(false); load(); toast('已更新并重新联想', 'ok') }
    catch { toast('保存失败', 'err') }
  }
  async function openCard(id) {
    const card = cards.find((c) => c.id === id) || {}
    setEditing(false)
    setOpen({ id, ctype: card.ctype, title: card.title, status: card.status, loading: true, chat: [] })
    try {
      const r = await api.cardRelated(id)
      const chat = (r.messages || []).map((m) => ({ role: 'assistant', content: m.content, proactive: true }))
      setOpen({ id, ctype: card.ctype, title: card.title, status: card.status, content: r.content, related: r.related || [], chat })
      load() // 打开即已读,刷新未读角标
    }
    catch { setOpen({ id, ctype: card.ctype, title: card.title, status: card.status, content: '', error: true, related: [], chat: [] }) }
  }
  // 点卡片直接执行建议/追问:居中弹窗展示结果(用户拍板:别挤在页面底部)
  const [amodal, setAmodal] = useState(null)
  function askDirect(q, label) {
    if (!q || (amodal && amodal.loading)) return
    setAmodal({ q: label || q, loading: true })
    api.ask(q).then((r) => setAmodal({ q: label || q, answer: r.answer, sources: r.sources || [] }))
      .catch((e) => setAmodal({ q: label || q, answer: String(e && e.message || '').length > 8 ? String(e.message) : 'AI 调用失败,请到「设置」检查模型/key。', sources: [] }))
  }

  async function globalAsk() {
    const q = gq.trim(); if (!q || gloading) return
    setGq('')   // 立即清空输入,给"已提交"反馈
    setGloading(true)
    const entry = { q, loading: true, ts: Date.now() }
    const base = [...thread, entry]
    saveThread(base)
    setTimeout(() => { ansRef.current && ansRef.current.scrollIntoView({ behavior: 'smooth', block: 'end' }) }, 60)
    // 带上最近 3 轮上下文,支持连续追问
    const hist = thread.filter((t) => t.answer).slice(-3).flatMap((t) => [{ role: 'user', content: t.q }, { role: 'assistant', content: t.answer }])
    try { const r = await api.ask(q, hist); saveThread(base.map((x) => x === entry ? { ...x, loading: false, answer: r.answer, sources: r.sources || [] } : x)) }
    catch (e) { const msg = String(e && e.message || ''); saveThread(base.map((x) => x === entry ? { ...x, loading: false, answer: msg.length > 8 ? msg : 'AI 调用失败,请到「设置」检查模型/key。', sources: [] } : x)) }
    setGloading(false)
    setTimeout(() => { ansRef.current && ansRef.current.scrollIntoView({ behavior: 'smooth', block: 'end' }) }, 80)
  }
  const delTurn = (i) => saveThread(thread.filter((_, j) => j !== i))
  const [tExpand, setTExpand] = useState(false)
  async function cardAsk() {
    const q = cq.trim(); if (!q || cloading || !open) return
    setCq('')
    const anchor = [{ role: 'user', content: '【我的' + tconf(open.ctype).name + '卡片】' + (open.content || '') }]
    const hist = [...anchor, ...open.chat.map((m) => ({ role: m.role, content: m.content }))]
    const next = [...open.chat, { role: 'user', content: q }]
    setOpen((o) => ({ ...o, chat: next })); setCloading(true)
    try { const r = await api.ask(q, hist); setOpen((o) => ({ ...o, chat: [...next, { role: 'assistant', content: r.answer, sources: r.sources || [] }] })) }
    catch { setOpen((o) => ({ ...o, chat: [...next, { role: 'assistant', content: 'AI 调用失败。', sources: [] }] })) }
    setCloading(false)
  }

  // ===== 卡片详情:围绕这张卡片 =====
  if (open) {
    const tc = tconf(open.ctype)
    const dMood = cardMood({ ctype: open.ctype, title: open.title, content: open.content })
    return (
      <div className="home-view">
        <button className="btn" style={{ marginBottom: 18 }} onClick={() => setOpen(null)}>← 返回</button>
        <div className="cd-content glass" style={{ borderLeft: `3px solid ${tc.color}` }}>
          <div className="cd-head">
            <span className="cd-type" style={{ color: tc.color }}>{dMood && <span className="card-mood" style={{ color: MOOD_META[dMood].color }} title={'心情' + dMood}><MoodIcon mood={dMood} /></span>}{tc.name}{open.status === 'done' && ' · 已完成'}</span>
            <span className="cd-actions">
              {tconf(open.ctype).key === 'goal' && open.content && (
                <button className={'cd-act' + (open.status === 'done' ? ' on' : '')} onClick={toggleDone}>{open.status === 'done' ? '↩ 恢复进行' : '✓ 标记完成'}</button>
              )}
              {open.content && !editing && <button className="cd-act" onClick={startEdit}>✎ 编辑</button>}
            </span>
          </div>
          {editing ? (
            <div>
              <textarea className="compose-area" value={editText} onChange={(e) => setEditText(e.target.value)} style={{ minHeight: 90 }} />
              <div style={{ marginTop: 10, display: 'flex', gap: 8 }}>
                <button className="btn btn-primary" onClick={saveEdit}>保存</button>
                <button className="btn" onClick={() => setEditing(false)}>取消</button>
              </div>
            </div>
          ) : open.content ? <div className={'cd-text' + (open.status === 'done' ? ' cd-done' : '')}>{open.content}</div>
            : open.error ? <div className="cd-text nd-dim">这张卡片内容加载失败。<button className="cd-act" onClick={() => openCard(open.id)}>重试</button></div>
            : <Thinking className="inline" phases={['正在打开卡片…', '翻你的知识库,联想相关历史…', '第二大脑正在主动接话…']} />}
        </div>
        <GenBar topic={open.content || open.title} />
        {open.related && open.related.length > 0 && (<>
          <div className="t-label" style={{ margin: '24px 0 12px' }}>为这张卡片,你的知识库里有</div>
          <div className="cd-related">{open.related.map((s, i) => (
            <div key={i} className="rel-card glass" onClick={() => onOpen(s.doc_id)}>
              <div className="rel-fn">{s.filename}</div>
              <div className="rel-meta">第 {s.page_no} 页 · 相关 {(s.score * 100).toFixed(0)}%</div>
              <div className="rel-snip">{(s.text || '').slice(0, 90)}…</div>
            </div>))}
          </div>
        </>)}
        {open.related && open.related.length === 0 && !open.error && (
          <div className="cd-norel">没找到和这张卡片明显相关的历史内容。写得更具体些(多提人名 / 项目 / 事),第二大脑更容易帮你串起过往。</div>
        )}
        <div className="cd-chatbox">
          <div className="cd-chat-head">围绕这张卡片继续问</div>
          <div className="cd-chat">
            {open.chat.length === 0 && !cloading && (
              <div className="cd-chat-hint">基于这张卡片和你的知识库,问我任何事 —— 比如「帮我列个大纲」「我还缺什么材料」。</div>
            )}
            {open.chat.map((m, i) => (<div key={i} className={'msg ' + m.role}>
              {m.role === 'assistant' && <div className="msg-tag">{m.proactive ? '第二大脑 · 主动发现' : '第二大脑'}</div>}
              <div className={'msg-body' + (m.proactive ? ' msg-proactive' : '')}>{m.role === 'assistant' ? renderAnswer(m.content, m.sources, onOpen) : m.content}</div>
            </div>))}
            {cloading && <div className="msg assistant"><div className="msg-tag">第二大脑</div><div className="msg-body"><span className="spinner" style={{ width: 16, height: 16, display: 'inline-block' }} /> 正在通读你的知识库,通常几秒…</div></div>}
            <div ref={endRef} />
          </div>
          <div className="ask-input glass">
            <textarea rows={1} placeholder="帮我基于这些做个大纲 / 还缺什么?" value={cq} onChange={(e) => setCq(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); cardAsk() } }} />
            <button className="btn btn-primary" onClick={cardAsk} disabled={cloading}>发送</button>
          </div>
        </div>
      </div>
    )
  }

  // ===== 首页:卡片在上(滚动区)+ 全局问答固定底部 =====
  return (
    <div className="home-view home-flex">
      <div className="home-scroll">
        <div className="view-head"><h1>第二大脑</h1><p>把目标 / 日记记成卡片 —— AI 会主动翻你的全部历史,发现能推进它的下一步、主动提醒你。红点是 AI 找你了。</p></div>

        <div className="t-label" style={{ marginBottom: 12 }}>你的卡片</div>
        <div className="home-cards">
          {TYPES.map((t) => (
            <div key={t.key} className="hcard newcard" style={{ borderColor: t.color + '55' }} onClick={() => startCompose(t.key)}>
              <span className="hc-plus" style={{ color: t.color }}>+</span>
              <span className="hc-newlabel">新建{t.name}</span>
              <span className="hc-newtip">{t.verb}…</span>
            </div>
          ))}
          {cards.map((c) => { const tc = tconf(c.ctype); const meta = cardMeta(c); const mood = cardMood(c); return (
            <div key={c.id} className={'hcard glass htype-' + (NORM[c.ctype] || 'diary') + (c.status === 'done' ? ' hcard-done' : '')} style={{ borderLeft: `3px solid ${tc.color}` }} onClick={() => openCard(c.id)}>
              {c.unread > 0 && <span className="hc-unread" title="AI 有主动发现">{c.unread}</span>}
              <span className="hc-del" onClick={(e) => delCard(c.id, e)}><IconClose /></span>
              <span className="hc-type" style={{ color: tc.color }}>{mood && <span className="card-mood" style={{ color: MOOD_META[mood].color }} title={'心情' + mood}><MoodIcon mood={mood} /></span>}{c.status === 'done' ? '✓ ' : ''}{tc.name}</span>
              <div className="hc-title">{c.title}</div>
              {meta.length > 0 && <div className="hc-meta">{meta.map((m, i) => <span key={i} className="hc-chip">{m}</span>)}</div>}
            </div>
          ) })}
        </div>

        {news && news.items && news.items.length > 0 && (
          <div className="news-sec news-top">
            <div className="news-head"><span className="news-dot" />今日新闻 · 和你关注的{news.domains && news.domains.length ? '「' + news.domains.slice(0, 3).join(' / ') + '」' : ''}相关<span className="news-count">{news.items.length} 条</span></div>
            <div className="news-grid">
              {news.items.map((n, i) => (
                <a key={i} className="news-card glass" href={n.url} target="_blank" rel="noreferrer">
                  <div className="news-toprow">
                    {n.date && <span className="news-date">{fmtNewsDate(n.date)}</span>}
                    <span className="news-site">{n.site || '来源'}</span>
                    <span className="news-arrow">↗</span>
                  </div>
                  <div className="news-title">{n.title}</div>
                  {n.why && <div className="news-why"><span className="news-why-tag">为什么对你</span>{n.why}</div>}
                </a>
              ))}
            </div>
          </div>
        )}

        {todayFeed === null && (
          <div className="today-sec">
            <Thinking phases={['正在跨知识库主动发现…', '关联你的目标与历史…', '组织今日要点…']} hint="第二大脑在通读你的全部资料,稍等片刻" />
          </div>
        )}

        {todayFeed && todayFeed.length > 0 && (
          <div className="today-sec">
            <div className="today-head"><span className="today-dot" />今日 · 第二大脑替你发现了 {todayFeed.length} 件事</div>
            <div className="today-items">
              {todayFeed.map((it, i) => {
                const col = INS_COLORS[i % INS_COLORS.length]
                return (
                  <div key={i} className={'today-item glass' + (it.action ? ' clickable' : '')} style={{ borderLeftColor: col }}
                       onClick={() => it.action && askDirect(`【背景】${it.insight}\n【任务】${it.action}\n请直接执行并给出成果本身:不要问我是否需要、不要复述任务、不要以"好的/要"开头,直接从成果内容开始输出。`, it.title)}>
                    <div className="today-title">{it.title}</div>
                    <div className="today-insight">{it.insight}</div>
                    {it.gain && <div className="lx-row"><span className="lx-tag">你能得到</span>{it.gain}</div>}
                    {it.action && <div className="today-action" style={{ color: col }}>{it.action}<span className="today-go">点击执行 →</span></div>}
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {links && links.length > 0 && (
          <div className="links-sec">
            <div className="links-head"><span className="links-dot" />大脑替你接上了这些 —— 你可能忘了它们其实相关</div>
            <div className="links-grid">
              {links.map((l, i) => (
                <div key={i} className="link-card glass clickable"
                     onClick={() => askDirect(`我的资料《${l.a}》和《${l.b}》被判定为相关(相似度 ${l.score}%)。请具体说明:①它们相关在哪里——共同的主题/人物/业务是什么,各引一小段两边的原文佐证;②把它们连起来看,我能得到什么此前没注意到的信息或可以做的事。`, `《${l.a}》和《${l.b}》具体相关在哪?`)}>
                  <div className="link-badge">
                    <span className="link-score">{l.score}<em>%</em></span>
                    <span className="link-tags">{l.ta} <i>×</i> {l.tb}{l.gap > 30 ? ` · 跨 ${Math.round(l.gap / 30)} 个月` : l.gap > 0 ? ` · 跨 ${l.gap} 天` : ''}</span>
                    <span className="link-go">哪里相关?点击看 →</span>
                  </div>
                  <div className="link-pair">
                    <span className="link-doc" onClick={(e) => { e.stopPropagation(); onOpen(l.a_id) }} title="打开这份资料">{l.a}</span>
                    <span className="link-link"><i /><i /><i /></span>
                    <span className="link-doc" onClick={(e) => { e.stopPropagation(); onOpen(l.b_id) }} title="打开这份资料">{l.b}</span>
                  </div>
                  {l.explain ? (
                    <div className="link-expl">
                      <div className="lx-why">{l.explain.why}</div>
                      {l.explain.get && <div className="lx-row"><span className="lx-tag">你能得到</span>{l.explain.get}</div>}
                      {l.explain.do && <div className="lx-row"><span className="lx-tag do">建议</span>{l.explain.do}</div>}
                    </div>
                  ) : <div className="link-expl pending">正在解读这对资料的具体关联,稍后刷新可见…</div>}
                </div>
              ))}
            </div>
          </div>
        )}


        {entLinks && entLinks.length > 0 && (
          <div className="ent-sec">
            <div className="ent-head"><span className="ent-dot" />同一个人 / 事,散落在这些资料里 —— 大脑替你认出来了</div>
            <div className="ent-grid">
              {entLinks.map((e, i) => (
                <div key={i} className="ent-card glass">
                  <div className="ent-name clickable" title="点击看这个关键词在各份资料里的具体上下文"
                       onClick={() => askDirect(`「${e.entity}」出现在我的 ${e.count} 份资料里。请告诉我:它在其中几份代表性资料里具体是因为什么出现的(各自的上下文和角色),以及这些散落的信息连起来,我能利用的点是什么。`, `「${e.entity}」为什么出现在这些资料里?`)}>
                    {e.etype && <span className="ent-type">{e.etype}</span>}
                    <span className="ent-word">{e.entity}</span>
                    <span className="ent-count">{e.count} 份资料</span>
                    <span className="ent-go">为什么相关?→</span>
                  </div>
                  {e.explain ? (
                    <div className="ent-expl">
                      <div className="lx-why">{e.explain.why}</div>
                      {e.explain.get && <div className="lx-row"><span className="lx-tag">你能得到</span>{e.explain.get}</div>}
                      {e.explain.do && <div className="lx-row"><span className="lx-tag do">建议</span>{e.explain.do}</div>}
                    </div>
                  ) : <div className="ent-expl pending">正在解读这个关键词的具体上下文,稍后刷新可见…</div>}
                  <div className="ent-docs">
                    {e.docs.map((d, j) => (
                      <span key={j} className="ent-doc" onClick={() => onOpen(d.id)} title={d.filename}>{d.filename}</span>
                    ))}
                    {e.count > e.docs.length && <span className="ent-doc-more">…共 {e.count} 份,点上方「为什么相关」问大脑</span>}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {thread.length > 0 && (() => { const threadEl = (
          <div className={'home-thread' + (tExpand ? ' expanded' : '')} ref={ansRef}>
            <div className="ht-head">
              <span className="t-label" style={{ margin: 0 }}>与第二大脑的对话 · {thread.length} 条</span>
              <span className="ht-btns">
                <button className="ht-clear" onClick={() => saveThread([])}>清空对话</button>
                <button className="ht-clear" onClick={() => setTExpand((v) => !v)}>
                  {tExpand ? (
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><path d="M9 4v5H4M15 4v5h5M9 20v-5H4M15 20v-5h5" /></svg>
                  ) : (
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" /></svg>
                  )}
                  {tExpand ? ' 收起' : ' 全屏'}
                </button>
              </span>
            </div>
            <div className="ht-list">
            {thread.map((t, i) => (
              <div key={t.ts || i} className="home-answer glass" style={{ position: 'relative' }}>
                <span className="ha-close" title="删除这条" onClick={() => delTurn(i)}><IconClose /></span>
                <div className="msg-tag">你 · {t.q}</div>
                <div className="msg-body">{t.loading
                  ? <span><span className="spinner" style={{ width: 16, height: 16, display: 'inline-block' }} /> 正在通读你的知识库,通常几秒…</span>
                  : renderRich(t.answer, t.sources, onOpen)}</div>
                {!t.loading && (t.sources || []).length > 0 && (
                  <div className="src-list"><div className="src-list-head">参考来源</div>{t.sources.slice(0, 6).map((s, j) => (
                    <div key={j} className="src-ref" onClick={() => onOpen({ id: s.doc_id, page: s.page_no || 0 })}><span className="src-n">{j + 1}</span><span className="src-fn">{s.filename}{s.rel_card ? '' : ' · 第 ' + s.page_no + ' 页'}</span><span className="src-score num">{s.rel_card ? '档案' : Math.min(99, Math.round(s.score * 100)) + '%'}</span></div>))}
                  </div>
                )}
                {!t.loading && <GenBar topic={t.q} />}
              </div>
            ))}
            </div>
            {tExpand && (
              <div className="ht-input">
                <textarea rows={1} placeholder="继续问…" value={gq} onChange={(e) => setGq(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); globalAsk() } }} />
                <button className="btn btn-primary" onClick={globalAsk} disabled={gloading}>问</button>
              </div>
            )}
          </div>
        ); return tExpand ? createPortal(threadEl, document.body) : threadEl })()}
      </div>

      <div className="home-composer">
        <div className="home-box glass">
          <IconSearch />
          <textarea rows={1} placeholder="问点什么,或搜你库里的东西…" value={gq} onChange={(e) => setGq(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); globalAsk() } }} />
          <button className="btn btn-primary home-send" onClick={globalAsk} disabled={gloading}>问</button>
        </div>
      </div>

      {amodal && (
        <div className="guide-overlay" onClick={() => !amodal.loading && setAmodal(null)}>
          <div className="ans-modal" onClick={(e) => e.stopPropagation()}>
            <div className="am-head">
              <span className="am-label">第二大脑 · 执行结果</span>
              <h2 className="am-title">{amodal.q}</h2>
              <div className="x" onClick={() => setAmodal(null)}><IconClose /></div>
            </div>
            <div className="am-body">
              {amodal.loading
                ? <div className="am-loading"><Thinking phases={['正在通读你的知识库…', '交叉比对相关资料…', '提取具体线索与出处…', '组织成果…']} hint="通常几秒,复杂任务约半分钟" /></div>
                : renderRich(amodal.answer, amodal.sources, onOpen)}
              {!amodal.loading && (amodal.sources || []).length > 0 && (
                <div className="src-list"><div className="src-list-head">参考来源</div>{amodal.sources.slice(0, 6).map((s, j) => (
                  <div key={j} className="src-ref" onClick={() => onOpen({ id: s.doc_id, page: s.page_no || 0 })}><span className="src-n">{j + 1}</span><span className="src-fn">{s.filename}{s.rel_card ? '' : ' · 第 ' + s.page_no + ' 页'}</span><span className="src-score num">{s.rel_card ? '档案' : Math.min(99, Math.round(s.score * 100)) + '%'}</span></div>))}
                </div>
              )}
              {!amodal.loading && <GenBar topic={amodal.q} />}
            </div>
          </div>
        </div>
      )}

      {compose && (
        <div className="guide-overlay" onClick={() => setCompose(null)}>
          <div className="guide glass compose-modal" onClick={(e) => e.stopPropagation()} style={{ width: 520, borderTop: `3px solid ${tconf(compose.ctype).color}` }}>
            <div className="x" onClick={() => setCompose(null)}><IconClose /></div>
            <h2 style={{ color: tconf(compose.ctype).color }}>新建{tconf(compose.ctype).name}</h2>
            <p className="compose-tip">{tconf(compose.ctype).tip}</p>
            <ComposeForm ct={compose.ctype} form={form} set={setF} />
            <div style={{ marginTop: 18 }}><button className="btn btn-primary" onClick={saveCard} disabled={saving}>{saving ? '保存中…' : '保存并联想历史'}</button></div>
          </div>
        </div>
      )}
    </div>
  )
}
