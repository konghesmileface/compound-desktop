import React, { useState, useRef, useEffect } from 'react'
import { api } from './api'
import { IconSearch } from './icons'

// 行内:**加粗** / `代码` / 【来源N】可点角标(其余原样)
function renderInline(text, ki, sources, onOpen) {
  const nodes = []
  const re = /(\*\*(.+?)\*\*|【来源(\d+)】|`([^`]+)`)/g
  let last = 0, m, idx = 0
  while ((m = re.exec(text))) {
    if (m.index > last) nodes.push(text.slice(last, m.index))
    if (m[2] != null) nodes.push(<b key={ki + '-' + idx}>{m[2]}</b>)
    else if (m[3] != null) {
      const n = parseInt(m[3], 10)
      const s = sources && sources[n - 1]
      nodes.push(<sup key={ki + '-' + idx} className="cite" title={s ? `${s.filename} · 第${s.page_no}页` : ''} onClick={() => s && onOpen({ id: s.doc_id, page: s.page_no })}>{n}</sup>)
    }
    else if (m[4] != null) nodes.push(<code key={ki + '-' + idx} className="md-code">{m[4]}</code>)
    last = m.index + m[0].length; idx++
  }
  if (last < text.length) nodes.push(text.slice(last))
  return nodes
}
// 答案 markdown 渲染:标题/列表/表格/分隔线/引用/段落 + 保留可点来源角标
function renderAnswer(text, sources, onOpen) {
  text = String(text || '').replace(/^\s*-{3,}\s*$/gm, '―HR―')
  const lines = text.split('\n')
  const out = []
  let list = []
  const flush = () => { if (list.length) { out.push(<ul key={'ul' + out.length} className="md-ul">{list}</ul>); list = [] } }
  const isRow = (s) => /^\s*\|.*\|\s*$/.test(s)
  const isSep = (s) => /^[\s|:\-]+$/.test(s) && s.includes('-') && s.includes('|')
  const cells = (s) => s.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim())
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].replace(/\s+$/, '')
    if (isRow(line) && i + 1 < lines.length && isSep(lines[i + 1])) {
      flush()
      const header = cells(line)
      const rows = []
      let jj = i + 2
      while (jj < lines.length && isRow(lines[jj]) && !isSep(lines[jj])) { rows.push(cells(lines[jj])); jj++ }
      out.push(
        <div key={'tw' + i} className="md-table-wrap"><table className="md-table">
          <thead><tr>{header.map((h, hi) => <th key={hi}>{renderInline(h, 't' + i + 'h' + hi, sources, onOpen)}</th>)}</tr></thead>
          <tbody>{rows.map((r, ri) => <tr key={ri}>{header.map((_, ci) => <td key={ci}>{renderInline(r[ci] || '', 't' + i + 'r' + ri + 'c' + ci, sources, onOpen)}</td>)}</tr>)}</tbody>
        </table></div>
      )
      i = jj - 1
      continue
    }
    if (!line.trim()) { flush(); continue }
    const h = line.match(/^(#{1,4})\s+(.*)/)
    const b = line.match(/^\s*[-•*]\s+(.*)/)
    const n = line.match(/^\s*(\d+)[.、]\s+(.*)/)
    if (h) { flush(); out.push(<div key={i} className="md-h">{renderInline(h[2], i, sources, onOpen)}</div>) }
    else if (b) { list.push(<li key={i}>{renderInline(b[1], i, sources, onOpen)}</li>) }
    else if (n) { list.push(<li key={i}><span className="md-num">{n[1]}.</span> {renderInline(n[2], i, sources, onOpen)}</li>) }
    else if (line.trim() === '―HR―') { flush(); out.push(<div key={i} className="md-hr" />) }
    else if (/^>\s?/.test(line)) { flush(); out.push(<div key={i} className="md-quote">{renderInline(line.replace(/^>\s?/, ''), i, sources, onOpen)}</div>) }
    else { flush(); out.push(<p key={i} className="md-p">{renderInline(line, i, sources, onOpen)}</p>) }
  }
  flush()
  return out
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
