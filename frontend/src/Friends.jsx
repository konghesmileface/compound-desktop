import React, { useState, useEffect, useRef } from 'react'
import html2canvas from 'html2canvas'
import { api } from './api'
import { IconClose, IconDownload, IconFriends } from './icons'
import { Thinking, Empty } from './ui'
import StarCloud from './StarCloud'
import ErrorBoundary from './ErrorBoundary'
import { toast, confirmDialog } from './ui'

const initial = (s) => ([...(s || '?')][0] || '?').toUpperCase()
const hue = (s) => { let h = 0; for (let i = 0; i < (s || '').length; i++) h = (h * 31 + s.charCodeAt(i)) | 0; return Math.abs(h) % 360 }

function DimBar({ name, score }) {
  const s = Math.max(0, Math.min(100, score || 0))
  return (
    <div className="mr2-dim">
      <span className="mr2-dim-n">{name}</span>
      <span className="mr2-dim-track"><i style={{ width: s + '%' }} /></span>
      <span className="mr2-dim-s">{s}</span>
    </div>
  )
}
function Radar({ dims }) {
  const N = dims.length; if (!N) return null
  // 加宽 viewBox 左右各留 60 单位给标签(避免 html2canvas 按 viewBox 裁掉右侧标签/分数)
  const PAD = 60, W = 264 + PAD * 2, H = 262
  const cx = W / 2, cy = 128, R = 84
  const pt = (i, r) => { const a = -Math.PI / 2 + i * 2 * Math.PI / N; return [cx + Math.cos(a) * r, cy + Math.sin(a) * r] }
  const ring = (f) => dims.map((_, i) => pt(i, R * f).join(',')).join(' ')
  const area = dims.map((d, i) => pt(i, R * Math.max(4, Math.min(100, d.score || 0)) / 100).join(',')).join(' ')
  return (
    <svg className="mr2-radar" viewBox={`0 0 ${W} ${H}`}>
      {[0.25, 0.5, 0.75, 1].map((f, i) => <polygon key={i} points={ring(f)} fill="none" stroke="rgba(255,255,255,0.09)" strokeWidth="1" />)}
      {dims.map((_, i) => { const [x, y] = pt(i, R); return <line key={i} x1={cx} y1={cy} x2={x} y2={y} stroke="rgba(255,255,255,0.08)" strokeWidth="1" /> })}
      <polygon points={area} fill="rgba(139, 140, 255,0.16)" stroke="#8b8cff" strokeWidth="1.6" strokeLinejoin="round" />
      {dims.map((d, i) => { const [x, y] = pt(i, R * Math.max(4, Math.min(100, d.score || 0)) / 100); return <circle key={i} cx={x} cy={y} r="2.6" fill="#a5f3fc" /> })}
      {dims.map((d, i) => { const [x, y] = pt(i, R + 17); const anchor = Math.abs(x - cx) < 6 ? 'middle' : (x < cx ? 'end' : 'start'); return (
        <text key={i} x={x} y={y} textAnchor={anchor} className="mr2-radar-lbl">{d.name}<tspan x={x} dy="12.5" className="mr2-radar-sc">{d.score}</tspan></text>
      ) })}
    </svg>
  )
}
function Section({ title, items, c }) {
  if (!items || !items.length) return null
  return (
    <div className="mr2-sec">
      <div className="mr2-sec-h" style={{ color: c }}>{title}</div>
      {items.map((t, i) => <div key={i} className="mr2-item"><span className="mr2-dot" style={{ background: c }} />{t}</div>)}
    </div>
  )
}

function MatchReport({ me, person, onClose }) {
  const [d, setD] = useState(null); const [err, setErr] = useState(false)
  const [av, setAv] = useState({}); const [saving, setSaving] = useState(false)
  const posterRef = useRef()
  useEffect(() => { setD(null); setErr(false); api.match(person.username).then(setD).catch(() => setErr(true)) }, [person.username])
  useEffect(() => { api.getAvatars([me, person.username].join(',')).then((r) => setAv(r.avatars || {})).catch(() => {}) }, [me, person.username])

  const avImg = (u, disp, love) => (
    <div className={'mr2-av' + (love ? ' love' : '')}>
      {av[u] ? <img className="mr2-avimg" src={av[u]} alt="" crossOrigin="anonymous" /> : <span className="mr2-avletter" style={{ background: `linear-gradient(145deg, hsl(${hue(u)} 50% 58%), hsl(${hue(u)} 55% 40%))` }}>{initial(disp)}</span>}
    </div>
  )
  async function download() {
    if (!posterRef.current || saving) return
    setSaving(true)
    try {
      // 等两帧,确保 compat/百分比等数据已经真正绘制到屏幕上再截图
      await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))
      const el = posterRef.current
      const cv = await html2canvas(el, {
        backgroundColor: '#0a0d16', scale: 2, useCORS: true, logging: false,
        // 按实际内容尺寸截图,避免右侧(雷达标签/分数)被裁
        width: el.scrollWidth, height: el.scrollHeight,
        windowWidth: el.scrollWidth, windowHeight: el.scrollHeight,
        // html2canvas 不支持 background-clip:text —— 会把渐变文字渲染成一个纯色块、
        // 文字本身(如综合契合的百分比数字)因 color:transparent 消失。
        // 在克隆的 DOM 上把这些渐变文字改成实心可见颜色。
        onclone: (doc) => {
          doc.querySelectorAll('.mr2-poster .mr2-score b, .mr2-poster .mr2-headline').forEach((n) => {
            n.style.background = 'none'
            n.style.webkitBackgroundClip = 'border-box'
            n.style.backgroundClip = 'border-box'
            n.style.webkitTextFillColor = ''
            n.style.color = n.classList.contains('mr2-headline') ? '#eaf3ff' : '#8fe6ff'
          })
        },
      })
      const a = document.createElement('a'); a.href = cv.toDataURL('image/png'); a.download = `匹配报告_你x${person.display}.png`; a.click()
      toast('已下载,可分享', 'ok')
    } catch (e) { toast('导出失败', 'err') }
    setSaving(false)
  }
  const love = d && d.love
  return (
    <div className="nd-overlay" onClick={onClose}>
      <div className="mr2-wrap glass" onClick={(e) => e.stopPropagation()}>
        <div className="nd-x" onClick={onClose}><IconClose /></div>
        {!d && !err && <Thinking phases={['正在对照你俩的真实大脑…', '找共同的关注与互补…', '写这份匹配报告…']} hint="基于双方知识库,不套话" />}
        {err && <div className="mr2-loading"><div className="nd-dim">匹配失败,请到设置检查模型 / key</div></div>}
        {d && d.needs_persona && (
          <div className="mr2-loading">
            <div className="e-big">先完善你的人格画像</div>
            <div className="nd-dim" style={{ marginTop: 8 }}>匹配报告需要基于你自己的画像来对照。请先到「探索 · 我的画像」生成人格画像,再回来匹配。</div>
          </div>
        )}
        {d && !d.needs_persona && (<>
          <div className="mr2-poster" ref={posterRef}>
            <div className="mr2-head">
              <div className="mr2-pair">
                <div className="mr2-side">{avImg(me, '你')}<div className="mr2-side-n">你{d.my_mbti && (d.my_mbti_real ? <i>{d.my_mbti}</i> : <i className="mbti-guess" title="AI 从画像推测">{d.my_mbti}<i className="mbti-est">推测</i></i>)}</div></div>
                <div className="mr2-score"><b>{d.compat}</b><span>%</span><em>综合契合</em></div>
                <div className="mr2-side">{avImg(person.username, person.display, true)}<div className="mr2-side-n">{person.display}{person.mbti && (person.mbti_real ? <i>{person.mbti}</i> : <i className="mbti-guess" title="AI 从画像推测">{person.mbti}<i className="mbti-est">推测</i></i>)}</div></div>
              </div>
              <h2 className="mr2-headline">{d.headline || '你俩的匹配'}</h2>
            </div>
            {d.gap_insight && <div className="mr2-gap"><span className="mr2-gap-i">最关键的发现</span>{d.gap_insight}</div>}
            {(d.archetype || d.shadow) && (
              <div className="mr2-arch">
                {d.archetype && <div className="mr2-arch-card on"><div className="mr2-arch-k">关系原型</div><div className="mr2-arch-name">{d.archetype.name}</div><div className="mr2-arch-line">{d.archetype.line}</div></div>}
                {d.shadow && <div className="mr2-arch-card"><div className="mr2-arch-k">压力阴影</div><div className="mr2-arch-name">{d.shadow.name}</div><div className="mr2-arch-line">{d.shadow.line}</div></div>}
              </div>
            )}
            {d.dimensions && d.dimensions.length > 0 && <Radar dims={d.dimensions} />}
            {love && (
              <div className="mr2-love">
                <div className="mr2-love-top"><span>姻缘</span><b>{love.score}</b></div>
                <div className="mr2-love-verdict">{love.verdict}</div>
                <div className="mr2-love-note">{love.note}</div>
              </div>
            )}
            {d.mbti_line && <div className="mr2-mbti">{d.mbti_line}</div>}
            <Section title="同频" items={(d.resonance || []).slice(0, 1)} c="#8b8cff" />
            <Section title="互补" items={(d.complement || []).slice(0, 1)} c="#a78bfa" />
            <Section title="磨合点" items={(d.friction || []).slice(0, 1)} c="#f2a35a" />
            <Section title="相处建议" items={(d.advice || []).slice(0, 1)} c="#f9a8d4" />
            <div className="mr2-brand">Compound · 基于你俩真实的第二大脑</div>
          </div>
          <button className="btn btn-primary mr2-dl" onClick={download} disabled={saving}>{saving ? '生成中…' : <><span className="btn-ico"><IconDownload /></span>下载为图片 · 分享</>}</button>
        </>)}
      </div>
    </div>
  )
}

function Grid({ list, onSel, onRemove }) {
  return (
    <div className="fr-grid">
      {list.map((p) => (
        <div key={p.username} className="fr-card glass" onClick={() => onSel(p)}>
          {onRemove && <span className="fr-del" title="移除好友" onClick={(e) => { e.stopPropagation(); onRemove(p) }}><IconClose /></span>}
          <div className="fr-top">
            <span className="fr-av" style={{ background: `linear-gradient(145deg, hsl(${hue(p.username)} 50% 58%), hsl(${hue(p.username)} 55% 40%))` }}>{initial(p.display)}</span>
            <div className="fr-compat"><div className="fr-ring" style={{ background: `conic-gradient(var(--accent) ${p.compat * 3.6}deg, rgba(255,255,255,0.08) 0)` }}><span className="num">{p.compat}</span></div></div>
          </div>
          <div className="fr-name">{p.display}{p.mbti && <span className={'fr-mbti' + (p.mbti_real ? '' : ' mbti-guess')} title={p.mbti_real ? '本人填写' : 'AI 从画像推测'}>{p.mbti}{p.mbti_real ? '' : <i className="mbti-est">推测</i>}</span>}</div>
          <div className="fr-one">{p.one_liner}</div>
          {p.tags && <div className="fr-tags">{p.tags.slice(0, 3).map((t, i) => <span key={i} className="fr-tag">{t}</span>)}</div>}
        </div>
      ))}
    </div>
  )
}

function DiscoverDrawer({ people, onAdd, onClose }) {
  const [q, setQ] = useState(''); const [busy, setBusy] = useState('')
  useEffect(() => { const h = (e) => { if (e.key === 'Escape') onClose() }; window.addEventListener('keydown', h); return () => window.removeEventListener('keydown', h) }, [onClose])
  const shown = people.filter((p) => !q || (p.display + p.one_liner + (p.tags || []).join('')).toLowerCase().includes(q.toLowerCase()))
  return (
    <div className="nd-overlay" onClick={onClose}>
      <div className="nd-panel dv-panel glass" onClick={(e) => e.stopPropagation()}>
        <div className="nd-x" onClick={onClose}><IconClose /></div>
        <div className="dv-head"><h2>添加好友</h2><p>发起请求后需<b>对方同意</b>才成为好友;同意后才能互相算姻缘 —— 只用双方 AI 画像,<b>不共享任何聊天原文</b>。</p></div>
        <input className="dv-search" placeholder="搜昵称 / 标签…" value={q} onChange={(e) => setQ(e.target.value)} />
        <div className="dv-list">
          {shown.length === 0 && (
            <div className="dv-empty">
              <svg viewBox="0 0 24 24" width="32" height="32"><circle cx="11" cy="11" r="6.5" fill="none" stroke="currentColor" strokeWidth="1.6" /><path d="m16 16 4 4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" /></svg>
              <div>{q ? `没有匹配「${q}」的人` : '暂时没有可添加的人了'}</div>
              {q && <button className="dv-empty-x" onClick={() => setQ('')}>清空搜索</button>}
            </div>
          )}
          {shown.map((p) => (
            <div key={p.username} className="dv-row">
              <span className="fr-av sm" style={{ background: `linear-gradient(145deg, hsl(${hue(p.username)} 50% 58%), hsl(${hue(p.username)} 55% 40%))` }}>{initial(p.display)}</span>
              <div className="dv-info">
                <div className="dv-name">{p.display}{p.mbti && <span className={'fr-mbti' + (p.mbti_real ? '' : ' mbti-guess')} title={p.mbti_real ? '本人填写' : 'AI 从画像推测'}>{p.mbti}{p.mbti_real ? '' : <i className="mbti-est">推测</i>}</span>}<span className="dv-compat num" style={{ color: p.compat >= 60 ? '#34d399' : p.compat >= 40 ? '#fbbf24' : '#8b93f8', borderColor: (p.compat >= 60 ? '#34d399' : p.compat >= 40 ? '#fbbf24' : '#8b93f8') + '55' }} title="预估契合度(基于双方公开画像)">契合 {p.compat}%</span></div>
                <div className="dv-one">{p.one_liner}</div>
              </div>
              <button className="dv-add-btn" disabled={busy === p.username}
                onClick={async () => { setBusy(p.username); try { await onAdd(p) } finally { setBusy('') } }}>
                {busy === p.username ? '…' : '+ 添加'}
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

export default function Friends({ auth }) {
  const [list, setList] = useState(null); const [need, setNeed] = useState(false)
  const [sel, setSel] = useState(null); const [view, setView] = useState('cloud')
  const [discover, setDiscover] = useState(false)
  const [reqs, setReqs] = useState([])   // 收到的好友请求(待同意)
  const hostRef = useRef(); const [dim, setDim] = useState({ w: 800, h: 600 })

  // 只有真·未登录(401)才提示登录;其它错误(空DB/后端慢)显示空列表,不误报"请先登录"
  const reload = () => api.people().then((r) => setList(r.people || [])).catch((e) => {
    if (String(e && e.message) === '401') setNeed(true); else setList([])
  })
  const loadReqs = () => api.friendRequests().then((r) => setReqs(r.incoming || [])).catch(() => {})
  useEffect(() => {
    if (!auth) { setNeed(true); return }
    setNeed(false); reload(); loadReqs()
    const t = setInterval(loadReqs, 30000); return () => clearInterval(t)
  }, [auth])
  // 加好友 = 发请求(要对方同意才成好友、才能算姻缘),不再单方直接加
  const addFriend = async (p) => {
    try {
      const r = await api.friendRequest(p.username)
      if (r && r.already === 'friend') toast(`${p.display} 已是好友`, 'ok')
      else if (r && r.auto_accepted) toast(`已和 ${p.display} 互相成为好友`, 'ok')
      else toast(`已向 ${p.display} 发送好友请求,等 TA 同意`, 'ok')
      setDiscover(false); reload()
    } catch { toast(`请求 ${p.display} 没成功,请稍后再试`, 'err') }
  }
  // 同意/拒绝收到的请求(同意=授权双方用AI画像算姻缘,不共享聊天原文)
  const respondReq = async (from, accept) => {
    if (accept && !(await confirmDialog('同意后,你俩可以互相用 AI 画像算姻缘(只共享 AI 画像,不共享任何聊天原文)。确定同意?', '同意'))) return
    try { await api.friendRespond(from, accept); toast(accept ? '已同意,现在可以互相算姻缘了' : '已拒绝', 'ok'); setReqs((s) => s.filter((x) => x.from !== from)); reload() }
    catch { toast('操作失败,请稍后再试', 'err') }
  }
  const removeFriend = async (p) => {
    if (!(await confirmDialog(`确定删除好友「${p.display}」吗?删除后将不再互相用 AI 画像算姻缘,如需再来需重新加回。`, '删除'))) return
    try { await api.friend(p.username, 'remove'); await reload(); toast(`已移除 ${p.display}`, 'ok') }
    catch { toast(`移除 ${p.display} 没成功,请稍后再试`, 'err') }
  }
  useEffect(() => {
    const el = hostRef.current; if (!el) return
    const ro = new ResizeObserver(() => setDim({ w: el.clientWidth, h: el.clientHeight }))
    ro.observe(el); return () => ro.disconnect()
  }, [view, list])

  if (need) return <div className="view"><div className="empty"><div className="e-big">请先登录</div></div></div>
  if (!list) return <div className="view"><Thinking phases={['正在读大家的知识库…', '计算你和每个人的契合度…']} hint="按真实兴趣与互补匹配" /></div>

  const friends = list.filter((p) => p.is_friend)
  const strangers = list.filter((p) => !p.is_friend)

  return (
    <div className="fr-view">
      <div className="fr-header">
        <div><h1>好友 · 匹配</h1><p>你的人格宇宙。星越近越同频,<b style={{ color: '#f9a8d4' }}>粉线是你的命定星</b>。点星看你俩的同频 / 互补 / 姻缘 —— 全基于真实大脑。</p></div>
        <div className="fr-header-r">
          <button className="btn fr-add-btn" onClick={() => setDiscover(true)}>+ 添加好友</button>
          <div className="seg glass">
            <button className={view === 'cloud' ? 'on' : ''} onClick={() => setView('cloud')}>星云</button>
            <button className={view === 'grid' ? 'on' : ''} onClick={() => setView('grid')}>列表</button>
          </div>
        </div>
      </div>
      {reqs.length > 0 && (
        <div className="fr-reqbar">
          <span className="fr-reqbar-t">好友请求 · {reqs.length}</span>
          {reqs.map((r) => (
            <span key={r.from} className="fr-reqbar-item">
              <b>{r.display}</b> 想加你为好友
              <button className="btn fr-reqbar-btn" onClick={() => respondReq(r.from, false)}>拒绝</button>
              <button className="btn btn-primary fr-reqbar-btn" onClick={() => respondReq(r.from, true)}>同意</button>
            </span>
          ))}
        </div>
      )}
      <div className="fr-body" ref={hostRef}>
        {friends.length === 0
          ? <Empty icon={<IconFriends />} title="还没有好友" sub="点右上「+ 添加好友」,把同频的人拉进你的人格宇宙" action={<button className="btn btn-primary" onClick={() => setDiscover(true)}>去添加</button>} />

          : view === 'cloud'
            ? <ErrorBoundary fallback={<div className="empty"><div className="e-big">星云需要 WebGL</div><div>切到「列表」也能看匹配</div></div>}>
                <StarCloud people={friends} onSelect={setSel} dim={dim} me={auth.username} />
              </ErrorBoundary>
            : <div className="fr-gridwrap"><Grid list={friends} onSel={setSel} onRemove={removeFriend} /></div>}
      </div>
      {sel && <MatchReport me={auth.username} person={sel} onClose={() => setSel(null)} />}
      {discover && <DiscoverDrawer people={strangers} onAdd={addFriend} onClose={() => setDiscover(false)} />}
    </div>
  )
}
