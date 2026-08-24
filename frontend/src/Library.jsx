import React, { useEffect, useState, useMemo } from 'react'
import { api } from './api'
import { IconSearch, IconLibrary } from './icons'
import { Thinking, Empty } from './ui'

const FT_COLOR = {
  PDF: '#f87171', 电子书: '#c084fc', Word: '#60a5fa', PPT: '#fb923c', Excel: '#34d399',
  笔记: '#94a3b8', 文本: '#94a3b8', 网页: '#38bdf8', 数据: '#a3e635', 邮件: '#f0abfc',
  录音: '#fbbf24', 视频: '#fb7185', 截图: '#14b8a6', 其它: '#cbd5e1',
}

export default function Library({ onOpen, reloadKey }) {
  const [lib, setLib] = useState(null)
  const [by, setBy] = useState('topic')   // 'topic' | 'ftype'
  const [sel, setSel] = useState(null)     // 选中的分类名(null=全部)
  const [q, setQ] = useState('')

  useEffect(() => {
    api.library().then(setLib).catch(() => setLib({ documents: [], topics: [], ftypes: [] }))
  }, [reloadKey])

  useEffect(() => { setSel(null) }, [by])

  const cats = (lib && (by === 'topic' ? lib.topics : lib.ftypes)) || []
  const docs = useMemo(() => {
    if (!lib) return []
    let ds = sel ? lib.documents.filter((d) => (by === 'topic' ? d.topic : d.ftype) === sel) : lib.documents
    const kw = q.trim().toLowerCase()
    if (kw) ds = ds.filter((d) => (d.filename || '').toLowerCase().includes(kw) || (d.topic || '').toLowerCase().includes(kw))
    return ds
  }, [lib, sel, by, q])

  if (!lib) return <div className="view"><Thinking phases={['正在读取你的文库…', '按学科与类型归类每份文档…', '文档越多首次归类越久,请稍候…']} hint="首次打开需要归类整理,之后会快很多" /></div>
  if (lib.documents.length === 0)
    return (
      <div className="view"><div className="view-head"><h1>文库</h1></div>
        <Empty icon={<IconLibrary />} title="文库还是空的" sub="去「入库」选个文件夹开始,文档会自动按学科与类型归类整理" />
      </div>
    )

  return (
    <div className="view lib-view">
      <div className="view-head" style={{ marginBottom: 20 }}>
        <h1>文库</h1>
        <p>{lib.documents.length} 份文档,自动按学科/类型归类。点左侧分类筛选,点卡片读原文。</p>
        <div className="lib-search">
          <IconSearch />
          <input placeholder="搜文件名 / 学科…" value={q} onChange={(e) => setQ(e.target.value)} />
          {q && <button className="lib-search-x" onClick={() => setQ('')}>×</button>}
        </div>
      </div>
      <div className="lib-body">
        <aside className="lib-side glass">
          <div className="seg" style={{ padding: 3, marginBottom: 12 }}>
            <button className={by === 'topic' ? 'on' : ''} onClick={() => setBy('topic')}>学科</button>
            <button className={by === 'ftype' ? 'on' : ''} onClick={() => setBy('ftype')}>类型</button>
          </div>
          <div className="cat-list">
            <div className={'cat-item' + (sel === null ? ' on' : '')} onClick={() => setSel(null)}>
              <span className="cat-name">全部</span><span className="cat-count num">{lib.documents.length}</span>
            </div>
            {cats.map((c) => (
              <div key={c.name} className={'cat-item' + (sel === c.name ? ' on' : '')} onClick={() => setSel(c.name)}>
                {by === 'ftype' && <span className="cat-dot" style={{ background: FT_COLOR[c.name] || '#cbd5e1' }} />}
                <span className="cat-name" title={c.name}>{c.name}</span>
                <span className="cat-count num">{c.count}</span>
              </div>
            ))}
          </div>
        </aside>

        <div className="lib-grid">
          {docs.length === 0 && <div className="lib-empty"><IconSearch /><div>没有匹配「{q}」的文档</div></div>}
          {docs.map((d) => (
            <div key={d.id} className="card glass" onClick={() => onOpen(d.id)}>
              <div className="name doc-name-clamp" title={d.filename}>{d.filename}</div>
              <div className="meta">
                <span className="tag" style={{ color: FT_COLOR[d.ftype], borderColor: 'transparent' }}>{d.ftype}</span>
                <span><span className="num">{d.pages}</span> 页</span>
              </div>
              {d.topic && d.topic !== '未分类' && <div className="card-topic">{d.topic}</div>}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
