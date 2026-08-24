import React, { useState, useRef, useEffect } from 'react'
import { api } from './api'
import { IconSearch } from './icons'

// 把答案里的【来源N】渲染成可点的上标引用
function renderAnswer(text, sources, onOpen) {
  const parts = String(text).split(/(【来源\d+】)/g)
  return parts.map((p, i) => {
    const m = p.match(/【来源(\d+)】/)
    if (m) {
      const n = parseInt(m[1], 10)
      const s = sources && sources[n - 1]
      return <sup key={i} className="cite" title={s ? `${s.filename} · 第${s.page_no}页` : ''} onClick={() => s && onOpen({ id: s.doc_id, page: s.page_no })}>{n}</sup>
    }
    return <span key={i}>{p}</span>
  })
}

const EXAMPLES = [
  '帮我做一个关于债券估值的 PPT 大纲',
  '我想系统学习衍生品,给我一条路径 + 我库里的素材',
  '关于风险管理,我读过的书里有哪些关键观点?',
  '把我库里 ESG 相关的内容总结成要点',
]

export default function Ask({ onOpen }) {
  const [msgs, setMsgs] = useState([])   // {role, content, sources?}
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const endRef = useRef()

  useEffect(() => { endRef.current && endRef.current.scrollIntoView({ behavior: 'smooth' }) }, [msgs, loading])

  async function send(q) {
    const query = (q ?? input).trim()
    if (!query || loading) return
    setInput('')
    const history = msgs.map((m) => ({ role: m.role, content: m.content }))
    const next = [...msgs, { role: 'user', content: query }]
    setMsgs(next); setLoading(true)
    try {
      const r = await api.ask(query, history)
      setMsgs([...next, { role: 'assistant', content: r.answer, sources: r.sources || [] }])
    } catch (e) {
      setMsgs([...next, { role: 'assistant', content: 'AI 调用失败。请到「设置」确认模型和 key 已配置。', sources: [] }])
    }
    setLoading(false)
  }

  const empty = msgs.length === 0

  return (
    <div className="ask-view">
      {empty ? (
        <div className="ask-empty">
          <h1>问你的第二大脑</h1>
          <p>写下你的目标、任务或问题 —— 它会翻遍你的全部历史,基于你自己的资料回答,并带上出处。</p>
          <div className="ask-box glass">
            <IconSearch />
            <textarea rows={1} autoFocus placeholder="例如:帮我做一个关于 XXX 的 PPT 大纲…"
              value={input} onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }} />
            <button className="btn btn-primary" onClick={() => send()} disabled={loading}>发送</button>
          </div>
          <div className="ask-examples">
            {EXAMPLES.map((ex) => (
              <div key={ex} className="ask-ex glass" onClick={() => send(ex)}>{ex}</div>
            ))}
          </div>
        </div>
      ) : (
        <>
          <div className="ask-thread">
            {msgs.map((m, i) => (
              <div key={i} className={'msg ' + m.role}>
                {m.role === 'assistant' && <div className="msg-tag">第二大脑</div>}
                <div className="msg-body">{m.role === 'assistant' ? renderAnswer(m.content, m.sources, onOpen) : m.content}</div>
                {m.role === 'assistant' && m.sources && m.sources.length > 0 && (
                  <div className="src-list">
                    <div className="src-list-head">参考来源 · 来自你的知识库</div>
                    {m.sources.slice(0, 6).map((s, j) => (
                      <div key={j} className="src-ref" onClick={() => onOpen({ id: s.doc_id, page: s.page_no })}>
                        <span className="src-n">{j + 1}</span>
                        <span className="src-fn">{s.filename} · 第 {s.page_no} 页</span>
                        <span className="src-score num">{(s.score * 100).toFixed(0)}%</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
            {loading && <div className="msg assistant"><div className="msg-tag">第二大脑</div><div className="msg-body"><span className="thinking-dots mini"><i /><i /><i /></span> 翻你的知识库中…</div></div>}
            <div ref={endRef} />
          </div>
          <div className="ask-input glass">
            <textarea rows={1} placeholder="继续追问…" value={input} onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }} />
            <button className="btn btn-primary" onClick={() => send()} disabled={loading}>发送</button>
          </div>
        </>
      )}
    </div>
  )
}
