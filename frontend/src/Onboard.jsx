import React, { useState } from 'react'

const St = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.7, strokeLinecap: 'round', strokeLinejoin: 'round' }
const IC = {
  brain: (
    <svg viewBox="0 0 24 24" fill="none">
      <path d="M10.2 10.6 6.4 7.6M13.9 10.7 17.5 8M10.5 13.6 7 16.7M13.7 13.5 17 16.3" {...St} strokeWidth="1.4" opacity="0.7" />
      <circle cx="12" cy="12" r="2.4" fill="currentColor" fillOpacity="0.25" /><circle cx="12" cy="12" r="2.4" {...St} />
      <circle cx="5" cy="6.6" r="1.7" {...St} /><circle cx="19" cy="7.2" r="1.7" {...St} />
      <circle cx="6" cy="17.8" r="1.7" {...St} /><circle cx="18.4" cy="17.2" r="1.7" {...St} />
    </svg>
  ),
  ingest: (
    <svg viewBox="0 0 24 24" fill="none">
      <path d="M4.5 13.5h4L9.5 15h5l1-1.5h4v3.8A1.7 1.7 0 0 1 17.8 20H6.2a1.7 1.7 0 0 1-1.7-1.7z" fill="currentColor" fillOpacity="0.22" />
      <path d="M4.5 14v4a1.7 1.7 0 0 0 1.7 1.7h11.6A1.7 1.7 0 0 0 19.5 18v-4" {...St} />
      <path d="M12 3.8v8.4M8.4 8.6 12 12.2l3.6-3.6" {...St} />
    </svg>
  ),
  spark: (
    <svg viewBox="0 0 24 24" fill="none">
      <path d="M11 3.4l1.7 4.9L17.6 10l-4.9 1.7L11 16.6l-1.7-4.9L4.4 10l4.9-1.7z" fill="currentColor" fillOpacity="0.25" />
      <path d="M11 3.4l1.7 4.9L17.6 10l-4.9 1.7L11 16.6l-1.7-4.9L4.4 10l4.9-1.7z" {...St} />
      <path d="M17.6 14.6l.7 2 2 .7-2 .7-.7 2-.7-2-2-.7 2-.7z" fill="currentColor" />
    </svg>
  ),
}

const STEPS = [
  { icon: 'brain', hue: 190, title: '欢迎来到 Compound', body: '你的复利大脑 —— 把你所有的历史(文档、笔记、目标)复利成一个会主动帮你的大脑。你越用,它越懂你。' },
  { icon: 'ingest', hue: 210, title: '先喂它一点东西', body: '去「入库」拖进文档 / 文件夹。你的文件永远只在本地、不上传。库越满,联想和产出越准。', cta: '去入库', tab: 'ingest' },
  { icon: 'spark', hue: 45, title: '它会主动来找你', body: '在「问答」建目标 / 日记卡片。AI 会翻你的全部历史,发现能推进的下一步、到点提醒你 —— 红点,就是它找你了。' },
]

export default function Onboard({ onDone, onGoto }) {
  const [i, setI] = useState(0)
  const s = STEPS[i]; const last = i === STEPS.length - 1
  return (
    <div className="ob-overlay">
      <div className="ob-card glass">
        <div className="ob-brand">Compound</div>
        <div className="ob-ic" style={{ '--h': s.hue }}>{IC[s.icon]}</div>
        <h2 className="ob-title">{s.title}</h2>
        <p className="ob-body">{s.body}</p>
        <div className="ob-dots">{STEPS.map((_, k) => <span key={k} className={'ob-dot' + (k === i ? ' on' : '')} />)}</div>
        <div className="ob-actions">
          {s.cta && <button className="btn ob-btn-2" onClick={() => { onGoto(s.tab); onDone() }}>{s.cta}</button>}
          <button className="btn btn-primary ob-btn-1" onClick={() => last ? onDone() : setI(i + 1)}>{last ? '开始使用' : '下一步'}</button>
        </div>
        <button className="ob-skip" onClick={onDone}>跳过引导</button>
      </div>
    </div>
  )
}
