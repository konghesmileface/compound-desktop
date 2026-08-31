import React, { useState } from 'react'
import Ingest from './Ingest'
import Library from './Library'
import Explore from './Explore'
import Home from './Home'
import Persona from './Persona'
import Friends from './Friends'
import Life from './Life'
import Relationships from './Relationships'
import Radar from './Radar'
import Insights from './Insights'
import AskDrawer from './AskDrawer'
import DiscoveryBell from './DiscoveryBell'
import AnalysisStatus from './AnalysisStatus'
import Settings from './Settings'
import Help from './Help'
import Reader from './Reader'
import NodeDetail from './NodeDetail'
import Auth, { AlipayBindModal } from './Auth'
import Landing from './Landing'
import Onboard from './Onboard'
import ModelDownload from './ModelDownload'
import ErrorBoundary from './ErrorBoundary'
import { TrialBanner, PaywallModal } from './Paywall'
import { api } from './api'
import { UIHost, confirmDialog, toast, UpdateBanner } from './ui'
import {
  Logo, IconIngest, IconLibrary, IconExplore, IconAsk, IconPersona, IconFriends, IconLife, IconGallery, IconSettings, IconNetwork, IconRadar, IconInsight, IconHelp, IconPersona as IconUser,
} from './icons'

const TABS = [
  { key: 'home', label: '问答', Icon: IconAsk },
  { key: 'explore', label: '探索', Icon: IconExplore },
  { key: 'persona', label: '画像', Icon: IconPersona },
  { key: 'renmai', label: '人脉', Icon: IconNetwork },
  { key: 'radar', label: '雷达', Icon: IconRadar },
  { key: 'insights', label: '洞察', Icon: IconInsight },
  { key: 'friends', label: '好友', Icon: IconFriends },
  { key: 'life', label: '冥想', Icon: IconLife },
  { key: 'library', label: '文库', Icon: IconLibrary },
  { key: 'ingest', label: '入库', Icon: IconIngest },
  { key: 'help', label: '说明', Icon: IconHelp },
]

const graphFallback = (
  <div className="empty">
    <div className="e-big">星系图需要 WebGL</div>
    <div>请用带硬件加速的现代浏览器打开(文库/入库不受影响)</div>
  </div>
)

export default function App() {
  const [tab, setTab] = useState('home')
  const [openDoc, setOpenDoc] = useState(null)
  const [askQuery, setAskQuery] = useState(null)
  const [askContact, setAskContact] = useState(null)   // 打开某联系人的「问TA分析中枢」
  const [askAction, setAskAction] = useState(null)     // 打开时自动跑的快捷(见面简报/深度分析/产出文档)
  const [askGroup, setAskGroup] = useState(false)      // 该联系人是否群聊(群聊给专属分析)
  // 统一入口:打开某联系人的问TA中枢,可选自动跑一个快捷动作
  const openAsk = (contact, action, isGroup) => { setAskQuery(null); setAskContact(contact); setAskAction(action || null); setAskGroup(!!isGroup) }
  const [nodeDoc, setNodeDoc] = useState(null)
  const [reloadKey, setReloadKey] = useState(0)
  const bump = () => setReloadKey((k) => k + 1)
  const [auth, setAuth] = useState(() => { try { return JSON.parse(localStorage.getItem('auth') || 'null') } catch { return null } })
  const [unread, setUnread] = useState(0)
  const [lifeNew, setLifeNew] = useState(false)   // 冥想有新歌(低调小圆点,非数字角标)
  const [myAvatar, setMyAvatar] = useState(null)
  React.useEffect(() => {
    if (!auth) { setMyAvatar(null); return }
    api.getAvatars(auth.username).then((m) => setMyAvatar((m && m.avatars && m.avatars[auth.username]) || null)).catch(() => {})
    const onAva = (e) => setMyAvatar(e.detail || null)   // 上传头像后即时刷新左下角(不用刷页面)
    window.addEventListener('avatar-updated', onAva)
    return () => window.removeEventListener('avatar-updated', onAva)
  }, [auth])
  const [onboard, setOnboard] = useState(() => localStorage.getItem('onboarded') !== '1' || (typeof window !== 'undefined' && window.location.search.includes('onboard')))
  const finishOnboard = () => { localStorage.setItem('onboarded', '1'); setOnboard(false) }
  const saveAuth = (a) => { setAuth(a); if (a) localStorage.setItem('auth', JSON.stringify(a)); else localStorage.removeItem('auth') }
  // 支付宝扫码回跳:云端 callback 把结果放在 URL hash 里带回
  const [alipayTicket, setAlipayTicket] = useState(null)
  React.useEffect(() => {
    const h = window.location.hash || ''
    if (!h.includes('alipay')) return
    const q = new URLSearchParams(h.slice(1))
    if (q.get('alipay_token')) {
      saveAuth({ token: q.get('alipay_token'), username: q.get('alipay_ident'), nickname: q.get('alipay_nick') || q.get('alipay_ident') })
      toast('支付宝登录成功', 'ok')
    } else if (q.get('alipay_bind')) {
      setAlipayTicket(q.get('alipay_bind'))
    } else if (q.get('alipay_err')) {
      toast('支付宝登录没成功,请重试,或先用验证码/密码登录', 'err')
    }
    window.history.replaceState(null, '', window.location.pathname + window.location.search)
  }, [])
  React.useEffect(() => {
    if (!auth) return
    const poll = () => api.cards().then((r) => setUnread(r.unread_total || 0)).catch(() => {})
    poll(); const t = setInterval(poll, 45000); return () => clearInterval(t)
  }, [auth])
  // 会员/授权:拉试用倒计时状态;监听 402 → 弹订阅墙
  const [account, setAccount] = useState(null)
  const [paywall, setPaywall] = useState(false)
  const paidAtRef = React.useRef(0)   // 刚付款成功的时刻:此后几秒内忽略滞后 402,避免付完又被弹墙
  React.useEffect(() => {
    if (!auth) { setAccount(null); return }
    api.account().then((a) => { setAccount(a); if (a && a.status === 'expired') setPaywall(true) }).catch(() => {})
    // 402 是服务端权威信号(无权限)→ 立即弹墙;仅在付款成功后 12s 内忽略滞后 402
    const onPay = () => { if (Date.now() - paidAtRef.current < 12000) return; setPaywall(true) }
    window.addEventListener('paywall', onPay)
    return () => window.removeEventListener('paywall', onPay)
  }, [auth])
  const refreshAccount = () => api.account().then((a) => { setAccount(a); if (a && a.status === 'expired') setPaywall(true) }).catch(() => {})
  // 单一可靠解锁:付费墙一开着就每 3s 复查账号,一旦变「已付费」立即关闭(支付宝/微信/退款通用);仅 deps=[paywall],不随 account 抖动重置
  React.useEffect(() => {
    if (!paywall) return
    const check = () => api.account(1).then((a) => {
      if (!a) return
      setAccount(a)
      if (a.status === 'paid') { paidAtRef.current = Date.now(); setPaywall(false); toast('已开通,欢迎回来!', 'ok') }
    }).catch(() => {})
    const iv = setInterval(check, 3000)
    const onFocus = () => check()
    window.addEventListener('focus', onFocus)
    return () => { clearInterval(iv); window.removeEventListener('focus', onFocus) }
  }, [paywall])
  // 冥想新歌小圆点:比对曲库最新 key 与已读;打开冥想即清
  React.useEffect(() => {
    if (!auth) return
    const check = () => api.mylibrary().then((d) => {
      const ss = (d && d.songs) || []
      const k = ss.length + ':' + (ss[0] ? (ss[0].date || ss[0].url) : '')
      let seen = ''; try { seen = localStorage.getItem('life_seen_key') || '' } catch (e) { /* noop */ }
      if (tab === 'life') { try { localStorage.setItem('life_seen_key', k) } catch (e) { /* noop */ } setLifeNew(false) }
      else setLifeNew(!!ss.length && k !== seen)
    }).catch(() => {})
    check()
    const iv = setInterval(check, 60000)
    return () => clearInterval(iv)
  }, [auth, tab])
  const displayName = auth ? (auth.nickname || auth.username) : ''

  // ★首启模型门:Windows 瘦身版大模型首次启动才下载。Mac 全打进包→model_status 立即 done→秒过。
  //   端点异常也返回 done(不卡首屏)。检测中极短暂显示空白,再决定是否显示下载页。
  const [modelsReady, setModelsReady] = useState(false)
  const [modelsChecked, setModelsChecked] = useState(false)
  React.useEffect(() => {
    let alive = true
    api.modelStatus()
      .then((s) => { if (alive) { if (s && s.done) setModelsReady(true); setModelsChecked(true) } })
      .catch(() => { if (alive) { setModelsReady(true); setModelsChecked(true) } })
    return () => { alive = false }
  }, [])
  if (!modelsReady) {
    if (!modelsChecked) return null           // 检测中(Mac 立即 done,基本无感)
    return <ModelDownload onDone={() => setModelsReady(true)} />
  }

  // 全局登录门:没登录先看登录/注册,登录后才进 app
  if (!auth) return (<><Landing onAuthed={saveAuth} />{alipayTicket && <AlipayBindModal ticket={alipayTicket} onAuthed={saveAuth} onClose={() => setAlipayTicket(null)} />}{typeof window !== 'undefined' && window.location.search.includes('onboard') && onboard && <Onboard onDone={finishOnboard} onGoto={() => {}} />}<UIHost /><UpdateBanner /></>)

  return (
    <div className="app">
      <nav className="rail">
        <div className="logo"><Logo /></div>
        <div className="nav">
          {TABS.map(({ key, label, Icon }) => (
            <button key={key} className={tab === key ? 'active' : ''} onClick={() => setTab(key)}>
              <Icon /><span className="label">{label}</span>
              {key === 'home' && unread > 0 && <span className="nav-badge">{unread > 99 ? '99+' : unread}</span>}
              {key === 'life' && lifeNew && <span className="nav-dot" title="有新歌" />}
            </button>
          ))}
        </div>
        <div className="rail-spacer" />
        <DiscoveryBell onOpen={setOpenDoc} onAsk={setAskQuery} />
        <div className="rail-user">
          <button className={'rail-user-btn' + (tab === 'account' ? ' active' : '')} onClick={() => setTab('account')} title={displayName + ' · 账户'}>
            {myAvatar
              ? <img className="rail-user-ava" src={myAvatar} alt="" />
              : <span className="rail-user-ava-fallback">{([...(displayName || '?')][0] || '').toUpperCase()}</span>}
            <span className="rail-user-name">{displayName}</span>
          </button>
          <button className={'rail-logout' + (tab === 'settings' ? ' active' : '')} title="设置" onClick={() => setTab('settings')}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" /></svg>
          </button>
          <button className="rail-logout" title="退出登录" onClick={async () => { if (await confirmDialog('退出当前账号?', '退出')) { saveAuth(null); toast('已退出', 'ok') } }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" /><path d="M16 17l5-5-5-5" /><path d="M21 12H9" /></svg>
          </button>
        </div>
      </nav>

      <main className="main">
        <ErrorBoundary key={tab} fallback={<div className="empty" style={{ padding: '60px 20px', textAlign: 'center' }}><div className="e-big">这个页面出了点问题</div><div style={{ color: 'var(--text-3)', marginTop: 8 }}>切到别的页再回来,或刷新一下。你的数据没事。</div></div>}>
        {tab === 'home' && <Home onOpen={setOpenDoc} onUnread={setUnread} />}
        {tab === 'persona' && <Persona />}
        {tab === 'renmai' && <Relationships onOpen={setOpenDoc} onAsk={setAskQuery} onAskContact={openAsk} />}
        {tab === 'radar' && <Radar onOpen={setOpenDoc} onAsk={setAskQuery} />}
        {tab === 'insights' && <Insights onOpen={setOpenDoc} onAsk={setAskQuery} />}
        {tab === 'friends' && <Friends auth={auth} />}
        {tab === 'life' && <Life onGoto={(t) => setTab(t)} />}
        {tab === 'explore' && (
          <ErrorBoundary fallback={graphFallback}><Explore onOpen={setNodeDoc} /></ErrorBoundary>
        )}
        {tab === 'library' && <Library onOpen={setOpenDoc} reloadKey={reloadKey} />}
        {tab === 'ingest' && <Ingest onDone={bump} />}
        {tab === 'help' && <Help />}
        {tab === 'account' && <Settings section="account" auth={auth} onLogout={() => { saveAuth(null); toast('已退出', 'ok') }} onNick={(nick) => saveAuth({ ...auth, nickname: nick })} />}
        {tab === 'settings' && <Settings section="settings" auth={auth} onLogout={() => { saveAuth(null); toast('已退出', 'ok') }} onNick={(nick) => saveAuth({ ...auth, nickname: nick })} />}
        </ErrorBoundary>

        {nodeDoc != null && (
          <NodeDetail docId={nodeDoc} onClose={() => setNodeDoc(null)}
            onOpenReader={(id) => { setNodeDoc(null); setOpenDoc(id) }}
            onOpenNode={(id) => setNodeDoc(id)} />
        )}
        {(askQuery != null || askContact != null) && (
          <AskDrawer query={askQuery} contact={askContact} initialAction={askAction} isGroup={askGroup}
            onClose={() => { setAskQuery(null); setAskContact(null); setAskAction(null); setAskGroup(false) }} onOpenDoc={setOpenDoc} />
        )}
        {/* Reader 必须渲染在问答抽屉之后:从抽屉里点来源联系人打开聊天时要盖在抽屉上面(同 z-index 按 DOM 顺序) */}
        {openDoc != null && (
          <Reader docId={typeof openDoc === 'object' ? openDoc.id : openDoc}
            targetPage={typeof openDoc === 'object' ? (openDoc.page || 0) : 0}
            onClose={() => setOpenDoc(null)} onOpen={setOpenDoc} onAsk={setAskQuery} onAskContact={openAsk} />
        )}
      </main>
      <UIHost />
      <UpdateBanner />
      <AnalysisStatus />
      {onboard && !(account && account.status === 'expired') && <Onboard onDone={finishOnboard} onGoto={(t) => setTab(t)} />}
      <TrialBanner account={account} onUpgrade={() => setPaywall(true)} />
      {paywall && <PaywallModal account={account} onClose={() => setPaywall(false)} onPaid={() => { paidAtRef.current = Date.now(); setAccount((a) => a ? { ...a, status: 'paid', active: true } : a); setPaywall(false); refreshAccount() }} />}
    </div>
  )
}
