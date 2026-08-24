import React, { useState, useEffect, useRef, useCallback } from 'react'
import { createPortal } from 'react-dom'
import { api } from './api'
import { Empty } from './ui'
import { IconRadar } from './icons'

// 主动发现:第二大脑替你盯着,有价值的事主动冒出来(该联系 / 对方在等回 / 承诺到期)。
// 铃铛 + 未读徽章 + 右侧信息流抽屉。数据来自 /api/discoveries。
const TYPE_META = {
  reply: { label: '在等你回', color: '#fb7185' },
  commitment: { label: '承诺', color: '#fb923c' },
  cooling: { label: '该联系', color: '#8b8cff' },
}
const SEEN_KEY = 'discoveriesSeen'
const DISM_KEY = 'discoveriesDismissed'

function keyOf(d) { return d.type + ':' + (d.contact || '') + ':' + (d.title || '') }

export default function DiscoveryBell({ onOpen, onAsk }) {
  const [items, setItems] = useState([])
  const [open, setOpen] = useState(false)
  const [seen, setSeen] = useState(() => { try { return new Set(JSON.parse(localStorage.getItem(SEEN_KEY) || '[]')) } catch { return new Set() } })
  const [dismissed, setDismissed] = useState(() => { try { return new Set(JSON.parse(localStorage.getItem(DISM_KEY) || '[]')) } catch { return new Set() } })
  const timer = useRef(null)

  const persistDismissed = (nx) => { setDismissed(nx); try { localStorage.setItem(DISM_KEY, JSON.stringify([...nx].slice(-500))) } catch {} }
  const dismissOne = (d) => { const nx = new Set(dismissed); nx.add(keyOf(d)); persistDismissed(nx) }
  const clearAll = () => { const nx = new Set(dismissed); feed.forEach((d) => nx.add(keyOf(d))); persistDismissed(nx) }

  const refresh = useCallback(() => {
    api.discoveries().then((r) => setItems((r && r.discoveries) || [])).catch(() => {})
  }, [])
  useEffect(() => {
    refresh()
    timer.current = setInterval(refresh, 60000)
    return () => clearInterval(timer.current)
  }, [refresh])

  // 去重:同一个人同一类只留最紧的一条(治攀岩群那种"答应你的事已逾期"刷屏)
  const feed = React.useMemo(() => {
    const seen2 = new Set(); const out = []
    for (const d of items) {
      if (dismissed.has(keyOf(d))) continue   // 用户清除过的不再出现
      const k = (d.type || '') + ':' + (d.contact || '')
      if (seen2.has(k)) continue
      seen2.add(k); out.push(d)
    }
    return out
  }, [items, dismissed])

  const unseen = feed.filter((d) => !seen.has(keyOf(d)))
  const badge = unseen.length

  const markAllSeen = () => {
    const next = new Set(seen)
    items.forEach((d) => next.add(keyOf(d)))
    setSeen(next)
    try { localStorage.setItem(SEEN_KEY, JSON.stringify([...next].slice(-300))) } catch {}
  }
  const toggle = () => {
    const nv = !open
    setOpen(nv)
    if (nv) { refresh(); setTimeout(markAllSeen, 1200) }
  }

  return (
    <>
      <button className={'disc-bell' + (badge > 0 ? ' has' : '') + (open ? ' active' : '')} onClick={toggle} title="主动发现">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.73 21a2 2 0 0 1-3.46 0" />
        </svg>
        {badge > 0 && <span className="disc-badge">{badge > 99 ? '99+' : badge}</span>}
      </button>

      {open && createPortal(
        <div className="disc-overlay" onClick={() => setOpen(false)}>
          <div className="disc-panel glass" onClick={(e) => e.stopPropagation()}>
            <div className="disc-head">
              <div className="disc-title">
                <span className="disc-title-dot" />主动发现
                <span className="disc-sub">第二大脑替你盯着的事</span>
              </div>
              <div className="disc-head-r">
                {feed.length > 0 && <button className="disc-clearall" onClick={clearAll}>全部清除</button>}
                <button className="disc-close" onClick={() => setOpen(false)}>×</button>
              </div>
            </div>

            {feed.length === 0 ? (
              <Empty icon={<IconRadar />} title="暂时没有要提醒你的事" sub="有承诺到期 / 谁在等你回 / 很久没联系的人,会主动冒到这里" />
            ) : (
              <div className="disc-feed">
                {feed.map((d, i) => {
                  const m = TYPE_META[d.type] || { label: '提醒', color: '#8b8cff' }
                  return (
                    <div key={i} className={'disc-item u' + (d.urgency || 2) + (seen.has(keyOf(d)) ? '' : ' fresh')} style={{ '--dc': m.color }}>
                      <button className="disc-dismiss" title="清除这条(不再提醒)" onClick={(e) => { e.stopPropagation(); dismissOne(d) }}>✕</button>
                      <div className="disc-item-top">
                        <span className="disc-tag" style={{ background: m.color }}>{m.label}</span>
                        <span className="disc-item-title">{d.title}</span>
                      </div>
                      {d.detail && <div className="disc-item-detail">{d.detail}</div>}
                      <div className="disc-item-acts">
                        {d.ask && <button className="disc-act primary" onClick={() => { setOpen(false); onAsk && onAsk(d.ask) }}>问大脑</button>}
                        {d.doc_id != null && <button className="disc-act" onClick={() => { setOpen(false); onOpen && onOpen(d.doc_id) }}>看聊天</button>}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </div>,
        document.body
      )}
    </>
  )
}
