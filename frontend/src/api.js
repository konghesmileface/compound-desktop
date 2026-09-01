// API 地址:网页版同源(base=''),桌面版指向本机 sidecar 或云端。
// __COMPOUND_API_BASE__ 由 Tauri 壳注入(本机 sidecar 端口);VITE_API_BASE 打包期兜底(如云端)。
// 用模块级 fetch 影子:本模块内所有 fetch('/api/..') 自动前缀 base,零改调用点。
const API_BASE = (typeof window !== 'undefined' && window.__COMPOUND_API_BASE__)
  || (import.meta.env && import.meta.env.VITE_API_BASE) || ''
const fetch = (input, init) => window.fetch(typeof input === 'string' ? API_BASE + input : input, init)

// 同源调用后端(前端由 FastAPI 挂在 /app,API 在 /api,同一个 origin)
const j = (r) => {
  if (r.status === 401) {   // token 失效(如账号系统升级后的旧登录)→ 自动登出,干净地回登录页
    try { localStorage.removeItem('auth') } catch { /* noop */ }
    if (!location.pathname.endsWith('/login')) location.reload()
    throw new Error('401')
  }
  if (r.status === 402) {   // 试用到期/未付费 → 全局弹订阅墙(App 监听 paywall 事件)
    try { window.dispatchEvent(new CustomEvent('paywall')) } catch { /* noop */ }
    throw new Error('402')
  }
  if (!r.ok) throw new Error(r.status)
  return r.json()
}
const authHeaders = () => { try { const a = JSON.parse(localStorage.getItem('auth') || 'null'); return a && a.token ? { Authorization: 'Bearer ' + a.token } : {} } catch { return {} } }

// ★Tauri WKWebView 里 <a href download>/window.open 都被拦(下载不触发、相对/api打不到sidecar)。
//   下载/外链统一走这个:补全 API_BASE(sidecar 真实地址)→ Tauri 用 open_external 交给系统浏览器下,
//   web 端 window.open 打开(/api/download 带 attachment 头 → 浏览器直接下)。
// 把相对 /api 路径补成 sidecar 全地址(Tauri 里 <audio src>/<img src> 相对路径打不到后端;web 端 API_BASE 为空不变)。
export function apiUrl(path) {
  if (!path) return path
  return /^https?:|^data:|^blob:/i.test(path) ? path : (API_BASE + path)
}

export function openExternal(url) {
  if (!url) return
  const full = /^https?:/i.test(url) ? url : (API_BASE + url)
  try {
    if (typeof window !== 'undefined' && window.__TAURI__ && window.__TAURI__.core) {
      window.__TAURI__.core.invoke('open_external', { url: full }); return
    }
  } catch { /* noop */ }
  try { window.open(full, '_blank') } catch { /* noop */ }
}

export const api = {
  modelStatus: () => fetch('/api/model_status').then(j),
  stats: () => fetch('/api/stats', { headers: authHeaders() }).then(j),
  library: () => fetch('/api/library', { headers: authHeaders() }).then(j),
  doc: (id, offset = 0, limit = 40) => fetch(`/api/doc/${id}?offset=${offset}&limit=${limit}`, { headers: authHeaders() }).then(j),
  search: (q) => fetch(`/api/search?q=${encodeURIComponent(q)}`, { headers: authHeaders() }).then(j),
  graph: () => fetch('/api/graph', { headers: authHeaders() }).then(j),
  starmap: (chunk = 12) => fetch(`/api/starmap?chunk=${chunk}`, { headers: authHeaders() }).then(j),
  similar: (id) => fetch(`/api/similar/${id}`, { headers: authHeaders() }).then(j),
  docSummary: (id) => fetch(`/api/doc_summary/${id}`, { headers: authHeaders() }).then(j),
  chatNode: (id) => fetch(`/api/chat_node/${id}`, { headers: authHeaders() }).then(j),
  connections: (id) => fetch(`/api/connections/${id}`, { headers: authHeaders() }).then(j),
  mediaStructure: (id) => fetch(`/api/media_structure?doc_id=${id}`, { headers: authHeaders() }).then(j),
  persona: (refresh) => fetch('/api/persona' + (refresh ? '?refresh=1' : ''), { headers: authHeaders() }).then(j),
  sendCode: (phone) => fetch('/api/auth/send_code', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ phone }) }).then(j),
  phoneRegister: (phone, code, nickname, gender, age, zodiac, mbti, bio) => fetch('/api/auth/phone_register', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ phone, code, nickname, gender, age, zodiac, mbti, bio }) }).then(j),
  pwdLogin: (phone, password) => fetch('/api/auth/pwd_login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ phone, password }) }).then(j),
  setPassword: (oldPwd, newPwd) => fetch('/api/auth/set_password', { method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() }, body: JSON.stringify({ old: oldPwd, new: newPwd }) }).then(j),
  resetPassword: (phone, code, newPwd) => fetch('/api/auth/reset_password', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ phone, code, new: newPwd }) }).then(j),
  alipayEnabled: () => fetch('/api/auth/alipay/enabled').then(j),
  alipayLoginUrl: () => fetch('/api/auth/alipay/login_url').then(j),
  alipayBind: (ticket, phone, code) => fetch('/api/auth/alipay/bind', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ticket, phone, code }) }).then(j),
  phoneLogin: (phone, code) => fetch('/api/auth/phone_login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ phone, code }) }).then(j),
  people: () => fetch('/api/people', { headers: authHeaders() }).then(j),
  friend: (username, action = 'add') => fetch('/api/friend', { method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() }, body: JSON.stringify({ username, action }) }).then(j),
  // ★好友社交(走云:手机号加+对方同意+画像共享算姻缘)
  friendRequest: (to) => fetch('/api/friend/request', { method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() }, body: JSON.stringify({ to }) }).then(j),
  friendRequests: () => fetch('/api/friend/requests', { headers: authHeaders() }).then(j),
  friendRespond: (from, accept) => fetch('/api/friend/respond', { method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() }, body: JSON.stringify({ from, accept }) }).then(j),
  friendList: () => fetch('/api/friend/list', { headers: authHeaders() }).then(j),
  friendRemove: (other) => fetch('/api/friend/remove', { method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() }, body: JSON.stringify({ other }) }).then(j),
  match: (u, refresh) => fetch('/api/match/' + encodeURIComponent(u) + (refresh ? '?refresh=1' : ''), { headers: authHeaders() }).then(j),
  lifestory: (refresh, style) => fetch('/api/lifestory?' + (refresh ? 'refresh=1&' : '') + 'style=' + (style || 'cinema'), { headers: authHeaders() }).then(j),
  songMake: (force) => fetch('/api/song/make' + (force ? '?force=1' : ''), { method: 'POST', headers: authHeaders() }).then(j),
  songStatus: () => fetch('/api/song/status', { headers: authHeaders() }).then(j),
  lifesong: (refresh) => fetch('/api/lifesong' + (refresh ? '?refresh=1' : ''), { headers: authHeaders() }).then(j),   // ★补:Life.jsx 调 api.lifesong 但之前没定义→冥想tab崩(api.lifesong is not a function)
  mylibrary: () => fetch('/api/mylibrary', { headers: authHeaders() }).then(j),
  today: (refresh) => fetch('/api/today' + (refresh ? '?refresh=1' : ''), { headers: authHeaders() }).then(j),
  links: () => fetch('/api/links', { headers: authHeaders() }).then(j),
  entityLinks: () => fetch('/api/entity_links', { headers: authHeaders() }).then(j),
  relationships: (refresh) => fetch('/api/relationships' + (refresh ? '?refresh=1' : ''), { headers: authHeaders() }).then(j),
  relGraph: () => fetch('/api/rel_graph', { headers: authHeaders() }).then(j),
  relPath: (a, b) => fetch('/api/rel_path?a=' + encodeURIComponent(a) + '&b=' + encodeURIComponent(b), { headers: authHeaders() }).then(j),
  commitments: (refresh) => fetch('/api/commitments' + (refresh ? '?refresh=1' : ''), { headers: authHeaders() }).then(j),
  dismissCommitment: (key) => fetch('/api/commitments/dismiss', { method: 'POST', headers: { ...authHeaders(), 'Content-Type': 'application/json' }, body: JSON.stringify({ key }) }).then(j),
  dismissLoop: (contact, text) => fetch('/api/loops/dismiss', { method: 'POST', headers: { ...authHeaders(), 'Content-Type': 'application/json' }, body: JSON.stringify({ contact, text }) }).then(j),
  dismissReach: (contact) => fetch('/api/reach/dismiss', { method: 'POST', headers: { ...authHeaders(), 'Content-Type': 'application/json' }, body: JSON.stringify({ contact }) }).then(j),
  groupGraph: (contact, refresh) => fetch('/api/group_graph?contact=' + encodeURIComponent(contact) + (refresh ? '&refresh=1' : ''), { headers: authHeaders() }).then(j),
  chatGalaxy: () => fetch('/api/chat_galaxy', { headers: authHeaders() }).then(j),
  chatTopicGalaxy: () => fetch('/api/chat_topic_galaxy', { headers: authHeaders() }).then(j),
  relationTimeline: (contact, refresh) => fetch('/api/relation_timeline?contact=' + encodeURIComponent(contact) + (refresh ? '&refresh=1' : ''), { headers: authHeaders() }).then(j),
  numberLedger: (refresh) => fetch('/api/number_ledger' + (refresh ? '?refresh=1' : ''), { headers: authHeaders() }).then(j),
  matches: (refresh) => fetch('/api/matches' + (refresh ? '?refresh=1' : ''), { headers: authHeaders() }).then(j),
  briefing: (contact) => fetch('/api/briefing?contact=' + encodeURIComponent(contact), { headers: authHeaders() }).then(j),
  cooling: () => fetch('/api/cooling', { headers: authHeaders() }).then(j),
  favors: () => fetch('/api/favors', { headers: authHeaders() }).then(j),
  dormant: () => fetch('/api/dormant', { headers: authHeaders() }).then(j),
  balance: () => fetch('/api/balance', { headers: authHeaders() }).then(j),
  panorama: () => fetch('/api/panorama', { headers: authHeaders() }).then(j),
  checkup: () => fetch('/api/checkup', { headers: authHeaders() }).then(j),
  draftReply: (contact, incoming) => fetch('/api/draft_reply', { method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() }, body: JSON.stringify({ contact, incoming }) }).then(j),
  wechatWatch: () => fetch('/api/wechat/watch', { method: 'POST', headers: authHeaders() }).then(j),
  iphoneImport: () => fetch('/api/iphone/import', { method: 'POST', headers: authHeaders() }).then(j),   // 启动iOS历史导入(后台跑,轮询ingestProgress看进度)
  iphoneStatus: () => fetch('/api/iphone/status', { headers: authHeaders() }).then(j),                   // iOS导入环境:tool_ready/connected/running
  realtimeStatus: () => fetch('/api/realtime/status', { headers: authHeaders() }).then(j),
  realtimeToggle: (enabled) => fetch('/api/realtime/toggle', { method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() }, body: JSON.stringify({ enabled }) }).then(j),
  ingestProgress: () => fetch('/api/ingest/progress', { headers: authHeaders() }).then(j),
  discoveries: () => fetch('/api/discoveries', { headers: authHeaders() }).then(j),
  deepen: (contact) => fetch('/api/relationships/deepen', { method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() }, body: JSON.stringify({ contact }) }).then(j),
  portrait: (refresh) => fetch('/api/network_portrait' + (refresh ? '?refresh=1' : ''), { headers: authHeaders() }).then(j),
  report: (contact, mode, since, until) => fetch('/api/report', { method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() }, body: JSON.stringify({ contact, mode, since, until }) }).then(j),
  wechatMessages: (contact, offset = 0, limit = 300) => fetch('/api/wechat_messages?contact=' + encodeURIComponent(contact) + '&offset=' + offset + '&limit=' + limit, { headers: authHeaders() }).then(j),
  deleteCard: (contact) => fetch('/api/relationships/delete', { method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() }, body: JSON.stringify({ contact }) }).then(j),
  analysisStatus: () => fetch('/api/analysis_status', { headers: authHeaders() }).then(j),
  news: () => fetch('/api/news', { headers: authHeaders() }).then(j),
  setAvatar: (dataurl) => fetch('/api/avatar', { method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() }, body: JSON.stringify({ dataurl }) }).then(j),
  getAvatars: (users) => fetch('/api/avatars?users=' + encodeURIComponent(users), { headers: authHeaders() }).then(j),
  getProfile: () => fetch('/api/auth/profile', { headers: authHeaders() }).then(j),
  updateProfile: (nickname, extra) => fetch('/api/auth/update_profile', { method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() }, body: JSON.stringify({ nickname, ...(extra || {}) }) }).then(j),
  uploadUrl: (url) => fetch('/api/upload_url', { method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() }, body: JSON.stringify({ url }) }).then(j),
  job: (id) => fetch(`/api/job/${id}`, { headers: authHeaders() }).then(j),
  account: (fresh) => fetch('/api/account' + (fresh ? '?fresh=1' : ''), { headers: authHeaders() }).then(j),
  plans: () => fetch('/api/plans', { headers: authHeaders() }).then(j),
  payCreate: (plan, method) => fetch('/api/pay/create', { method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() }, body: JSON.stringify({ plan, method: method || 'alipay' }) }).then(j),
  payQuery: (orderId) => fetch('/api/pay/query?order_id=' + encodeURIComponent(orderId), { headers: authHeaders() }).then(j),
  orders: () => fetch('/api/orders', { headers: authHeaders() }).then(j),
  orderDelete: (orderId) => fetch('/api/orders/delete', { method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() }, body: JSON.stringify({ order_id: orderId }) }).then(j),
  getSettings: () => fetch('/api/settings', { headers: authHeaders() }).then(j),
  saveSettings: (cfg) => fetch('/api/settings', { method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() }, body: JSON.stringify(cfg) }).then(j),
  testSettings: () => fetch('/api/settings/test', { method: 'POST', headers: { ...authHeaders() } }).then(j),
  ask: (query, history = []) => fetch('/api/ask', { method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() }, body: JSON.stringify({ query, history }) }).then(async (r) => {
    if (r.status === 401) { try { localStorage.removeItem('auth') } catch { /* noop */ } location.reload(); throw new Error('401') }
    if (!r.ok) { let d = ''; try { d = (await r.json()).detail || '' } catch { /* noop */ } throw new Error(d || String(r.status)) }
    return r.json()
  }),
  cards: () => fetch('/api/cards', { headers: authHeaders() }).then(j),
  createCard: (c) => fetch('/api/card', { method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() }, body: JSON.stringify(c) }).then(j),
  cardRelated: (id) => fetch(`/api/card/${id}/related`, { headers: authHeaders() }).then(j),
  deleteCard: (id) => fetch(`/api/card/${id}`, { method: 'DELETE', headers: authHeaders() }).then(j),
  cardStatus: (id, status) => fetch(`/api/card/${id}/status`, { method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() }, body: JSON.stringify({ status }) }).then(j),
  cardEdit: (id, content) => fetch(`/api/card/${id}/edit`, { method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() }, body: JSON.stringify({ content }) }).then(j),
  // ★异步产出:后端立即返 job_id,内部轮询到完成——躲开 Tauri WKWebView ~60s 网络超时(深度撰写常60-90s)。命中缓存则直接返回。
  generate: async (topic, format, theme) => {
    const r = await fetch('/api/generate', { method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() }, body: JSON.stringify({ topic, format, theme }) }).then(j)
    if (!r || !r.job_id) return r
    for (let i = 0; i < 180; i++) {
      await new Promise((s) => setTimeout(s, 2000))
      const st = await fetch('/api/generate/status/' + r.job_id, { headers: authHeaders() }).then(j)
      if (st && st.state === 'done') return st
      if (st && st.state === 'error') throw new Error(st.error || '生成失败')
    }
    throw new Error('生成超时')
  },
  upload: (files, backend = 'auto') => {
    const fd = new FormData()
    for (const f of files) {
      // 用相对路径(展平)当文件名 → 嵌套/多文件夹里的同名文件不再撞名
      const rel = (f.webkitRelativePath && f.webkitRelativePath.length) ? f.webkitRelativePath : f.name
      fd.append('files', f, rel.replace(/[\\/]+/g, '__'))
    }
    return fetch(`/api/upload?backend=${backend}`, { method: 'POST', headers: authHeaders(), body: fd }).then(j)
  },
  // 定期同步文件夹(autosync):监听文件夹,新增/改动文件自动入库
  autosyncList: () => fetch('/api/autosync/list', { headers: authHeaders() }).then(j),
  autosyncAdd: (path) => fetch('/api/autosync/add', { method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() }, body: JSON.stringify({ path }) }).then(j),
  autosyncRemove: (path) => fetch('/api/autosync/remove', { method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() }, body: JSON.stringify({ path }) }).then(j),
}
