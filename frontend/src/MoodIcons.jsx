// 心情图标:线条小脸 + 微动画(纯 SVG,遵守全站禁 emoji)。
// 每个心情一张脸,animate 的部件带 class,动画在 styles.css 里(悬停/选中更活)。
import React from 'react'

const S = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.7, strokeLinecap: 'round', strokeLinejoin: 'round' }
const dot = (cx, cy) => <circle cx={cx} cy={cy} r="1.1" fill="currentColor" />

// 每个心情:签名色 + 面部 SVG(动画部件带 mi-* class)
// 调亮:暗底上要看得清(疲惫原灰色最不清晰,提亮最多)
export const MOOD_META = {
  开心: { color: '#ffd45e' },
  平静: { color: '#48d6c2' },
  充实: { color: '#74e879' },
  疲惫: { color: '#b09cf0' },
  低落: { color: '#7aa8ff' },
  焦虑: { color: '#ffab63' },
  兴奋: { color: '#ff86b6' },
}

const FACES = {
  开心: (
    <svg viewBox="0 0 24 24" className="mi mi-happy">
      <circle cx="12" cy="12" r="9" {...S} />
      {dot(9, 10)}{dot(15, 10)}
      <path d="M8 13.6 Q12 17 16 13.6" {...S} />
    </svg>
  ),
  平静: (
    <svg viewBox="0 0 24 24" className="mi mi-calm">
      <circle cx="12" cy="12" r="9" {...S} />
      <path d="M8 10.5 h2.2M13.8 10.5 h2.2" {...S} />
      <path d="M9 14.6 Q12 15.6 15 14.6" {...S} />
    </svg>
  ),
  充实: (
    <svg viewBox="0 0 24 24" className="mi mi-full">
      <circle cx="12" cy="12" r="9" {...S} />
      <path d="M8 11 Q9 9.8 10 11M14 11 Q15 9.8 16 11" {...S} />
      <path d="M8.4 14 Q12 16.6 15.6 14" {...S} />
      <path className="mi-spark" d="M18.5 5 l0.7 1.8 1.8 0.7-1.8 0.7-0.7 1.8-0.7-1.8-1.8-0.7 1.8-0.7z" fill="currentColor" stroke="none" />
    </svg>
  ),
  疲惫: (
    <svg viewBox="0 0 24 24" className="mi mi-tired">
      <circle cx="12" cy="12" r="9" {...S} />
      <path d="M8 11.2 Q9 12.2 10 11.2M14 11.2 Q15 12.2 16 11.2" {...S} />
      <path d="M9.6 14.8 h4.8" {...S} />
      <path className="mi-z" d="M14.5 4 h2.6 l-2.6 2.8 h2.6" {...S} strokeWidth="1.3" />
    </svg>
  ),
  低落: (
    <svg viewBox="0 0 24 24" className="mi mi-down">
      <circle cx="12" cy="12" r="9" {...S} />
      {dot(9, 10.6)}{dot(15, 10.6)}
      <path d="M8 15.4 Q12 12.8 16 15.4" {...S} />
      <path className="mi-tear" d="M9 12.4 q1.2 1.6 0 2.6 q-1.2-1-0-2.6z" fill="currentColor" stroke="none" />
    </svg>
  ),
  焦虑: (
    <svg viewBox="0 0 24 24" className="mi mi-anxious">
      <circle cx="12" cy="12" r="9" {...S} />
      <path d="M7.6 8.4 L10 8M14 8 L16.4 8.4" {...S} strokeWidth="1.4" />
      {dot(9, 10.8)}{dot(15, 10.8)}
      <path d="M8.2 14.6 q1-1 2 0 t2 0 t1.6 0" {...S} />
      <path className="mi-sweat" d="M17 8.8 q1.1 1.5 0 2.5 q-1.1-1-0-2.5z" fill="currentColor" stroke="none" />
    </svg>
  ),
  兴奋: (
    <svg viewBox="0 0 24 24" className="mi mi-excited">
      <circle cx="12" cy="12" r="9" {...S} />
      <path d="M7.7 10.4 L9 8.8 10.3 10.4M13.7 10.4 L15 8.8 16.3 10.4" {...S} strokeWidth="1.5" />
      <circle cx="12" cy="14.6" r="2.1" fill="currentColor" />
      <path className="mi-spark" d="M4 5.5 l0.5 1.3 1.3 0.5-1.3 0.5-0.5 1.3-0.5-1.3-1.3-0.5 1.3-0.5z" fill="currentColor" stroke="none" />
      <path className="mi-spark mi-spark2" d="M20 6 l0.5 1.3 1.3 0.5-1.3 0.5-0.5 1.3-0.5-1.3-1.3-0.5 1.3-0.5z" fill="currentColor" stroke="none" />
    </svg>
  ),
}

export function MoodIcon({ mood }) {
  return FACES[mood] || null
}
