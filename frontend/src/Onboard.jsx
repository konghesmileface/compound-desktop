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
  key: (
    <svg viewBox="0 0 24 24" fill="none">
      <circle cx="8" cy="9" r="4" fill="currentColor" fillOpacity="0.22" /><circle cx="8" cy="9" r="4" {...St} />
      <path d="M11 11.4 19 19.4M16.4 16.8l2-2M14.2 14.6l2-2" {...St} />
    </svg>
  ),
  persona: (
    <svg viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="8.4" r="3.4" fill="currentColor" fillOpacity="0.22" /><circle cx="12" cy="8.4" r="3.4" {...St} />
      <path d="M5.5 20c0-3.6 2.9-6 6.5-6s6.5 2.4 6.5 6" {...St} />
    </svg>
  ),
}

const STEPS = [
  { icon: 'brain', hue: 190, title: '欢迎来到 Compound', body: '你的复利大脑 —— 把你的聊天、文档、笔记复利成一个会主动帮你的大脑。跟着下面 4 步走,十分钟就能用起来。你越用,它越懂你。' },
  { icon: 'key', hue: 265, title: '第 1 步 · 先配置你的 AI', body: '去「设置」选一家 AI(推荐 DeepSeek,便宜中文好)、填上你的 Key,填完点「测试连通」确认能用。★这是第一件必做的事 —— 没有 AI,画像、问答、产出这些全跑不起来。', cta: '去设置配 AI', tab: 'settings' },
  { icon: 'ingest', hue: 210, title: '第 2 步 · 把你的数据弄进来', body: '去「入库」,三种方式任选:① 微信聊天 —— 装微信同步助手,电脑版微信开着就自动进;② iPhone 老聊天 —— 数据线连手机,一次性把历史补进来;③ 文档 —— 直接拖文件 / 文件夹。数据越多它越懂你,且全程只在本地、绝不上传。', cta: '去入库', tab: 'ingest' },
  { icon: 'persona', hue: 45, title: '第 3 步 · 生成人格画像', body: '去「画像」,让 AI 通读你的数据、读懂你是谁、在意什么。有了画像,好友匹配、冥想主题曲、深度产出才算得准。', cta: '去生成画像', tab: 'persona' },
  { icon: 'spark', hue: 320, title: '第 4 步 · 开始用,它会主动找你', body: '在「问答」建目标 / 日记卡片,AI 翻你全部历史帮你推进;「雷达」盯着承诺与商机;「好友」算姻缘契合;「冥想」为你谱专属主题曲。左侧出现红点,就是它主动来找你了。' },
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
