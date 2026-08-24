import React, { useState, useEffect, useRef } from 'react'
import { api } from './api'
import { Thinking, Empty } from './ui'
import { IconAsk } from './icons'

const TYPES = [
  { key: 'goal', name: '目标', color: '#8b8cff', ph: '例如:下个月做一个关于债券的分享 PPT' },
  { key: 'diary', name: '日记', color: '#f0abfc', ph: '今天发生了什么、想到了什么…' },
  { key: 'note', name: '笔记', color: '#fbbf24', ph: '随手记一个想法/知识点…' },
  { key: 'task', name: '任务', color: '#34d399', ph: '要做的事,写清楚一点…' },
]
const tconf = (k) => TYPES.find((t) => t.key === k) || TYPES[2]

export default function Cards({ onOpen }) {
  const [cards, setCards] = useState(null)
  const [sel, setSel] = useState(null)          // 选中卡片 id
  const [detail, setDetail] = useState(null)    // {content, related}
  const [composing, setComposing] = useState(false)
  const [draft, setDraft] = useState({ ctype: 'goal', title: '', content: '' })
  const [chat, setChat] = useState([])          // {role,content,sources?}
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const endRef = useRef()

  const load = () => api.cards().then((r) => setCards(r.cards || [])).catch(() => setCards([]))
  useEffect(() => { load() }, [])
  useEffect(() => { endRef.current && endRef.current.scrollIntoView({ behavior: 'smooth' }) }, [chat, loading])

  async function openCard(id) {
    setSel(id); setComposing(false); setDetail(null); setChat([])
    try { const r = await api.cardRelated(id); setDetail(r) } catch { setDetail({ content: '', related: [] }) }
  }

  async function saveCard() {
    if (!draft.content.trim()) return
    try {
      const r = await api.createCard(draft)
      setDraft({ ctype: 'goal', title: '', content: '' })
      await load(); openCard(r.id)
    } catch { alert('保存失败') }
  }

  async function ask(q) {
    const query = (q ?? input).trim(); if (!query || loading) return
    setInput('')
    const anchor = detail ? [{ role: 'user', content: '【我的卡片】' + detail.content }] : []
    const history = [...anchor, ...chat.map((m) => ({ role: m.role, content: m.content }))]
    const next = [...chat, { role: 'user', content: query }]
    setChat(next); setLoading(true)
    try { const r = await api.ask(query, history); setChat([...next, { role: 'assistant', content: r.answer, sources: r.sources || [] }]) }
    catch { setChat([...next, { role: 'assistant', content: 'AI 调用失败,请到「设置」检查模型/key。', sources: [] }]) }
    setLoading(false)
  }

  return (
    <div className="cards-view">
      {/* 左:卡片列表 */}
      <aside className="cards-side glass">
        <button className="btn btn-primary" style={{ width: '100%', marginBottom: 14 }}
          onClick={() => { setComposing(true); setSel(null); setDetail(null); setChat([]) }}>+ 新建卡片</button>
        {cards === null ? <Thinking text="正在打开你的卡片…" />
          : cards.length === 0 ? <div className="cards-hint">还没有卡片。写下你的第一个目标/日记,第二大脑会为它翻出相关历史。</div>
            : cards.map((c) => (
              <div key={c.id} className={'card-item' + (sel === c.id ? ' on' : '')} onClick={() => openCard(c.id)}>
                <span className="ci-dot" style={{ background: tconf(c.ctype).color }} />
                <span className="ci-title">{c.title}</span>
                <span className="ci-type">{tconf(c.ctype).name}</span>
              </div>
            ))}
      </aside>

      {/* 右:新建 or 卡片详情 */}
      <main className="cards-main">
        {composing ? (
          <div className="compose">
            <div className="view-head"><h1>新建卡片</h1><p>写下你的目标、日记、笔记或任务 —— 存下来它就成了你大脑的一部分。</p></div>
            <div className="seg glass" style={{ display: 'inline-flex', marginBottom: 16 }}>
              {TYPES.map((t) => <button key={t.key} className={draft.ctype === t.key ? 'on' : ''} onClick={() => setDraft((d) => ({ ...d, ctype: t.key }))}>{t.name}</button>)}
            </div>
            <input className="search" style={{ marginBottom: 12 }} placeholder="标题(可选)" value={draft.title} onChange={(e) => setDraft((d) => ({ ...d, title: e.target.value }))} />
            <textarea className="compose-area glass" placeholder={tconf(draft.ctype).ph} value={draft.content} onChange={(e) => setDraft((d) => ({ ...d, content: e.target.value }))} />
            <div style={{ marginTop: 16 }}><button className="btn btn-primary" onClick={saveCard}>保存并联想历史</button></div>
          </div>
        ) : !detail ? (
          <Empty icon={<IconAsk />} title="选一张卡片,或新建一张" sub="它会自动翻出你知识库里相关的内容" />
        ) : (
          <div className="card-detail">
            <div className="cd-content glass">{detail.content}</div>
            {detail.related && detail.related.length > 0 && (
              <>
                <div className="t-label" style={{ margin: '22px 0 12px' }}>为这张卡片,你的知识库里有</div>
                <div className="cd-related">
                  {detail.related.map((s, i) => (
                    <div key={i} className="rel-card glass" onClick={() => onOpen(s.doc_id)}>
                      <div className="rel-fn">{s.filename}</div>
                      <div className="rel-meta">第 {s.page_no} 页 · 相关 {(s.score * 100).toFixed(0)}%</div>
                      <div className="rel-snip">{(s.text || '').slice(0, 90)}…</div>
                    </div>
                  ))}
                </div>
              </>
            )}
            <div className="t-label" style={{ margin: '26px 0 12px' }}>针对这张卡片继续问</div>
            <div className="cd-chat">
              {chat.map((m, i) => (
                <div key={i} className={'msg ' + m.role}>
                  {m.role === 'assistant' && <div className="msg-tag">第二大脑</div>}
                  <div className="msg-body">{m.content}</div>
                  {m.sources && m.sources.length > 0 && <div className="msg-src">{m.sources.slice(0, 5).map((s, j) => <span key={j} className="src-chip" onClick={() => onOpen(s.doc_id)}>{s.filename.slice(0, 16)} · P{s.page_no}</span>)}</div>}
                </div>
              ))}
              {loading && <div className="msg assistant"><div className="msg-tag">第二大脑</div><div className="msg-body"><span className="thinking-dots mini"><i /><i /><i /></span> 翻你的知识库…</div></div>}
              <div ref={endRef} />
            </div>
            <div className="ask-input glass" style={{ margin: '14px 0 0' }}>
              <textarea rows={1} placeholder="例如:帮我基于这些做个大纲 / 还缺什么资料?" value={input} onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); ask() } }} />
              <button className="btn btn-primary" onClick={() => ask()} disabled={loading}>发送</button>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
