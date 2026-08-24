import React, { useState, useEffect } from 'react'
import { api } from './api'
import { toast, Thinking, Empty } from './ui'
import { IconPersona } from './icons'

// 知识领域卡循环配色(科技冷 + 暖色)
const DOM_COLORS = ['#6ee7f7', '#a78bfa', '#fbbf24', '#fb7185', '#34d399', '#38bdf8', '#f472b6', '#a3e635']

// 双向刻度:0=左标签 100=右标签
function Gauge({ left, right, value, note }) {
  const v = Math.max(0, Math.min(100, value || 50))
  return (
    <div className="pg-gauge">
      <div className="pg-gauge-row">
        <span className="pg-gl">{left}</span>
        <div className="pg-track"><div className="pg-fill" style={{ left: `calc(${v}% - 7px)` }} /></div>
        <span className="pg-gr">{right}</span>
      </div>
      {note && <div className="pg-note">{note}</div>}
    </div>
  )
}

export default function Persona() {
  const [d, setD] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = (refresh) => {
    setBusy(true)
    api.persona(refresh).then((r) => { setD(r); setBusy(false); if (refresh) toast('画像已重新生成', 'ok') })
      .catch(() => { setBusy(false); if (refresh) toast('画像生成失败,检查设置里的模型/key', 'err') })
  }
  useEffect(() => { load(false) }, [])

  if (!d && busy) return (
    <div className="view"><Thinking phases={['正在读你的读物与笔记…', '推断你的人格特质…', '整理成画像与证据…']} hint="基于你真实的知识库,反巴纳姆效应" /></div>
  )
  if (!d) return (
    <div className="view"><Empty icon={<IconPersona />} title="还画不出画像" sub="先去入库灌点文档、建几张卡片,AI 就能基于你真实的知识库画出你的人格画像" /></div>
  )

  return (
    <div className="view persona-view">
      <div className="view-head" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div><h1>我的画像</h1><p>你的第二大脑眼中的你 —— 只从你真实读的、写的里推断,每条都有据。</p></div>
        <button className="btn" disabled={busy} onClick={() => load(true)}>{busy ? '重画中…' : '重新生成'}</button>
      </div>

      <div className="pg-hero glass">
        <div className="pg-oneliner">{d.one_liner}</div>
        {d.tags && <div className="pg-tags">{d.tags.map((t, i) => <span key={i} className="pg-tag">{t}</span>)}</div>}
      </div>

      {d.social && (d.social.circle || d.social.evidence) && (
        <div className="pg-sec">
          <div className="t-label">你的职业与人脉圈</div>
          <div className="pg-social glass">
            <div className="pg-social-circle">{d.social.circle}</div>
            {d.social.evidence && <div className="pg-ev">{d.social.evidence}</div>}
          </div>
        </div>
      )}

      {d.domains && d.domains.length > 0 && (
        <div className="pg-sec">
          <div className="t-label">知识领域</div>
          <div className="pg-domains">
            {d.domains.map((x, i) => {
              const c = DOM_COLORS[i % DOM_COLORS.length]
              return (
                <div key={i} className="pg-domain glass" style={{ '--c': c, borderTopColor: c + '55' }}>
                  <div className="pg-dom-top"><span className="pg-dom-name">{x.name}</span><span className="pg-dom-w num" style={{ color: c }}>{x.weight}</span></div>
                  <div className="pg-bar"><i style={{ width: `${x.weight}%`, background: `linear-gradient(90deg, ${c}, ${c}bb)` }} /></div>
                  {x.evidence && <div className="pg-ev">{x.evidence}</div>}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {d.thinking && (
        <div className="pg-sec">
          <div className="t-label">思维风格</div>
          <div className="glass" style={{ padding: '18px 22px' }}>
            <Gauge left="广度涉猎" right="深挖到底" value={d.thinking.depth} />
            <Gauge left="凭直觉" right="重数据理性" value={d.thinking.rational} />
            {d.thinking.note && <div className="pg-note" style={{ marginTop: 10 }}>{d.thinking.note}</div>}
          </div>
        </div>
      )}

      {d.values && d.values.length > 0 && (
        <div className="pg-sec">
          <div className="t-label">你在意什么</div>
          <div className="pg-values">
            {d.values.map((x, i) => (
              <div key={i} className="pg-value glass">
                <div className="pg-val-trait">{x.trait}</div>
                {x.evidence && <div className="pg-ev">{x.evidence}</div>}
              </div>
            ))}
          </div>
        </div>
      )}

      {d.curiosity && d.curiosity.length > 0 && (
        <div className="pg-sec">
          <div className="t-label">你正在好奇</div>
          <div className="pg-curio">{d.curiosity.map((c, i) => <span key={i} className="pg-cchip">{c}</span>)}</div>
        </div>
      )}

      <div className="pg-foot">基于你的 <span className="num">{d.doc_count}</span> 份文档 + <span className="num">{d.card_count}</span> 张卡片{d.wechat_count > 0 && <> + <span className="num">{d.wechat_count}</span> 位微信联系人</>} · 随大脑生长,画像会变</div>
    </div>
  )
}
