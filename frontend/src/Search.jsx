import React, { useState } from 'react'
import { api } from './api'
import { IconSearch } from './icons'
import { Empty } from './ui'

// 后端 snippet 用「」标高亮 → 转成 <mark>
function renderSnippet(s) {
  const parts = String(s).split(/[「」]/)
  return parts.map((p, i) => (i % 2 === 1 ? <mark key={i}>{p}</mark> : <span key={i}>{p}</span>))
}

export default function Search({ onOpen }) {
  const [q, setQ] = useState('')
  const [hits, setHits] = useState(null)
  const [loading, setLoading] = useState(false)

  async function run(e) {
    e.preventDefault()
    if (!q.trim()) return
    setLoading(true)
    try { const r = await api.search(q); setHits(r.hits || []) }
    catch { setHits([]) }
    setLoading(false)
  }

  return (
    <div className="view">
      <div className="view-head">
        <h1>搜索</h1>
        <p>全文检索你的整个知识库,命中直达原文页。</p>
      </div>

      <form className="search-wrap" onSubmit={run} style={{ maxWidth: 640 }}>
        <IconSearch />
        <input className="search" autoFocus placeholder="输入关键词,回车检索"
               value={q} onChange={(e) => setQ(e.target.value)} />
      </form>

      <div style={{ marginTop: 22, maxWidth: 760 }}>
        {loading ? (
          <div className="empty"><div className="spinner" /></div>
        ) : hits === null ? null : hits.length === 0 ? (
          <Empty icon={<IconSearch />} title="没有命中" sub="换个关键词试试" />
        ) : (
          <>
            <div className="t-label" style={{ marginBottom: 8 }}>{hits.length} 条命中</div>
            {hits.map((h, i) => (
              <div key={i} className="hit glass" onClick={() => onOpen(h.doc_id)}>
                <div className="h-title">{h.filename} · 第 {h.page_no} 页</div>
                <div className="h-snip">{renderSnippet(h.snippet)}</div>
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  )
}
