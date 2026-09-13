// ============================================================
// M2 桌面 WebRTC answerer(跑在 Tauri webview,原生 RTCPeerConnection,零新依赖)
//
// 手机是 offerer,桌面是 answerer。信令经 106 relay 中转(phone_link 搬运),
// 加解密全在 Python(phone_link.rtc_exchange 复用 M1 那套,密钥不出 Python)。
// 本模块是"哑管道":
//   1. 短轮询 /api/phone/rtc/poll 取手机来的 offer/ice(带 cid 路由戳)
//   2. 建 RTCPeerConnection + answer,answer/ice 经 /api/phone/rtc/signal 发回手机
//   3. DataChannel(手机建的,ondatachannel 收)上收 {rid,n,d} → /api/phone/rtc/exchange
//      → 回 {rid,n,d}。DataChannel open = 打洞成功,业务数据不过服务器。
//
// 打洞失败 / webview 被最小化节流导致 DataChannel 断 → 手机端已有回落 relay 逻辑兜底,
// 桌面这边只要不回应/连不上,手机自动走中转,无需桌面特殊处理。
// ============================================================
import { api } from './api.js'

const STUN = [{ urls: ['stun:compoundtome.com:3478'] }]
const POLL_MS = 700
const CONN_TTL = 60000   // 一条连接 60s 没 open 就丢弃重来

let running = false
let timer = null
const conns = new Map()  // cid -> { pc, dev, dc, born }

function cleanup(cid) {
  const c = conns.get(cid)
  if (!c) return
  try { c.dc && c.dc.close() } catch { /* noop */ }
  try { c.pc && c.pc.close() } catch { /* noop */ }
  conns.delete(cid)
}

function sweep() {
  const now = Date.now()
  for (const [cid, c] of conns) {
    const open = c.dc && c.dc.readyState === 'open'
    if (!open && now - c.born > CONN_TTL) cleanup(cid)
  }
}

async function onOffer(sig) {
  const { cid, dev, sdp } = sig
  if (!cid || !dev || !sdp) return
  cleanup(cid)   // 同 cid 旧连接作废(手机重连会发新 offer)
  if (typeof RTCPeerConnection === 'undefined') return

  const pc = new RTCPeerConnection({ iceServers: STUN })
  const entry = { pc, dev, dc: null, born: Date.now() }
  conns.set(cid, entry)

  pc.onicecandidate = (ev) => {
    if (ev.candidate) api.rtcSignal({ sub: 'ice', cid, cand: ev.candidate.toJSON() }).catch(() => {})
  }
  pc.onconnectionstatechange = () => {
    if (['failed', 'closed', 'disconnected'].includes(pc.connectionState)) cleanup(cid)
  }
  // 手机(offerer)建的 DataChannel,桌面这边被动收
  pc.ondatachannel = (ev) => {
    const dc = ev.channel
    entry.dc = dc
    dc.onmessage = async (m) => {
      let msg
      try { msg = JSON.parse(m.data) } catch { return }
      if (!msg || msg.rid == null || !msg.n || !msg.d) return
      try {
        const r = await api.rtcExchange(dev, msg.n, msg.d)
        dc.send(JSON.stringify({ rid: msg.rid, n: r.n, d: r.d }))
      } catch {
        // 交换失败:回一个空错误帧,手机端该请求会超时并回落 relay
        try { dc.send(JSON.stringify({ rid: msg.rid, err: 'exchange_failed' })) } catch { /* noop */ }
      }
    }
    dc.onclose = () => cleanup(cid)
  }

  try {
    await pc.setRemoteDescription({ type: 'offer', sdp })
    const answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)
    await api.rtcSignal({ sub: 'answer', cid, sdp: answer.sdp })
  } catch {
    cleanup(cid)
  }
}

async function onIce(sig) {
  const c = conns.get(sig.cid)
  if (!c || !sig.cand) return
  try { await c.pc.addIceCandidate(sig.cand) } catch { /* 乱序/重复候选忽略 */ }
}

async function tick() {
  if (!running) return
  try {
    const r = await api.rtcPoll()
    for (const sig of (r.signals || [])) {
      if (sig.sub === 'offer') await onOffer(sig)
      else if (sig.sub === 'ice') await onIce(sig)
    }
    sweep()
  } catch { /* relay 未连/后端忙:下轮再试 */ }
  if (running) timer = setTimeout(tick, POLL_MS)
}

export function startRtcAnswerer() {
  if (running) return
  running = true
  timer = setTimeout(tick, POLL_MS)
}

export function stopRtcAnswerer() {
  running = false
  if (timer) { clearTimeout(timer); timer = null }
  for (const cid of [...conns.keys()]) cleanup(cid)
}
