import React, { useState, useEffect } from 'react'
import { api } from './api'
import { IconClose, Logo } from './icons'
import { toast, Select } from './ui'

const PHONE_RE = /^1[3-9]\d{9}$/
export const ZODIACS = ['白羊座', '金牛座', '双子座', '巨蟹座', '狮子座', '处女座', '天秤座', '天蝎座', '射手座', '摩羯座', '水瓶座', '双鱼座']
export const MBTIS = ['INTJ', 'INTP', 'ENTJ', 'ENTP', 'INFJ', 'INFP', 'ENFJ', 'ENFP', 'ISTJ', 'ISFJ', 'ESTJ', 'ESFJ', 'ISTP', 'ISFP', 'ESTP', 'ESFP']

// 支付宝扫码登录按钮:云端配置好才显示(enabled=false 时整块不渲染,零影响)
function AlipayButton() {
  const [on, setOn] = useState(false)
  useEffect(() => { api.alipayEnabled().then((r) => setOn(!!r.enabled)).catch(() => {}) }, [])
  if (!on) return null
  return (
    <button type="button" className="alipay-btn" onClick={() => {
      api.alipayLoginUrl().then((r) => { window.location.href = r.url }).catch(() => toast('支付宝登录暂不可用', 'err'))
    }}>
      <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3.5" y="3.5" width="6" height="6" rx="1.2" /><rect x="14.5" y="3.5" width="6" height="6" rx="1.2" />
        <rect x="3.5" y="14.5" width="6" height="6" rx="1.2" /><path d="M14.5 14.5h2.5v2.5h-2.5zM18.5 14.5h2v2h-2zM14.5 18.5h2v2h-2zM18 18h2.5v2.5" />
      </svg>
      支付宝扫码登录
    </button>
  )
}

// 首次支付宝登录:绑定手机号(验证码),之后扫码直登
export function AlipayBindModal({ ticket, onAuthed, onClose }) {
  const [phone, setPhone] = useState(''); const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false); const [cd, setCd] = useState(0)
  useEffect(() => { if (cd <= 0) return; const t = setTimeout(() => setCd((c) => c - 1), 1000); return () => clearTimeout(t) }, [cd])
  async function getCode() {
    if (!PHONE_RE.test(phone)) { toast('请输入正确的手机号', 'err'); return }
    try { await api.sendCode(phone); setCd(60); toast('验证码已发送', 'ok') } catch (e) { toast(String(e && e.message) === '429' ? '请求太频繁,请稍后再试' : '发送失败,稍后再试', 'err') }
  }
  async function submit() {
    if (!PHONE_RE.test(phone)) { toast('请输入正确的手机号', 'err'); return }
    if (!code.trim()) { toast('请输入验证码', 'err'); return }
    setBusy(true)
    try {
      const r = await api.alipayBind(ticket, phone, code.trim())
      toast('绑定成功,已登录', 'ok')
      onAuthed({ token: r.token, username: r.username, nickname: r.nickname })
      onClose && onClose()
    } catch (e) {
      toast(String(e.message) === '400' ? '验证码不对,或绑定会话已过期(可重新扫码)' : '绑定失败,请重试', 'err')
    }
    setBusy(false)
  }
  return (
    <div className="guide-overlay" onClick={onClose}>
      <div className="auth-gate-card glass" style={{ maxWidth: 400, position: "relative" }} onClick={(e) => e.stopPropagation()}>
        <div className="x" onClick={onClose}><IconClose /></div>
        <h2 style={{ marginBottom: 6 }}>绑定手机号</h2>
        <p style={{ fontSize: 12.5, color: 'var(--text-3)', margin: '0 0 14px', lineHeight: 1.65 }}>支付宝扫码成功。首次使用需要绑定你的手机号(账号以手机号为准),以后扫码即可直接登录。</p>
        <input className="auth-in" placeholder="手机号" inputMode="numeric" maxLength={11} value={phone} onChange={(e) => setPhone(e.target.value.replace(/\D/g, ''))} autoFocus />
        <div className="auth-coderow">
          <input className="auth-in" placeholder="短信验证码" inputMode="numeric" maxLength={6} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))} onKeyDown={(e) => { if (e.key === 'Enter') submit() }} />
          <button className="auth-code-btn" disabled={cd > 0} onClick={getCode}>{cd > 0 ? cd + 's' : '获取验证码'}</button>
        </div>
        <button className="btn btn-primary" style={{ width: '100%', marginTop: 4 }} disabled={busy} onClick={submit}>{busy ? '…' : '绑定并登录'}</button>
      </div>
    </div>
  )
}

export function Form({ onAuthed, onClose, registerOnly, onRegistered }) {
  const [mode, setMode] = useState(registerOnly ? 'register' : 'login')
  const [phone, setPhone] = useState(''); const [code, setCode] = useState(''); const [nick, setNick] = useState('')
  const [busy, setBusy] = useState(false); const [cd, setCd] = useState(0)
  const [gender, setGender] = useState(''); const [age, setAge] = useState('')
  const [zodiac, setZodiac] = useState(''); const [mbti, setMbti] = useState(''); const [bio, setBio] = useState('')
  const [pwd, setPwd] = useState(''); const [forgot, setForgot] = useState(false); const [newPwd, setNewPwd] = useState('')

  useEffect(() => { if (cd <= 0) return; const t = setTimeout(() => setCd((c) => c - 1), 1000); return () => clearTimeout(t) }, [cd])

  async function getCode() {
    if (!PHONE_RE.test(phone)) { toast('请输入正确的手机号', 'err'); return }
    try {
      const r = await api.sendCode(phone); setCd(60)
      if (r && r.dev_code) toast('验证码 ' + r.dev_code + '(开发模式,真短信接阿里云后自动发)', 'ok')
      else toast('验证码已发送', 'ok')
    } catch (e) { toast(String(e && e.message) === '429' ? '请求太频繁,请稍后再试' : '发送失败,请重试', 'err') }
  }
  async function submit() {
    if (!PHONE_RE.test(phone)) { toast('请输入正确的手机号', 'err'); return }
    if (mode === 'pwd' && !forgot) {
      if (!pwd) { toast('请输入密码', 'err'); return }
      setBusy(true)
      try {
        const r = await api.pwdLogin(phone, pwd)
        if (r && r.token) { toast('已登录', 'ok'); onAuthed({ token: r.token, username: r.username, nickname: r.nickname }); onClose && onClose() }
      } catch (e) { toast(String(e.message) === '400' ? '手机号或密码不对(也可以用验证码登录)' : '登录失败,请重试', 'err') }
      setBusy(false); return
    }
    if (mode === 'pwd' && forgot) {
      if ((code || '').trim().length < 4) { toast('请输入验证码', 'err'); return }
      if ((newPwd || '').length < 6) { toast('新密码至少 6 位', 'err'); return }
      setBusy(true)
      try {
        const r = await api.resetPassword(phone, code.trim(), newPwd)
        if (r && r.token) { toast('密码已重置并登录', 'ok'); onAuthed({ token: r.token, username: r.username, nickname: r.nickname }); onClose && onClose() }
      } catch { toast('验证码错误或已过期', 'err') }
      setBusy(false); return
    }
    if ((code || '').trim().length < 4) { toast('请输入验证码', 'err'); return }
    if (mode === 'register' && !nick.trim()) { toast('请填个昵称', 'err'); return }
    setBusy(true)
    try {
      const r = await (mode === 'register' ? api.phoneRegister(phone, code.trim(), nick.trim(), gender, age, zodiac, mbti, bio.trim()) : api.phoneLogin(phone, code.trim()))
      if (r && r.token) {
        if (mode === 'register' && onRegistered) { toast('注册成功', 'ok'); onRegistered({ username: r.username || phone, nickname: r.nickname || nick.trim() }); setBusy(false); return }
        toast(mode === 'register' ? '注册成功' : '已登录', 'ok'); onAuthed({ token: r.token, username: r.username, nickname: r.nickname }); onClose && onClose()
      }
    } catch { toast(mode === 'register' ? '注册失败(手机号可能已注册)' : '验证码错误或已过期', 'err') }
    setBusy(false)
  }
  return (
    <>
      {!registerOnly && (
        <div className="auth-tabs">
          <button className={mode === 'login' ? 'on' : ''} onClick={() => setMode('login')}>验证码登录</button>
          <button className={mode === 'pwd' ? 'on' : ''} onClick={() => setMode('pwd')}>密码登录</button>
          <button className={mode === 'register' ? 'on' : ''} onClick={() => setMode('register')}>注册</button>
        </div>
      )}
      <input className="auth-in" placeholder="手机号" inputMode="numeric" maxLength={11} value={phone} onChange={(e) => setPhone(e.target.value.replace(/\D/g, ''))} autoFocus />
      {(mode !== 'pwd' || forgot) && (
        <div className="auth-coderow">
          <input className="auth-in" placeholder="短信验证码" inputMode="numeric" maxLength={6} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))} onKeyDown={(e) => { if (e.key === 'Enter') submit() }} />
          <button className="auth-code-btn" disabled={cd > 0} onClick={getCode}>{cd > 0 ? cd + 's' : '获取验证码'}</button>
        </div>
      )}
      {mode === 'pwd' && !forgot && (
        <input className="auth-in" type="password" placeholder="密码" value={pwd} onChange={(e) => setPwd(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') submit() }} />
      )}
      {mode === 'pwd' && forgot && (
        <input className="auth-in" type="password" placeholder="设个新密码(至少 6 位)" value={newPwd} onChange={(e) => setNewPwd(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') submit() }} />
      )}
      {mode === 'register' && <input className="auth-in" placeholder="给自己起个昵称" maxLength={16} value={nick} onChange={(e) => setNick(e.target.value)} />}
      {mode === 'register' && (
        <div className="auth-ga">
          <div className="auth-gender">
            <button type="button" className={gender === '男' ? 'on' : ''} onClick={() => setGender('男')}>男</button>
            <button type="button" className={gender === '女' ? 'on' : ''} onClick={() => setGender('女')}>女</button>
          </div>
          <input className="auth-in auth-age" placeholder="年龄" inputMode="numeric" maxLength={3} value={age} onChange={(e) => setAge(e.target.value.replace(/\D/g, ''))} />
        </div>
      )}
      {mode === 'register' && (
        <div className="auth-ga">
          <Select value={zodiac} onChange={setZodiac} options={ZODIACS} placeholder="星座(选填)" />
          <Select value={mbti} onChange={setMbti} options={MBTIS} placeholder="MBTI(选填)" />
        </div>
      )}
      {mode === 'register' && <input className="auth-in" placeholder="自我介绍(选填,想写多点也行)" maxLength={200} value={bio} onChange={(e) => setBio(e.target.value)} />}
      <button className="btn btn-primary" style={{ width: '100%', marginTop: 4 }} disabled={busy} onClick={submit}>{busy ? '…' : (mode === 'register' ? (registerOnly ? '注册,开启我的第二大脑' : '注册') : (mode === 'pwd' && forgot ? '重置密码并登录' : '登录'))}</button>
      {/* 支付宝扫码登录暂时隐藏(用户令):客户端需 ticket 轮询流(云端+客户端两头),待单独实现。
          现用手机验证码/密码登录。要恢复:把下行的 false && 去掉。 */}
      {false && !registerOnly && <AlipayButton />}
      {mode === 'pwd' && (
        <div style={{ marginTop: 10, textAlign: 'right' }}>
          <button type="button" style={{ background: 'none', border: 'none', color: '#67a6c9', fontSize: 12.5, cursor: 'pointer' }} onClick={() => setForgot((v) => !v)}>{forgot ? '← 返回密码登录' : '忘记密码?用验证码重置'}</button>
        </div>
      )}
      <div className="auth-hint">{registerOnly ? '注册后,下载客户端,用这个手机号在你自己的电脑上登录使用 —— 你的文档只存在你自己的电脑里,永不上传。' : '未注册的手机号,验证码正确会直接登录。你的文档永远只在本地,不会上传。'}</div>
    </>
  )
}

export default function Auth({ onClose, onAuthed, gate }) {
  if (gate) {
    return (
      <div className="auth-gate">
        <div className="auth-gate-card glass">
          <div className="auth-logo"><Logo /></div>
          <h1 className="auth-brand">Compound</h1>
          <p className="auth-tag">你的复利大脑 —— 把你所有的历史,复利成产出机与灵感源。</p>
          <div style={{ marginTop: 24 }}><Form onAuthed={onAuthed} /></div>
        </div>
      </div>
    )
  }
  return (
    <div className="guide-overlay" onClick={onClose}>
      <div className="guide glass" onClick={(e) => e.stopPropagation()} style={{ width: 400 }}>
        <div className="x" onClick={onClose}><IconClose /></div>
        <Form onAuthed={onAuthed} onClose={onClose} />
      </div>
    </div>
  )
}
