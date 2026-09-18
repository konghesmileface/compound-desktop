// 给下载的歌嵌 ID3v2.3 标签(歌名/歌手/专辑/完整歌词/封面)——
// 存到手机后,系统播放器/微信/网易云导入都能认出歌名、显示歌词和封面,
// 而不是一个只有文件名的裸音频。封面用 canvas 现画:黑胶+彩色圆标(和 App 冥想页一个气质)。

// 歌词洗掉结构标记行([Intro]/Verse 2/BRIDGE/副歌…)——用户只要词,不要谱曲脚手架
const LYR_MARK = /^\s*[[(【(]?\s*(intro|outro|verse|chorus|pre[- ]?chorus|bridge|hook|interlude|solo|refrain|rap|breakdown|drop|instrumental|前奏|间奏|尾奏|主歌|副歌|导歌|桥段|说唱)\s*\d*\s*[\])】)]?\s*[::]?\s*$/i
export function cleanLyrics(t) {
  if (!t) return ''
  const out = []
  let prevBlank = false
  for (const ln of String(t).split(/\r?\n/)) {
    if (LYR_MARK.test(ln)) continue
    const blank = !ln.trim()
    if (blank && prevBlank) continue
    out.push(ln); prevBlank = blank
  }
  return out.join('\n').trim()
}

// UTF-16LE + BOM(ID3v2.3 对中文最稳的编码,encoding byte=0x01)
function u16(str) {
  const s = String(str || '')
  const b = new Uint8Array(2 + s.length * 2)
  b[0] = 0xff; b[1] = 0xfe
  for (let i = 0; i < s.length; i++) { const c = s.charCodeAt(i); b[2 + i * 2] = c & 0xff; b[3 + i * 2] = c >> 8 }
  return b
}
function ascii(str) { return Uint8Array.from(String(str), (ch) => ch.charCodeAt(0) & 0x7f) }
function concat(parts) {
  const total = parts.reduce((n, p) => n + p.length, 0)
  const out = new Uint8Array(total)
  let o = 0
  for (const p of parts) { out.set(p, o); o += p.length }
  return out
}
// v2.3 帧:ID(4) + 大端长度(4) + flags(2) + payload
function frame(id, payload) {
  const h = new Uint8Array(10)
  h.set(ascii(id), 0)
  const n = payload.length
  h[4] = (n >>> 24) & 0xff; h[5] = (n >>> 16) & 0xff; h[6] = (n >>> 8) & 0xff; h[7] = n & 0xff
  return concat([h, payload])
}
const textFrame = (id, str) => frame(id, concat([Uint8Array.of(1), u16(str)]))

export function buildId3(meta) {
  const frames = []
  if (meta.title) frames.push(textFrame('TIT2', meta.title))
  if (meta.artist) frames.push(textFrame('TPE1', meta.artist))
  if (meta.album) frames.push(textFrame('TALB', meta.album))
  if (meta.year) frames.push(textFrame('TYER', meta.year))
  if (meta.lyrics) {
    // USLT: encoding(1) + lang(3) + 描述(UTF16空串:BOM+00 00) + 歌词
    frames.push(frame('USLT', concat([Uint8Array.of(1), ascii('chi'),
      Uint8Array.of(0xff, 0xfe, 0, 0), u16(meta.lyrics)])))
  }
  if (meta.coverPng && meta.coverPng.length) {
    // APIC: encoding(1,对描述,用latin1) + "image/png\0" + type 3封面 + 描述"\0" + 图
    frames.push(frame('APIC', concat([Uint8Array.of(0), ascii('image/png'), Uint8Array.of(0),
      Uint8Array.of(3), Uint8Array.of(0), meta.coverPng])))
  }
  const body = concat(frames)
  const head = new Uint8Array(10)
  head.set(ascii('ID3'), 0); head[3] = 3
  const n = body.length   // syncsafe 4x7bit
  head[6] = (n >>> 21) & 0x7f; head[7] = (n >>> 14) & 0x7f; head[8] = (n >>> 7) & 0x7f; head[9] = n & 0x7f
  return concat([head, body])
}

// 已有 ID3 的裸文件先剥掉旧标签,防两个标签打架
function stripId3(bytes) {
  if (bytes.length > 10 && bytes[0] === 0x49 && bytes[1] === 0x44 && bytes[2] === 0x33) {
    const n = ((bytes[6] & 0x7f) << 21) | ((bytes[7] & 0x7f) << 14) | ((bytes[8] & 0x7f) << 7) | (bytes[9] & 0x7f)
    return bytes.subarray(10 + n)
  }
  return bytes
}

// 封面:黑胶盘+按歌名哈希取色的圆标(和冥想页专辑一个气质),歌名+日期印在标上
export async function drawCoverPng(title, sub) {
  const S = 640
  const cv = document.createElement('canvas')
  cv.width = S; cv.height = S
  const g = cv.getContext('2d')
  let h = 0
  for (const ch of String(title || '')) h = (h * 31 + ch.codePointAt(0)) % 360
  const h2 = (h + 60) % 360
  g.fillStyle = '#0c0e12'; g.fillRect(0, 0, S, S)
  // 胶盘
  g.beginPath(); g.arc(S / 2, S / 2, S * 0.46, 0, 7); g.fillStyle = '#16181d'; g.fill()
  for (let r = S * 0.24; r < S * 0.44; r += 9) {
    g.beginPath(); g.arc(S / 2, S / 2, r, 0, 7)
    g.strokeStyle = 'rgba(255,255,255,0.045)'; g.lineWidth = 1.4; g.stroke()
  }
  // 圆标
  const lg = g.createLinearGradient(S * 0.3, S * 0.3, S * 0.7, S * 0.7)
  lg.addColorStop(0, `hsl(${h},72%,58%)`); lg.addColorStop(1, `hsl(${h2},70%,46%)`)
  g.beginPath(); g.arc(S / 2, S / 2, S * 0.215, 0, 7); g.fillStyle = lg; g.fill()
  g.beginPath(); g.arc(S / 2, S / 2, S * 0.018, 0, 7); g.fillStyle = '#0c0e12'; g.fill()
  // 歌名(最多两行)+ 日期
  g.textAlign = 'center'; g.fillStyle = 'rgba(255,255,255,0.96)'
  const t = String(title || '').replace(/^《|》$/g, '')
  const line1 = t.slice(0, 6), line2 = t.slice(6, 12)
  g.font = `600 ${line2 ? 44 : 52}px "PingFang SC", sans-serif`
  g.fillText(line1, S / 2, line2 ? S / 2 - 8 : S / 2 + 6)
  if (line2) g.fillText(line2, S / 2, S / 2 + 44)
  if (sub) {
    g.font = '400 24px "PingFang SC", sans-serif'
    g.fillStyle = 'rgba(255,255,255,0.72)'
    g.fillText(sub, S / 2, S / 2 + (line2 ? 92 : 60))
  }
  const blob = await new Promise((res) => cv.toBlob(res, 'image/png'))
  return blob ? new Uint8Array(await blob.arrayBuffer()) : null
}

// 入口:裸 mp3 Blob + 歌 meta → 带完整标签的 Blob(任何一步失败都返回原样,不挡下载)
export async function tagSongBlob(blob, song) {
  try {
    const bytes = stripId3(new Uint8Array(await blob.arrayBuffer()))
    const title = song.title || '我的主题曲'
    const coverPng = await drawCoverPng(title, [song.genre, song.date].filter(Boolean).join(' · ')).catch(() => null)
    const tag = buildId3({
      title, artist: '复利 · 你的大脑', album: '我的专辑',
      year: (song.date || '').slice(0, 4) || undefined,
      lyrics: cleanLyrics(song.lyrics), coverPng,
    })
    return new Blob([tag, bytes], { type: 'audio/mpeg' })
  } catch {
    return blob
  }
}
