import React, { useState } from 'react'
import { api } from './api'
import { toast } from './ui'

// 极简 markdown 渲染(## 标题 / **加粗** / - 列表)
function renderMd(md) {
  return (md || '').split('\n').map((line, i) => {
    const t = line.trim()
    if (!t) return null
    if (t.startsWith('## ')) return <div key={i} className="rp-h">{t.slice(3)}</div>
    if (t.startsWith('# ')) return <div key={i} className="rp-h">{t.slice(2)}</div>
    const body = t.replace(/^[-*]\s+/, '· ')
    const parts = body.split(/(\*\*[^*]+\*\*)/g).map((p, j) =>
      p.startsWith('**') && p.endsWith('**') ? <b key={j}>{p.slice(2, -2)}</b> : p)
    return <div key={i} className={'rp-p' + (body.startsWith('· ') ? ' li' : '')}>{parts}</div>
  })
}

const MODES = [['summary', '总结'], ['marketing', '营销复盘'], ['weekly', '周报'], ['meeting', '会议纪要']]
const RANGES = [['all', '全部'], ['7', '近7天'], ['30', '近30天'], ['90', '近90天']]

export default function ReportPanel({ contact, onClose, onAsk }) {
  const [mode, setMode] = useState('summary')
  const [range, setRange] = useState('all')
  const [busy, setBusy] = useState(false)
  const [res, setRes] = useState(null)

  const gen = () => {
    setBusy(true); setRes(null)
    const since = range === 'all' ? '' : new Date(Date.now() - Number(range) * 86400000).toISOString().slice(0, 10)
    api.report(contact, mode, since, '').then((r) => { setRes(r); setBusy(false) })
      .catch(() => { setBusy(false); toast('生成失败,请重试', 'err') })
  }
  const copy = () => {
    if (res && res.markdown) { navigator.clipboard.writeText(res.markdown).then(() => toast('已复制', 'ok')).catch(() => {}) }
  }
  const modeLabel = (MODES.find((m) => m[0] === mode) || [])[1]

  return (
    <div className="rp-overlay" onClick={onClose}>
      <div className="rp-panel glass" onClick={(e) => e.stopPropagation()}>
        <div className="rp-head">
          <div><span className="rp-title">产出文档</span><span className="rp-contact">与 {contact}</span></div>
          <button className="rp-close" onClick={onClose}>×</button>
        </div>

        <div className="rp-controls">
          <div className="rp-seg">
            {MODES.map(([k, lab]) => <button key={k} className={mode === k ? 'on' : ''} onClick={() => setMode(k)}>{lab}</button>)}
          </div>
          <div className="rp-seg small">
            {RANGES.map(([k, lab]) => <button key={k} className={range === k ? 'on' : ''} onClick={() => setRange(k)}>{lab}</button>)}
          </div>
          <button className="btn btn-primary rp-gen" disabled={busy} onClick={gen}>{busy ? '生成中…' : '生成' + (modeLabel || '')}</button>
        </div>

        <div className="rp-body">
          {busy && <div className="rp-loading">正在读你和 {contact} 的聊天,生成{modeLabel}…{mode !== 'summary' ? '(pro,约1分钟)' : ''}</div>}
          {!busy && !res && <div className="rp-hint">选类型和时间段,点「生成」。总结秒回;营销复盘/周报/会议纪要用 pro,质量更高。</div>}
          {!busy && res && (
            <div className="rp-result">
              <div className="rp-doc">{renderMd(res.markdown)}</div>
              <div className="rp-acts">
                <button className="rp-act" onClick={copy}>复制</button>
                <button className="rp-act" onClick={gen}>重新生成</button>
                {onAsk && <button className="rp-act primary" onClick={() => { onClose(); onAsk('基于我和' + contact + '的聊天,' + (modeLabel || '总结') + '之后我还想追问:') }}>就这份追问</button>}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
