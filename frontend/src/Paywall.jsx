import React, { useState, useEffect, useRef, useCallback } from 'react'
import { api } from './api'
import { IconClose } from './icons'
import { toast } from './ui'

// 勾:实心圆内白色对勾(SVG,比文字 ✓ 锐利)
const IconCheck = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12.5l4.2 4.3L19 7" /></svg>
)
// 支付宝品牌 logo(蓝底 + 白色“支”字)
const AlipayLogo = () => (
  <svg className="pw-logo" viewBox="0 0 32 32"><rect width="32" height="32" rx="7" fill="#1677FF" />
    <text x="16" y="24" textAnchor="middle" fontSize="21" fontWeight="700" fill="#fff" fontFamily="'PingFang SC','Microsoft YaHei',sans-serif">支</text>
  </svg>
)
// 微信支付品牌 logo(绿底 + 白色双气泡)
const WechatLogo = () => (
  <svg className="pw-logo" viewBox="0 0 32 32"><rect width="32" height="32" rx="7" fill="#07C160" />
    <path d="M13 8.2c-3.6 0-6.5 2.4-6.5 5.4 0 1.7 1 3.3 2.5 4.3l-.6 2 2.3-1.2c.7.2 1.5.3 2.3.3h.5a5 5 0 0 1-.2-1.5c0-3 2.9-5.3 6.4-5.3.3 0 .6 0 .9.05C19.6 9.9 16.6 8.2 13 8.2z" fill="#fff" />
    <path d="M25.5 17.7c0-2.4-2.4-4.4-5.4-4.4s-5.4 2-5.4 4.4 2.4 4.4 5.4 4.4c.7 0 1.3-.1 1.9-.3l1.8 1-.5-1.7c1.3-.8 2.2-2 2.2-3.4z" fill="#fff" />
    <circle cx="10.6" cy="12.4" r=".9" fill="#07C160" /><circle cx="15.4" cy="12.4" r=".9" fill="#07C160" />
    <circle cx="18.3" cy="16.9" r=".8" fill="#07C160" /><circle cx="22.1" cy="16.9" r=".8" fill="#07C160" />
  </svg>
)

// 会员权益点(勾单用)——讲"订阅后你能持续得到什么"
const PERKS = [
  ['问答与洞察不设限', '随时问你的第二大脑,主动发现跨文档线索、承诺与机会'],
  ['每月一部「冥想」短片', 'AI 读懂你这段时间,谱成专属手绘动画 + 主题曲,可下载收藏'],
  ['人脉情报持续更新', '关系卡、见面简报、匹配、群关系图,替你把人脉经营成资产'],
  ['产出交付物', '一键把知识库变成 PPT / Word / Excel,带出处'],
]

function fmtDate(s) {
  if (!s) return ''
  return String(s).slice(0, 10)
}

// 选套餐 + 支付方式(支付宝/微信) + 轮询到账。onPaid:支付成功回调。
function SubscribeFlow({ plans, onPaid, compact, alipayOn = true, wechatOn = false }) {
  const [plan, setPlan] = useState('year')
  const [method, setMethod] = useState(alipayOn ? 'alipay' : 'wechat')
  const [stage, setStage] = useState('choose')   // choose | paying
  const [order, setOrder] = useState(null)
  const [busy, setBusy] = useState(false)
  const pollRef = useRef(null)
  useEffect(() => () => clearInterval(pollRef.current), [])

  const startPoll = (oid) => {
    clearInterval(pollRef.current)
    pollRef.current = setInterval(async () => {
      try {
        const q = await api.payQuery(oid)
        if (q.status === 'paid') { clearInterval(pollRef.current); toast('开通成功,感谢支持!', 'ok'); onPaid && onPaid() }
      } catch { /* noop */ }
    }, 3000)
  }
  // ★Tauri 客户端里 window.open/<a target=_blank> 被 WKWebView 拦(支付宝页弹不出),必须走 open_external
  const openExternal = (url) => {
    if (!url) return
    try {
      if (typeof window !== 'undefined' && window.__TAURI__ && window.__TAURI__.core) {
        window.__TAURI__.core.invoke('open_external', { url }); return
      }
    } catch { /* noop */ }
    try { window.open(url, '_blank') } catch { /* noop */ }
  }
  const startPay = async () => {
    setBusy(true)
    try {
      const r = await api.payCreate(plan, method)
      setOrder(r); setStage('paying')
      if (r.method !== 'wechat') openExternal(r.pay_url)
      startPoll(r.order_id)
    } catch (e) { toast(String(e && e.message) === '402' ? '' : '发起支付失败,请稍后再试', 'err') }
    finally { setBusy(false) }
  }
  const confirmPaid = async () => {
    if (!order) return
    try { const q = await api.payQuery(order.order_id); if (q.status === 'paid') { onPaid && onPaid() } else toast('还没查到到账,支付完成后稍等几秒', 'err') }
    catch { toast('查询失败,请稍后再试', 'err') }
  }

  const pl = (plans && plans.length) ? plans : [{ id: 'year', amount: 199, subject: '年' }, { id: 'month', amount: 29, subject: '月' }]
  const bothPay = alipayOn && wechatOn
  const isWx = order && order.method === 'wechat'
  if (stage === 'paying') {
    return (
      <div className="pw-paying">
        {isWx ? (
          <>
            <div className="pw-paying-t">微信扫码支付 ¥{order && order.amount}</div>
            {order && order.qr_img
              ? <div className="pw-qr"><img src={order.qr_img} alt="微信支付二维码" /></div>
              : <div className="pw-paying-s">二维码生成失败,请重试</div>}
            <div className="pw-paying-s">打开手机微信 › 扫一扫,扫描上方二维码完成付款。付好后这里会自动解锁。</div>
          </>
        ) : (
          <>
            <div className="pw-paying-t">已为你打开支付宝付款页</div>
            <div className="pw-paying-s">在弹出的支付宝页面用手机扫码或登录完成付款(¥{order && order.amount})。付好后这里会自动解锁。</div>
          </>
        )}
        <div className="pw-paying-dots"><span className="thinking-dots mini"><i /><i /><i /></span> 正在等待到账…</div>
        <div className="pw-paying-acts">
          <button className="btn btn-primary" onClick={confirmPaid}>我已完成支付</button>
          <button className="btn" onClick={() => { clearInterval(pollRef.current); setStage('choose') }}>重新选择</button>
        </div>
        {!isWx && <div className="pw-paying-tip">没弹出?<a href="#" onClick={(e) => { e.preventDefault(); order && openExternal(order.pay_url) }}>点这里手动打开支付页</a></div>}
      </div>
    )
  }
  return (
    <div className={'pw-sub' + (compact ? ' compact' : '')}>
      <div className="pw-plans">
        {pl.map((p) => (
          <button key={p.id} className={'pw-plan' + (plan === p.id ? ' on' : '') + (p.id === 'year' ? ' best' : '')} onClick={() => setPlan(p.id)}>
            {p.id === 'year' && <span className="pw-plan-badge">超值</span>}
            <span className="pw-plan-name">{p.id === 'year' ? '年度会员' : '月度会员'}</span>
            <span className="pw-plan-price"><b>¥{p.amount}</b><i>/{p.id === 'year' ? '年' : '月'}</i></span>
            {p.id === 'year' && <span className="pw-plan-sub">≈ ¥{(p.amount / 12).toFixed(0)}/月 · 最划算</span>}
          </button>
        ))}
      </div>
      {bothPay && (
        <div className="pw-methods">
          <button className={'pw-method' + (method === 'alipay' ? ' on' : '')} onClick={() => setMethod('alipay')}>
            <AlipayLogo />支付宝
          </button>
          <button className={'pw-method' + (method === 'wechat' ? ' on' : '')} onClick={() => setMethod('wechat')}>
            <WechatLogo />微信支付
          </button>
        </div>
      )}
      <button className="btn btn-primary pw-pay-btn" disabled={busy} onClick={startPay}>
        {method === 'wechat' ? <WechatLogo /> : <AlipayLogo />}{busy ? '正在发起…' : ((method === 'wechat' ? '微信' : '支付宝') + '支付 · 立即开通')}
      </button>
      <div className="pw-pay-note">桌面端付款:{method === 'wechat' ? '生成二维码后用手机微信扫码' : '点击后打开支付宝页,手机扫码即可'}。支持随时续费。</div>
    </div>
  )
}

// 订阅墙:试用到期/未付费时全屏拦截,友好讲价值 + 直接可付
export function PaywallModal({ account, onClose, onPaid }) {
  const [plans, setPlans] = useState(null)
  const [pay, setPay] = useState({ alipay: true, wechat: false })
  const [closing, setClosing] = useState(false)
  useEffect(() => { api.plans().then((r) => { setPlans(r.plans || []); setPay({ alipay: !!r.alipay_enabled, wechat: !!r.wechat_enabled }) }).catch(() => setPlans([])) }, [])
  const expired = account && account.status === 'expired'
  // 到期=硬墙(不可关,必须订阅);试用主动点开的=可关,带退出动画
  const dismissable = !expired && !!onClose
  const doClose = () => { if (!dismissable || closing) return; setClosing(true); setTimeout(() => onClose && onClose(), 230) }
  return (
    <div className={'pw-overlay' + (closing ? ' pw-closing' : '')} onClick={(e) => { if (dismissable && e.target === e.currentTarget) doClose() }}>
      <div className="pw-modal glass">
        {dismissable && <button className="nd-x" onClick={doClose} aria-label="关闭"><IconClose /></button>}
        <div className="pw-kicker">第二大脑 · 会员</div>
        <h1 className="pw-title">{expired ? '试用已结束,继续解锁你的第二大脑' : '解锁第二大脑的全部能力'}</h1>
        <p className="pw-lead">你已经把资料喂给了它 —— 别停在这里。订阅后,它会持续替你思考、发现、经营,并每月为你谱一部专属短片。</p>
        <div className="pw-perks">
          {PERKS.map(([t, d], i) => (
            <div key={i} className="pw-perk">
              <span className="pw-perk-tick"><IconCheck /></span>
              <div><div className="pw-perk-t">{t}</div><div className="pw-perk-d">{d}</div></div>
            </div>
          ))}
        </div>
        <SubscribeFlow plans={plans} onPaid={onPaid} alipayOn={pay.alipay} wechatOn={pay.wechat} />
      </div>
    </div>
  )
}

// 顶部试用倒计时条(试用中显示;临期变急促)
export function TrialBanner({ account, onUpgrade }) {
  if (!account || account.status !== 'trial') return null
  const d = account.days_left || 0
  const urgent = d <= 2
  return (
    <div className={'trial-bar' + (urgent ? ' urgent' : '')} onClick={onUpgrade}>
      <span className="trial-dot" />
      <span className="trial-txt">试用中 · 还剩 <b>{d}</b> 天{urgent ? ' · 快到期啦' : ''}</span>
      <span className="trial-cta">开通会员 →</span>
    </div>
  )
}

// 设置页 · 会员与订单
export function MembershipSection() {
  const [acc, setAcc] = useState(null)
  const [plans, setPlans] = useState([])
  const [pay, setPay] = useState({ alipay: true, wechat: false })
  const [orders, setOrders] = useState(null)
  const [subOpen, setSubOpen] = useState(false)
  const load = useCallback(() => {
    api.account().then(setAcc).catch(() => {})
    api.plans().then((r) => { setPlans(r.plans || []); setPay({ alipay: !!r.alipay_enabled, wechat: !!r.wechat_enabled }) }).catch(() => {})
    api.orders().then((r) => setOrders(r.orders || [])).catch(() => setOrders([]))
  }, [])
  useEffect(() => { load() }, [load])

  const status = acc ? acc.status : 'trial'
  const HERO = {
    paid: { badge: '会员', title: '会员有效', icon: (<svg viewBox="0 0 24 24" fill="currentColor"><path d="M3 7.5l4.2 3.4L12 4l4.8 6.9L21 7.5 19.4 18H4.6L3 7.5z" /></svg>) },
    trial: { badge: '试用', title: '免费试用中', icon: (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" strokeLinecap="round" /></svg>) },
    expired: { badge: '已过期', title: '试用已结束', icon: (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="4" y="10" width="16" height="10" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3" strokeLinecap="round" /></svg>) },
  }
  const heroSub = () => {
    if (!acc) return '加载中…'
    if (acc.status === 'paid') return '到期 ' + fmtDate(acc.tier_until) + ' · 剩 ' + (acc.days_left || 0) + ' 天'
    if (acc.status === 'trial') return '还剩 ' + (acc.days_left || 0) + ' 天 · 试用到 ' + fmtDate(acc.trial_until)
    return '订阅后继续解锁全部能力,并每月获得一部专属短片'
  }
  const del = async (oid) => {
    try { await api.orderDelete(oid); toast('已删除', 'ok'); load() } catch (e) { toast(String(e && e.message).includes('凭证') ? '已付费订单不能删除' : '删除失败', 'err') }
  }
  const OS = { paid: '已付费', pending: '未付费', canceled: '已取消', refunded: '已退款' }
  const h = HERO[status] || HERO.trial
  return (
    <div className="set-block ms-block">
      <label className="set-blk-t">会员与订阅</label>
      <div className={'ms-hero ms-' + status}>
        <div className="ms-hero-icon">{h.icon}</div>
        <div className="ms-hero-body">
          <div className="ms-hero-top"><span className="ms-hero-badge">{h.badge}</span><span className="ms-hero-title">{h.title}</span></div>
          <div className="ms-hero-sub">{heroSub()}</div>
        </div>
        {status === 'paid'
          ? <button className="btn ms-hero-btn" onClick={() => setSubOpen((v) => !v)}>{subOpen ? '收起' : '续费'}</button>
          : <button className="btn btn-primary ms-hero-btn" onClick={() => setSubOpen((v) => !v)}>{subOpen ? '收起' : '开通会员'}</button>}
      </div>
      {subOpen && <div className="ms-sub"><SubscribeFlow plans={plans} compact onPaid={() => { setSubOpen(false); load() }} alipayOn={pay.alipay} wechatOn={pay.wechat} /></div>}

      <div className="ms-orders-t">订单记录</div>
      {orders === null ? <div className="ms-empty">加载中…</div>
        : orders.length === 0 ? <div className="ms-empty">还没有订单</div>
          : (
            <div className="ms-orders">
              {orders.map((o) => (
                <div key={o.order_id} className="ms-order">
                  <span className={'ms-o-status ms-o-' + o.status}>{OS[o.status] || o.status}</span>
                  <span className="ms-o-subject">{o.subject}</span>
                  <span className="ms-o-amount">¥{o.amount}</span>
                  <span className="ms-o-date">{fmtDate(o.created)}</span>
                  {o.status === 'pending' && <button className="ms-o-del" title="删除订单" onClick={() => del(o.order_id)}><IconClose /></button>}
                </div>
              ))}
            </div>
          )}
    </div>
  )
}
