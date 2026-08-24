import React from 'react'

export default function ComingSoon({ title, desc, roadmap }) {
  return (
    <div className="view">
      <div className="view-head">
        <h1>{title}</h1>
        <p>{desc}</p>
      </div>
      <div className="empty" style={{ height: '56%' }}>
        <div className="pill" style={{ marginBottom: 14 }}>
          <span className="dot" style={{ background: 'var(--warm)', boxShadow: '0 0 8px var(--warm)' }} />
          即将上线
        </div>
        {roadmap && <div className="e-big">{roadmap}</div>}
      </div>
    </div>
  )
}
