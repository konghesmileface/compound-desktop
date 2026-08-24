import React, { useEffect, useState, useRef } from 'react'
import { api } from './api'
import { toast } from './ui'
import { ZODIACS, MBTIS } from './Auth'
import { Select } from './ui'
import { MembershipSection } from './Paywall'

// 密码强度评估(轻量启发式,不引第三方库):长度 + 字符种类 + 惩罚常见弱口令/纯数字/重复。返回 {score:0-4, label, tips}
const COMMON_PW = ['password', '123456', '12345678', '123456789', '111111', '000000', 'qwerty', 'abc123', 'iloveyou', 'admin', '888888', '666666', 'aa123456', 'woaini', '5201314', 'a123456', '123123', 'zxcvbnm']
function pwScore(pw) {
  pw = pw || ''
  if (!pw) return { score: 0, label: '', tips: [] }
  const tips = []
  const lower = /[a-z]/.test(pw), upper = /[A-Z]/.test(pw), digit = /\d/.test(pw), sym = /[^A-Za-z0-9]/.test(pw)
  const classes = [lower, upper, digit, sym].filter(Boolean).length
  const lowered = pw.toLowerCase()
  if (COMMON_PW.some((c) => lowered === c || lowered.includes(c))) return { score: 0, label: '太弱(常见弱口令)', tips: ['别用生日/连号/常见词'] }
  let s = 0
  if (pw.length >= 8) s++
  if (pw.length >= 12) s++
  if (classes >= 2) s++
  if (classes >= 3 && pw.length >= 10) s++
  if (/^(\d+|[a-z]+)$/i.test(pw)) s = Math.min(s, 1)        // 纯数字或纯字母 → 封顶
  if (/(.)\1\1/.test(pw)) s = Math.max(0, s - 1)             // 三连重复扣分
  s = Math.max(0, Math.min(4, s))
  if (pw.length < 8) tips.push('至少 8 位(建议 12 位以上)')
  if (classes < 3) tips.push('混合大小写字母/数字/符号更安全')
  const labels = ['太弱', '弱', '一般', '强', '很强']
  return { score: s, label: labels[s], tips }
}

const myName = () => { try { const a = JSON.parse(localStorage.getItem('auth') || 'null'); return a ? (a.nickname || a.username) : '' } catch { return '' } }
const myUser = () => { try { const a = JSON.parse(localStorage.getItem('auth') || 'null'); return a ? a.username : '' } catch { return '' } }

// model=质量模型默认(交付物/深度),fast=快模型默认(批量抽取/交互,省成本+秒回)。
// alts=下拉候选(只放联网核实过的稳定名,不猜);输入框=datalist 下拉+可手输,必填。
const PROVIDERS = [
  { key: 'deepseek', name: 'DeepSeek', hint: '便宜、中文好。platform.deepseek.com', model: 'deepseek-v4-pro', fast: 'deepseek-v4-flash' },
  { key: 'qwen', name: '通义千问', hint: '阿里。bailian.console.aliyun.com', model: 'qwen-max', fast: 'qwen-flash', alts: ['qwen-plus'] },
  { key: 'doubao', name: '豆包', hint: '字节。模型名多需填你的「接入点ID」', model: 'doubao-pro-32k', fast: 'doubao-lite-32k' },
  { key: 'kimi', name: 'Kimi', hint: '月之暗面。platform.moonshot.cn', model: 'kimi-k2.5', fast: 'kimi-k2.5' },
  { key: 'zhipu', name: '智谱 GLM', hint: 'open.bigmodel.cn。glm-4.5-flash 便宜', model: 'glm-4.6', fast: 'glm-4.5-flash' },
  { key: 'openai', name: 'OpenAI', hint: 'platform.openai.com', model: 'gpt-5', fast: 'gpt-5-mini' },
  { key: 'claude', name: 'Claude', hint: 'Anthropic。opus-4-8 最强 · sonnet-4-6 均衡 · haiku-4-5 最快', model: 'claude-sonnet-4-6', fast: 'claude-haiku-4-5', alts: ['claude-opus-4-8', 'claude-fable-5', 'claude-haiku-4-5'] },
  { key: 'gemini', name: 'Gemini', hint: '谷歌。aistudio.google.com', model: 'gemini-2.5-pro', fast: 'gemini-2.5-flash' },
  { key: 'siliconflow', name: '硅基流动', hint: '一个 key 用众多开源模型。siliconflow.cn', model: 'deepseek-ai/DeepSeek-V3.2', fast: 'Qwen/Qwen3-8B' },
  { key: 'hunyuan', name: '腾讯混元', hint: '腾讯云。cloud.tencent.com/product/hunyuan', model: 'hunyuan-t1-latest', fast: 'hunyuan-lite' },
  { key: 'ollama', name: '本地 Ollama', hint: '全免费离线,需本机装 Ollama', model: 'llama3', fast: 'llama3' },
]
// 该厂商的下拉候选(质量/快默认 + 核实过的备选,去重)
const provModels = (p) => [...new Set([p.model, p.fast, ...(p.alts || [])].filter(Boolean))]

// 模型组合框:点击/聚焦即展开全部选项(原生 datalist 会按已填值过滤,看不到其它),仍可手输任意模型名
function ModelCombo({ value, onChange, options, placeholder }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  useEffect(() => {
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', h); return () => document.removeEventListener('mousedown', h)
  }, [])
  return (
    <div className="model-combo" ref={ref}>
      <input className="search" value={value || ''} placeholder={placeholder}
             onChange={(e) => onChange(e.target.value)} onFocus={() => setOpen(true)} />
      <button type="button" className={'model-combo-caret' + (open ? ' open' : '')} tabIndex={-1} aria-label="展开选项" onClick={() => setOpen((v) => !v)}>▾</button>
      {open && (options || []).length > 0 && (
        <div className="model-combo-menu">
          {options.map((o) => (
            <div key={o} className={'model-combo-opt' + (o === value ? ' on' : '')}
                 onMouseDown={() => { onChange(o); setOpen(false) }}>{o}</div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function Settings({ auth, onLogout, onNick, section = 'all' }) {
  const [cfg, setCfg] = useState({ llm_provider: 'deepseek', llm_key: '', llm_base_url: '', llm_model: '', llm_fast_model: '' })
  const [status, setStatus] = useState(null)
  const [saved, setSaved] = useState(null)
  const [testing, setTesting] = useState(false)
  const [avatar, setAvatar] = useState(null)
  const [nick, setNick] = useState(myName()); const [phone, setPhone] = useState(''); const [savingNick, setSavingNick] = useState(false)
  const [gender, setGender] = useState(''); const [age, setAge] = useState(''); const [zodiac, setZodiac] = useState(''); const [mbti, setMbti] = useState(''); const [bio, setBio] = useState('')
  const [oldPwd, setOldPwd] = useState(''); const [newPwd, setNewPwd] = useState(''); const [newPwd2, setNewPwd2] = useState(''); const [pwdBusy, setPwdBusy] = useState(false)
  async function changePwd() {
    if ((newPwd || '').length < 8) { toast('新密码至少 8 位', 'err'); return }
    if (pwScore(newPwd).score < 2) { toast('密码太弱,请混合大小写/数字/符号,或加长', 'err'); return }
    if (newPwd !== newPwd2) { toast('两次输入的新密码不一致', 'err'); return }
    setPwdBusy(true)
    try { await api.setPassword(oldPwd, newPwd); toast('密码已更新', 'ok'); setOldPwd(''); setNewPwd(''); setNewPwd2('') }
    catch (e) { toast(String(e.message) === '400' ? '原密码不对' : '修改失败,请重试', 'err') }
    setPwdBusy(false)
  }
  const avRef = useRef()

  useEffect(() => {
    const u = myUser(); if (u) api.getAvatars(u).then((r) => setAvatar((r.avatars || {})[u] || null)).catch(() => {})
    api.getProfile().then((p) => {
      setNick(p.nickname || myName()); setPhone(p.phone || '')
      setGender(p.gender || ''); setAge(p.age || ''); setZodiac(p.zodiac || ''); setMbti(p.mbti || ''); setBio(p.bio || '')
    }).catch(() => {})
  }, [])
  async function saveNick() {
    if (!nick.trim()) { toast('昵称不能为空', 'err'); return }
    setSavingNick(true)
    try {
      await api.updateProfile(nick.trim(), { gender, age, zodiac, mbti, bio: bio.trim() })
      onNick && onNick(nick.trim()); toast('资料已更新', 'ok')
    } catch { toast('更新失败', 'err') }
    setSavingNick(false)
  }
  function onPickAvatar(e) {
    const f = e.target.files && e.target.files[0]; if (!f) return
    const rd = new FileReader()
    rd.onload = () => {
      const im = new Image()
      im.onload = () => {
        const S = 256, c = document.createElement('canvas'); c.width = S; c.height = S
        const g = c.getContext('2d'); const s = Math.max(S / im.width, S / im.height)
        g.drawImage(im, S / 2 - im.width * s / 2, S / 2 - im.height * s / 2, im.width * s, im.height * s)
        const dataurl = c.toDataURL('image/jpeg', 0.85)
        api.setAvatar(dataurl).then(() => { setAvatar(dataurl); try { window.dispatchEvent(new CustomEvent('avatar-updated', { detail: dataurl })) } catch (e) { /* noop */ } toast('头像已更新,星云里就是你了', 'ok') }).catch(() => toast('上传失败', 'err'))
      }
      im.src = rd.result
    }
    rd.readAsDataURL(f)
  }

  useEffect(() => {
    api.getSettings().then((s) => {
      setSaved(s)
      const p = PROVIDERS.find((x) => x.key === (s.llm_provider || 'deepseek')) || PROVIDERS[0]
      // 必填:老配置留空的,带入该厂商推荐默认
      setCfg((c) => ({ ...c, llm_provider: p.key, llm_model: s.llm_model || p.model, llm_fast_model: s.llm_fast_model || p.fast || p.model, llm_base_url: s.llm_base_url || '' }))
    }).catch(() => {})
  }, [])

  const prov = PROVIDERS.find((p) => p.key === cfg.llm_provider) || PROVIDERS[0]

  async function save() {
    setStatus(null)
    if (!(cfg.llm_model || '').trim()) { setStatus({ ok: false, msg: '请填写「质量模型」(可从下拉选推荐)' }); return }
    if (!(cfg.llm_fast_model || '').trim()) { setStatus({ ok: false, msg: '请填写「快模型」(可从下拉选推荐)' }); return }
    try { await api.saveSettings(cfg); const s = await api.getSettings(); setSaved(s); setCfg((c) => ({ ...c, llm_key: '' })); setStatus({ ok: true, msg: '已保存' }) }
    catch (e) { setStatus({ ok: false, msg: '保存失败' }) }
  }
  async function test() {
    setTesting(true); setStatus(null)
    try { const r = await api.testSettings(); setStatus(r.ok ? { ok: true, msg: '连通 ✓ 模型回复:' + (r.reply || '') } : { ok: false, msg: '连不通:' + (r.error || '') }) }
    catch { setStatus({ ok: false, msg: '测试失败' }) }
    setTesting(false)
  }

  return (
    <div className="view">
      <div className="view-head">
        <h1>{section === 'settings' ? '设置' : '账户'}</h1>
        <p>{section === 'settings' ? 'AI 模型与识别配置。所有密钥只存在你自己机器,不外传。' : '你的资料、会员订阅与账号安全。'}</p>
      </div>

      {section !== 'settings' && (<>
      <div className="glass set-card">
        <div className="set-card-head">
          <div className="set-sec-h">基本资料</div>
          <button className="btn set-logout" onClick={onLogout}>退出登录</button>
        </div>
        <div className="set-sub">资料会让你的「一生」脚本与主题曲更贴合你本人;MBTI 只用你真实填写的,姻缘报告绝不替你编造。</div>
        <div className="set-profile">
          <div className="set-avatar-col">
            <div className="set-avatar" onClick={() => avRef.current.click()}>
              {avatar ? <img src={avatar} alt="" /> : (
                <svg viewBox="0 0 24 24" width="30" height="30" fill="none" stroke="#06202a" strokeWidth="2" strokeLinecap="round">
                  <circle cx="12" cy="8.2" r="3.6" /><path d="M4.5 20c1.4-3.6 4.2-5.4 7.5-5.4s6.1 1.8 7.5 5.4" />
                </svg>
              )}
              <div className="set-avatar-edit">更换</div>
            </div>
            <div className="set-avatar-hint">点击更换</div>
          </div>
          <div className="set-form">
            <div className="set-form-row">
              <div className="set-field" style={{ flex: '1 1 200px', maxWidth: 280, marginBottom: 0 }}>
                <label>昵称</label>
                <input className="auth-in" style={{ marginBottom: 0 }} value={nick} maxLength={16} onChange={(e) => setNick(e.target.value)} />
              </div>
              <div className="set-field" style={{ marginBottom: 0 }}>
                <label>性别</label>
                <div className="set-gender">
                  <button type="button" className={gender === '男' ? 'on' : ''} onClick={() => setGender('男')}>男</button>
                  <button type="button" className={gender === '女' ? 'on' : ''} onClick={() => setGender('女')}>女</button>
                  <button type="button" className={gender === '其他' ? 'on' : ''} onClick={() => setGender('其他')}>其他</button>
                </div>
              </div>
              <div className="set-field" style={{ width: 90, marginBottom: 0 }}>
                <label>年龄</label>
                <input className="auth-in" style={{ marginBottom: 0 }} placeholder="—" inputMode="numeric" maxLength={3} value={age} onChange={(e) => setAge(e.target.value.replace(/\D/g, ''))} />
              </div>
              <div className="set-field" style={{ flex: '0 1 160px', marginBottom: 0 }}>
                <label>星座</label>
                <Select value={zodiac} onChange={setZodiac} options={ZODIACS} placeholder="未选" />
              </div>
              <div className="set-field" style={{ flex: '0 1 160px', marginBottom: 0 }}>
                <label>MBTI</label>
                <Select value={mbti} onChange={setMbti} options={MBTIS} placeholder="未知" />
              </div>
            </div>
            <div className="set-field" style={{ marginBottom: 0 }}>
              <label>自我介绍(选填,想写多点也行)</label>
              <input className="auth-in" style={{ marginBottom: 0, width: '100%' }} maxLength={200} value={bio} onChange={(e) => setBio(e.target.value)} />
            </div>
            <div className="set-form-foot">
              <span className="set-phone">登录手机号 {phone || '—'}</span>
              <button className="btn btn-primary" disabled={savingNick} onClick={saveNick}>{savingNick ? '保存中…' : '保存资料'}</button>
            </div>
          </div>
        </div>
        <input ref={avRef} type="file" accept="image/*" style={{ display: 'none' }} onChange={onPickAvatar} />
      </div>

      <div className="glass set-card"><MembershipSection /></div>

      <div className="glass set-card">
        <div className="set-sec-h">账号安全</div>
        <div className="set-sub">你的聊天、人脉、文档都是核心隐私 —— 请设一个<b>足够强</b>的密码。设置后可用「密码登录」;忘了也不怕,登录页有验证码重置。</div>
        <div className="set-3col">
          <div className="set-field" style={{ marginBottom: 0 }}>
            <label>原密码</label>
            <input className="auth-in" type="password" style={{ marginBottom: 0 }} placeholder="首次设置留空" value={oldPwd} onChange={(e) => setOldPwd(e.target.value)} />
          </div>
          <div className="set-field" style={{ marginBottom: 0 }}>
            <label>新密码</label>
            <input className="auth-in" type="password" style={{ marginBottom: 0 }} placeholder="至少 8 位" value={newPwd} onChange={(e) => setNewPwd(e.target.value)} />
          </div>
          <div className="set-field" style={{ marginBottom: 0 }}>
            <label>确认新密码</label>
            <input className="auth-in" type="password" style={{ marginBottom: 0 }} placeholder="再输一遍" value={newPwd2} onChange={(e) => setNewPwd2(e.target.value)} />
          </div>
        </div>
        {(() => { const r = pwScore(newPwd); const cls = [newPwd.length >= 8, [/[a-z]/, /[A-Z]/, /\d/, /[^A-Za-z0-9]/].filter((re) => re.test(newPwd)).length >= 2, newPwd.length >= 12]; return (
          <div className="pw-panel">
            {newPwd && (
              <div className="pw-strength">
                <div className="pw-bars">{[0, 1, 2, 3].map((i) => <span key={i} className={'pw-seg' + (i < r.score ? ' on s' + r.score : '')} />)}</div>
                <span className={'pw-label s' + r.score}>{r.label}</span>
              </div>
            )}
            <div className="pw-req">
              <span className={cls[0] ? 'ok' : ''}>{cls[0] ? '✓' : '○'} 至少 8 位</span>
              <span className={cls[1] ? 'ok' : ''}>{cls[1] ? '✓' : '○'} 两类以上字符(大小写/数字/符号)</span>
              <span className={cls[2] ? 'ok' : ''}>{cls[2] ? '✓' : '○'} 12 位以上更佳</span>
              {newPwd2 && <span className={newPwd === newPwd2 ? 'ok' : 'bad'}>{newPwd === newPwd2 ? '✓ 两次一致' : '✕ 两次不一致'}</span>}
            </div>
          </div>
        ) })()}
        <div className="set-form-foot" style={{ marginTop: 14 }}>
          <span className="set-phone">更高级的验证(指纹/Face ID 免密登录、二步验证)即将上线</span>
          <button className="btn btn-primary" disabled={pwdBusy} onClick={changePwd}>{pwdBusy ? '保存中…' : '保存密码'}</button>
        </div>
      </div>
      </>)}

      {section !== 'account' && (
      <div className="glass set-card">
        <div className="set-sec-h">AI 模型 · 自带 key</div>
        <div className="set-sub">选你自己的 AI 模型 —— 本地优先、隐私、BYO。key 只存在本机,不外传。</div>
        <div className="prov-grid">
          {PROVIDERS.map((p) => (
            <div key={p.key} className={'prov-card' + (cfg.llm_provider === p.key ? ' on' : '')}
                 onClick={() => setCfg((c) => ({ ...c, llm_provider: p.key, llm_model: p.model, llm_fast_model: p.fast || p.model }))}>
              <div className="prov-name">{p.name}</div>
              <div className="prov-hint">{p.hint}</div>
            </div>
          ))}
        </div>

        <div className="set-field">
          <label>API Key {saved && saved.has_key && <span className="set-ok">当前:{saved.key_masked}</span>}</label>
          <input className="search" type="password" placeholder={prov.key === 'ollama' ? '本地无需 key' : `粘贴你的 ${prov.name} key(sk-…)`}
                 value={cfg.llm_key} onChange={(e) => setCfg((c) => ({ ...c, llm_key: e.target.value }))} />
        </div>
        <div className="set-twomodel-tip">
          <b>为什么分两个模型?</b> 我们把活儿分两档跑,在<b>不影响质量</b>的前提下给你<b>最省成本、最快</b>的体验:
          <span className="stm-row"><span className="stm-tag stm-q">质量模型</span> 产出交付物(PPT / 报告 / 深度分析)—— 用强模型保证质量</span>
          <span className="stm-row"><span className="stm-tag stm-f">快模型</span> 批量分析(联系人情报 / 主题命名 / 问答)—— 用便宜快模型,秒回又省钱</span>
          <span className="stm-note">都可留空用推荐默认;未来出了新模型,直接填新名字即可,无需等我们更新。</span>
        </div>
        <div className="set-2col">
          <div className="set-field">
            <label>质量模型(交付物)<span className="set-req">必填</span></label>
            <ModelCombo value={cfg.llm_model} onChange={(v) => setCfg((c) => ({ ...c, llm_model: v }))}
                        options={provModels(prov)} placeholder={'点击选择,或手动输入(推荐 ' + prov.model + ')'} />
          </div>
          <div className="set-field">
            <label>快模型(批量 · 省成本)<span className="set-req">必填</span></label>
            <ModelCombo value={cfg.llm_fast_model} onChange={(v) => setCfg((c) => ({ ...c, llm_fast_model: v }))}
                        options={provModels(prov)} placeholder={'点击选择,或手动输入(推荐 ' + (prov.fast || prov.model) + ')'} />
          </div>
        </div>
        <div className="set-field">
          <label>接口地址(可留空用默认;自建/代理才填)</label>
          <input className="search" placeholder="https://api.deepseek.com" value={cfg.llm_base_url} onChange={(e) => setCfg((c) => ({ ...c, llm_base_url: e.target.value }))} />
        </div>

        <div className="set-field" style={{ marginTop: 22, paddingTop: 18, borderTop: '1px solid var(--border)' }}>
          <label style={{ fontWeight: 650, color: 'var(--text-1)' }}>OCR 服务器地址(选填 · 高精度识别)</label>
          <p style={{ fontSize: 12, color: 'var(--text-3)', margin: '4px 0 10px', lineHeight: 1.6 }}>默认用内置轻量 OCR(纯本地、免费、开箱即用)。若你有更强的 OCR 服务(如百度 Unlimited-OCR / 自建 GPU 服务),填入地址即可切换到高精度识别,扫描件/复杂版面更准。留空则用内置。</p>
          <input className="search" placeholder="http://你的OCR服务:端口(留空用内置轻量OCR)" value={cfg.ocr_url || ''} onChange={(e) => setCfg((c) => ({ ...c, ocr_url: e.target.value }))} />
        </div>

        <div style={{ display: 'flex', gap: 10, marginTop: 20, alignItems: 'center' }}>
          <button className="btn btn-primary" onClick={save}>保存</button>
          <button className="btn" onClick={test} disabled={testing}>{testing ? '测试中…' : '测试连通'}</button>
          {status && <span style={{ fontSize: 13, color: status.ok ? 'var(--good)' : 'var(--bad)' }}>{status.msg}</span>}
        </div>
      </div>
      )}
    </div>
  )
}
