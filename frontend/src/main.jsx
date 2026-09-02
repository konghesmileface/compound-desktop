import React, { useState, useEffect } from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource-variable/inter'
import App from './App.jsx'
import { api } from './api'
import './styles.css'

// 桌面版:sidecar 首启要几十秒(Windows/慢机尤甚)。窗口秒出 + 这里轮询 /health,
// 就绪前显示启动 splash,不发业务请求 → 即时反馈、不丢初始请求、不再黑屏干等。
// 网页版(非 Tauri)无本地 sidecar,直接进。
const isTauri = typeof window !== 'undefined' && !!window.__TAURI__

function Splash() {
  return (
    <div style={{ position: 'fixed', inset: 0, display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center', gap: 16, background: '#0a0c12', color: '#cdd6e6' }}>
      <div className="spinner" style={{ width: 30, height: 30 }} />
      <div style={{ fontSize: 15, fontWeight: 600 }}>正在启动本地引擎…</div>
      <div style={{ fontSize: 12.5, color: '#6b7280', maxWidth: 320, textAlign: 'center', lineHeight: 1.7 }}>
        首次打开需加载本地模型,约几十秒;之后会快很多。请勿关闭窗口。
      </div>
    </div>
  )
}

function Boot() {
  const [ready, setReady] = useState(!isTauri)
  useEffect(() => {
    if (!isTauri) return
    let stop = false, n = 0
    const tick = async () => {
      if (stop) return
      if (await api.health()) { setReady(true); return }
      n++
      if (n > 240) { setReady(true); return }   // ~2min 兜底:真起不来也放行(前端各处已有重试/报错)
      setTimeout(tick, 500)
    }
    tick()
    return () => { stop = true }
  }, [])
  return ready ? <App /> : <Splash />
}

createRoot(document.getElementById('root')).render(<Boot />)
