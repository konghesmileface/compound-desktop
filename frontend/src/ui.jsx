import React, { useState, useEffect } from 'react'
import { IconClose } from './icons'

// 全站自主设计的 toast + 确认弹窗(替代原生 alert/confirm)
let listeners = []
const state = { toasts: [], confirm: null }
const emit = () => listeners.forEach((l) => l({ toasts: [...state.toasts], confirm: state.confirm }))
let seq = 0

export function toast(msg, type = 'info') {
  const id = ++seq
  state.toasts = [...state.toasts, { id, msg, type }]
  emit()
  setTimeout(() => { state.toasts = state.toasts.filter((t) => t.id !== id); emit() }, 2800)
}

export function confirmDialog(msg, okText = '确定', danger = false) {
  return new Promise((res) => { state.confirm = { msg, okText, danger, res }; emit() })
}

export function UIHost() {
  const [s, setS] = useState({ toasts: [], confirm: null })
  useEffect(() => { listeners.push(setS); return () => { listeners = listeners.filter((l) => l !== setS) } }, [])
  const done = (v) => { const c = state.confirm; state.confirm = null; emit(); c && c.res(v) }
  return (
    <>
      <div className="toaster">
        {s.toasts.map((t) => (
          <div key={t.id} className={'toast toast-' + t.type}>{t.msg}</div>
        ))}
      </div>
      {s.confirm && (
        <div className="dialog-overlay" onClick={() => done(false)}>
          <div className="dialog glass" onClick={(e) => e.stopPropagation()}>
            <div className="dialog-x" onClick={() => done(false)}><IconClose /></div>
            <div className="dialog-msg">{s.confirm.msg}</div>
            <div className="dialog-actions">
              <button className="btn" onClick={() => done(false)}>取消</button>
              <button className={'btn ' + (s.confirm.danger ? 'btn-danger' : 'btn-primary')} onClick={() => done(true)}>{s.confirm.okText}</button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

// 前端新版本检测:记住当前加载的构建 hash,轮询 index.html 比对,变了就提示刷新。
// dev 模式入口 script 指向 src/main.jsx(无 hash)→ 返回 null → 自动禁用,不打扰开发。
function currentBuildHash() {
  try {
    const s = document.querySelector('script[type="module"][src*="/assets/"]')
    const m = s && s.getAttribute('src').match(/index-([\w-]+)\.js/)
    return m ? m[1] : null
  } catch { return null }
}

export function UpdateBanner() {
  const [stale, setStale] = useState(false)
  useEffect(() => {
    const current = currentBuildHash()
    if (!current) return // dev 或识别不到 hash → 不检测
    let alive = true
    const check = async () => {
      try {
        const r = await fetch('/app/index.html', { cache: 'no-store' })
        if (!r.ok) return
        const html = await r.text()
        const m = html.match(/index-([\w-]+)\.js/)
        if (alive && m && m[1] !== current) setStale(true)
      } catch { /* 离线/抖动忽略,下次再查 */ }
    }
    const t = setInterval(check, 60000)
    const onVis = () => { if (document.visibilityState === 'visible') check() }
    document.addEventListener('visibilitychange', onVis)
    return () => { alive = false; clearInterval(t); document.removeEventListener('visibilitychange', onVis) }
  }, [])
  if (!stale) return null
  return (
    <div className="update-banner" role="status">
      <span className="ub-dot" />
      <span className="ub-text">已发布新版本</span>
      <button className="ub-btn" onClick={() => location.reload()}>刷新升级</button>
    </div>
  )
}

// 定制下拉框(替代原生 select): 玻璃拟态 + 键盘可关 + 点击外部关闭
// 全站统一 loading:三点脉动 + 多阶段文案轮播(慢端点 40s 也不焦虑)
export function Thinking({ text = '正在处理…', hint, phases, className = '' }) {
  const [i, setI] = useState(0)
  useEffect(() => {
    if (!phases || phases.length < 2) return
    const t = setInterval(() => setI((v) => (v + 1) % phases.length), 2200)
    return () => clearInterval(t)
  }, [phases])
  const label = phases && phases.length ? phases[i % phases.length] : text
  return (
    <div className={'thinking ' + className}>
      <div className="thinking-dots"><i /><i /><i /></div>
      <div className="thinking-text" key={label}>{label}</div>
      {hint && <div className="thinking-hint">{hint}</div>}
    </div>
  )
}

// 全站统一空状态:居中 + 图标 + 标题 + 副标题(+可选操作)。loading=true 时图标位显示 spinner。
export function Empty({ icon, title, sub, action, loading = false, className = '' }) {
  return (
    <div className={'empty-state ' + className}>
      <div className={'empty-state-ic' + (loading ? ' loading' : '')}>
        {loading ? <span className="spinner" /> : icon}
      </div>
      {title && <div className="empty-state-t">{title}</div>}
      {sub && <div className="empty-state-s">{sub}</div>}
      {action && <div className="empty-state-act">{action}</div>}
    </div>
  )
}

export function Select({ value, onChange, options, placeholder = '请选择', style }) {
  const [open, setOpen] = useState(false)
  const ref = React.useRef(null)
  useEffect(() => {
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    const k = (e) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', h); document.addEventListener('keydown', k)
    return () => { document.removeEventListener('mousedown', h); document.removeEventListener('keydown', k) }
  }, [])
  const opts = options.map((o) => (typeof o === 'object' ? o : { value: o, label: o }))
  const cur = opts.find((o) => o.value === value)
  return (
    <div className={'csel' + (open ? ' open' : '')} ref={ref} style={style}>
      <button type="button" className="csel-btn" onClick={() => setOpen((v) => !v)}>
        <span className={cur ? '' : 'csel-ph'}>{cur ? cur.label : placeholder}</span>
        <svg className="csel-arrow" width="10" height="6" viewBox="0 0 10 6"><path d="M1 1l4 4 4-4" stroke="currentColor" strokeWidth="1.5" fill="none" /></svg>
      </button>
      {open && (
        <div className="csel-menu">
          <div className={'csel-item' + (!value ? ' on' : '')} onClick={() => { onChange(''); setOpen(false) }}>{placeholder}</div>
          {opts.map((o) => (
            <div key={o.value} className={'csel-item' + (o.value === value ? ' on' : '')} onClick={() => { onChange(o.value); setOpen(false) }}>{o.label}</div>
          ))}
        </div>
      )}
    </div>
  )
}
