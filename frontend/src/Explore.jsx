import React, { useEffect, useRef, useState, useCallback, useMemo } from 'react'
import ForceGraph3D from 'react-force-graph-3d'
import ForceGraph2D from 'react-force-graph-2d'
import { forceCollide, forceX as d3ForceX, forceY as d3ForceY } from 'd3-force-3d'
import * as THREE from 'three'
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js'
import { api } from './api'
import { IconSearch, IconExplore } from './icons'
import { toast, Empty } from './ui'
import FILE_ICONS from './fileIcons.json'

// ★ 星海预设:每个都是"真正不同"的可视化 —— 深黑通透底 + 只让最亮的核心 bloom(高 threshold 防发白雾)。
// 关键差异字段:layout(布局形态) core(密核) neb(暗星云层) links(连线可见度) starLayers(星尘两层) sizeBoost/白核映射 等
const PRESETS = [
  // 银河:参照图主形态 —— 纯黑深空 + 明亮白青密核 + 放射星丝 + 金/白/青彩簇
  { key: 'galaxy', name: '银河', dims: 3, bg: '#08090d', layout: 'core', gravity: 0.34,
    palette: ['#fff7e0', '#fde68a', '#fcd34d', '#fbbf24', '#e8f0ff', '#bcd4ff', '#a9f0ff', '#ffd8a0'],
    coreColor: '#eaf6ff', coreSize: 26, sizeBoost: 1.85, whiteCore: true,
    bloom: { s: 0.95, r: 0.55, t: 0.82 }, link: 'rgba(180,205,255,0.22)', linkW: 1.2, linkVis: 1,
    // 星尘:压掉蓝味泛 navy —— 数量减、透明度降、颜色改中性微暖白(去蓝味)、点更小,空背景干净近黑
    charge: -70, dist: 30, starLayers: [{ n: 520, c: '#d6d4cf', size: 0.5, op: 0.16, rIn: 780 }, { n: 80, c: '#ffffff', size: 1.4, op: 0.8, rIn: 420 }] },
  // 星云:柔和弥散的暗紫星云雾(仍深黑底)+ 中等散布,朦胧但不发白
  { key: 'nebula', name: '星云', dims: 3, bg: '#0a080e', layout: 'cloud', gravity: 0.08,
    palette: ['#d8b4fe', '#c084fc', '#f0abfc', '#a78bfa', '#f9a8d4', '#93c5fd', '#7dd3fc', '#e9d5ff'],
    coreColor: '#e9c8ff', coreSize: 20, sizeBoost: 1.0, whiteCore: false,
    nebula: { color: '#6d28d9', color2: '#241042', intensity: 0.13, scale: 1.7 },
    bloom: { s: 0.85, r: 0.7, t: 0.74 }, link: 'rgba(190,150,255,0.14)', linkW: 0.4, linkVis: 1,
    charge: -150, dist: 52, starLayers: [{ n: 2600, c: '#d9c2ff', size: 0.85, op: 0.4, rIn: 620 }] },
  // 繁星:海量冷白小亮点铺满深空,清冷通透,几乎无连线(纯星野)
  { key: 'deepfield', name: '繁星', dims: 3, bg: '#06070a', layout: 'scatter', gravity: 0.03,
    palette: ['#f5f8ff', '#dbe6ff', '#bcd4ff', '#cfe0ff', '#e2e8f0', '#a9c6ff', '#eef4ff', '#c7d6f5'],
    coreColor: '#ffffff', coreSize: 12, sizeBoost: 0.72, whiteCore: false,
    bloom: { s: 0.9, r: 0.62, t: 0.72 }, link: 'rgba(150,165,200,0.05)', linkW: 0.25, linkVis: 0,
    charge: -230, dist: 72, starLayers: [{ n: 4200, c: '#ffffff', size: 0.6, op: 0.5, rIn: 520 }, { n: 1100, c: '#c6d6f0', size: 0.9, op: 0.26, rIn: 900 }] },
  // 极光:深墨绿底 + 顶部真·极光飘带(shader 光带)+ 青绿星丝,像坐在极地看极光
  { key: 'aurora', name: '极光', dims: 3, bg: '#06090b', layout: 'core', gravity: 0.22,
    palette: ['#7dffc4', '#5eead4', '#8b8cff', '#a3f0d0', '#bef264', '#38f0c0', '#9df0ff', '#c6ff9e'],
    coreColor: '#c8fff0', coreSize: 22, sizeBoost: 1.1, whiteCore: false,
    aurora: true,
    bloom: { s: 1.45, r: 0.85, t: 0.55 }, link: 'rgba(120,255,210,0.2)', linkW: 0.6, linkVis: 1,
    charge: -90, dist: 40, starLayers: [{ n: 1600, c: '#bffce8', size: 0.7, op: 0.42, rIn: 640 }] },
  // 烟花:从核心猛烈爆发的放射感 —— 强 gravity 抱核 + 高饱和彩簇 + 强连线成放射丝
  { key: 'fireworks', name: '烟花', dims: 3, bg: '#09080b', layout: 'burst', gravity: 0.48,
    palette: ['#ff4d6d', '#ff8c42', '#ffd23f', '#ff5eb0', '#3fd0ff', '#b78cff', '#5effa0', '#54c8ff'],
    coreColor: '#fff4e0', coreSize: 24, sizeBoost: 1.15, whiteCore: false,
    bloom: { s: 1.9, r: 0.9, t: 0.5 }, link: 'rgba(255,180,150,0.28)', linkW: 0.9, linkVis: 1,
    charge: -55, dist: 26, starLayers: [{ n: 1200, c: '#ffd6c0', size: 0.7, op: 0.4, rIn: 700 }] },
  // 银盘:盘状旋臂(2D 铺平 + 旋臂布局),金橙暖色,像俯视一个星系盘
  { key: 'disk', name: '银盘', dims: 2, bg: '#09080a', layout: 'disk', gravity: 0.12,
    palette: ['#ffd98a', '#ffb14d', '#ff9f6b', '#ffce8f', '#f7c26b', '#ffe0a3', '#f0a35a', '#ffcf9e'],
    coreColor: '#fff2d0', coreSize: 22, sizeBoost: 1.05, whiteCore: true,
    bloom: { s: 1.35, r: 0.8, t: 0.55 }, link: 'rgba(255,205,140,0.16)', linkW: 0.5, linkVis: 1,
    charge: -80, dist: 38, starLayers: [{ n: 2200, c: '#e6d3b0', size: 0.75, op: 0.4, rIn: 640 }] },
  // 星图:干净的蓝白星座连线图 —— 细锐节点 + 明显可见的连线(星座感),弱 bloom 保持清晰
  { key: 'chart', name: '星图', dims: 2, bg: '#080a0e', layout: 'scatter', gravity: 0.05,
    palette: ['#bcd4ff', '#9df0ff', '#a7f3d0', '#c4b5fd', '#fda4af', '#ffe08a', '#8fe6ff', '#e0c4ff'],
    coreColor: '#dcefff', coreSize: 14, sizeBoost: 0.85, whiteCore: false,
    bloom: { s: 0.7, r: 0.55, t: 0.68 }, link: 'rgba(150,185,235,0.34)', linkW: 0.55, linkVis: 1,
    charge: -140, dist: 56, starLayers: [{ n: 1600, c: '#cfe0ff', size: 0.65, op: 0.45, rIn: 560 }] },
  // 霓虹:高饱和赛博彩色 + 强辉光,粉紫青撞色,亮到发光
  { key: 'neon', name: '霓虹', dims: 3, bg: '#09080d', layout: 'core', gravity: 0.26,
    palette: ['#ff5ff0', '#22e0ff', '#a86bff', '#5effe0', '#ff5e8a', '#6b8cff', '#ffe23f', '#3fffb0'],
    coreColor: '#ffd0ff', coreSize: 22, sizeBoost: 1.2, whiteCore: false,
    bloom: { s: 2.0, r: 0.92, t: 0.46 }, link: 'rgba(230,120,255,0.28)', linkW: 0.7, linkVis: 1,
    charge: -110, dist: 46, starLayers: [{ n: 1800, c: '#f0c0ff', size: 0.8, op: 0.42, rIn: 620 }] },
  // 极简:极干净 —— 只留素白节点,无连线、几乎无 bloom、少量星尘,禅意留白
  { key: 'minimal', name: '极简', dims: 3, bg: '#08090d', layout: 'scatter', gravity: 0.06,
    palette: ['#e8ecf3', '#cbd5e1', '#dfe5ee', '#c7d0dd', '#eef2f8', '#b8c2d0', '#f2f5fa', '#d0d8e4'],
    coreColor: '#f2f5fa', coreSize: 12, sizeBoost: 0.8, whiteCore: false,
    bloom: { s: 0.35, r: 0.45, t: 0.78 }, link: 'rgba(160,170,190,0.04)', linkW: 0.3, linkVis: 0,
    charge: -170, dist: 60, starLayers: [{ n: 700, c: '#e6ecf5', size: 0.6, op: 0.32, rIn: 640 }] },
]

// ★ 三档 = 真正的性能档,不只是节点数(chunk 越大 → 采样越稀 → 节点越少)。
//   每档还控制: bloom 强度/分辨率倍率、逐帧呼吸(pulse)、星尘密度倍率、pixelRatio 上限、是否自转。
//   coarse=给弱机(最少节点/几乎无 bloom/无呼吸/无自转/低分辨率),fine=给强机(全效果)。
const GRAINS = [
  { key: 'coarse', name: '粗', chunk: 42, perf: {
      bloomMul: 0,          // 关 bloom(粗档最省)
      bloomRes: 0.4,        // (bloom 关时无用)
      pulse: false,         // 不做逐帧呼吸
      dustMul: 0.25,        // 星尘只留 1/4
      pixelRatio: 1.0,      // 硬顶 1x
      autoRotate: false,    // 不自转
      pulseSlice: 1,        // (无 pulse)
    } },
  { key: 'medium', name: '中', chunk: 14, perf: {
      bloomMul: 0.7, bloomRes: 0.6, pulse: true, dustMul: 0.6,
      pixelRatio: 1.25, autoRotate: true, pulseSlice: 4,   // 每帧只更新 1/4 精灵
    } },
  { key: 'fine', name: '细', chunk: 5, perf: {
      bloomMul: 1.0, bloomRes: 1.0, pulse: true, dustMul: 1.0,
      pixelRatio: 1.5, autoRotate: true, pulseSlice: 2,    // 每帧更新 1/2 精灵(≈30fps 视觉)
    } },
]
const grainPerf = (key) => (GRAINS.find((g) => g.key === key) || GRAINS[1]).perf

const FTYPES = {
  '.pdf': ['PDF', '#ef4444'], '.epub': ['电子书', '#a855f7'], '.mobi': ['电子书', '#a855f7'],
  '.fb2': ['电子书', '#a855f7'], '.docx': ['Word', '#3b82f6'], '.pptx': ['PPT', '#f97316'],
  '.xlsx': ['Excel', '#22c55e'], '.xlsm': ['Excel', '#22c55e'], '.md': ['笔记', '#94a3b8'],
  '.markdown': ['笔记', '#94a3b8'], '.txt': ['文本', '#94a3b8'],
  '.html': ['网页', '#38bdf8'], '.htm': ['网页', '#38bdf8'], '.csv': ['数据', '#a3e635'],
  '.json': ['数据', '#a3e635'], '.eml': ['邮件', '#f0abfc'],
  '.png': ['截图', '#14b8a6'], '.jpg': ['截图', '#14b8a6'], '.jpeg': ['截图', '#14b8a6'],
  '.webp': ['截图', '#14b8a6'], '.heic': ['截图', '#14b8a6'], '.gif': ['截图', '#14b8a6'],
  '.mp4': ['视频', '#fb7185'], '.mov': ['视频', '#fb7185'], '.mkv': ['视频', '#fb7185'], '.avi': ['视频', '#fb7185'],
  '.mp3': ['录音', '#fbbf24'], '.wav': ['录音', '#fbbf24'], '.m4a': ['录音', '#fbbf24'],
  '.flac': ['录音', '#fbbf24'], '.aac': ['录音', '#fbbf24'], '.ogg': ['录音', '#fbbf24'],
}
function ftypeOf(node) {
  const fn = String(node.label || '').split(' · ')[0].toLowerCase()
  const ext = fn.slice(fn.lastIndexOf('.'))
  return FTYPES[ext] || ['其它', '#cbd5e1']
}
const FT_ABBR = { PDF: 'PDF', 电子书: 'BOOK', Word: 'DOC', PPT: 'PPT', Excel: 'XLS', 笔记: 'MD', 文本: 'TXT', 网页: 'WEB', 数据: 'CSV', 邮件: 'MAIL', 截图: 'IMG', 视频: 'VID', 录音: 'AUD', 其它: 'FILE', 目标: '目标', 日记: '日记', 笔记本: '笔记' }

function roundRectPath(g, x, y, w, h, r) {
  g.beginPath()
  g.moveTo(x + r, y); g.arcTo(x + w, y, x + w, y + h, r); g.arcTo(x + w, y + h, x, y + h, r)
  g.arcTo(x, y + h, x, y, r); g.arcTo(x, y, x + w, y, r); g.closePath()
}
// 颜色工具:提亮 / 变暗 / 按亮度选文字色(高度还原参考图那种彩色 app 图标砖)
function hex2rgb(h) { h = h.replace('#', ''); if (h.length === 3) h = h.split('').map((c) => c + c).join(''); return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)] }
function mix(c, t, amt) { const [r, g, b] = hex2rgb(c); return `rgb(${Math.round(r + (t[0] - r) * amt)},${Math.round(g + (t[1] - g) * amt)},${Math.round(b + (t[2] - b) * amt)})` }
const lighten = (c, a) => mix(c, [255, 255, 255], a)
const darken = (c, a) => mix(c, [0, 0, 0], a)
function textOn(c) { const [r, g, b] = hex2rgb(c); return (0.299 * r + 0.587 * g + 0.114 * b) > 165 ? '#12151c' : '#ffffff' }
// 真·文件图标:白色文档 + 折角 + 底部彩色类型徽标(PDF/DOC/PPT/XLS/EPUB…),精细小巧,对标 @0xDezo/Ryven
function drawFileTile(ctx, cx, cy, s, abbr, color) {
  const w = s * 1.6, h = s * 2.0, x = cx - w / 2, y = cy - h / 2, rr = Math.max(0.8, s * 0.16), fold = w * 0.34
  ctx.save()
  // 文档主体(白)带折角
  ctx.beginPath()
  ctx.moveTo(x + rr, y); ctx.lineTo(x + w - fold, y); ctx.lineTo(x + w, y + fold)
  ctx.lineTo(x + w, y + h - rr); ctx.arcTo(x + w, y + h, x + w - rr, y + h, rr)
  ctx.lineTo(x + rr, y + h); ctx.arcTo(x, y + h, x, y + h - rr, rr)
  ctx.lineTo(x, y + rr); ctx.arcTo(x, y, x + rr, y, rr); ctx.closePath()
  ctx.fillStyle = '#f7f9fc'; ctx.fill()
  // 折角阴影三角
  ctx.beginPath(); ctx.moveTo(x + w - fold, y); ctx.lineTo(x + w - fold, y + fold); ctx.lineTo(x + w, y + fold); ctx.closePath()
  ctx.fillStyle = '#d3dae5'; ctx.fill()
  // 内容假线(细横线)
  ctx.strokeStyle = 'rgba(120,135,160,0.5)'; ctx.lineWidth = Math.max(0.4, s * 0.09)
  for (let i = 0; i < 3; i++) { const ly = y + fold + s * 0.4 + i * s * 0.42; ctx.beginPath(); ctx.moveTo(x + s * 0.3, ly); ctx.lineTo(x + w - s * 0.3, ly); ctx.stroke() }
  // 底部彩色类型徽标
  const bh = h * 0.42
  ctx.beginPath()
  ctx.moveTo(x, y + h - bh); ctx.lineTo(x + w, y + h - bh)
  ctx.lineTo(x + w, y + h - rr); ctx.arcTo(x + w, y + h, x + w - rr, y + h, rr)
  ctx.lineTo(x + rr, y + h); ctx.arcTo(x, y + h, x, y + h - rr, rr); ctx.closePath()
  ctx.fillStyle = color; ctx.fill()
  ctx.fillStyle = '#fff'; ctx.font = `800 ${bh * 0.56}px -apple-system,"Helvetica Neue",sans-serif`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'
  ctx.fillText(abbr, cx, y + h - bh / 2 + bh * 0.02)
  ctx.restore()
}

// 彩色 app 图标砖:圆角方块 + 渐变 + 顶部高光 + 类型字(高度还原参考图)
const _iconCache = new Map()
function makeTileIcon(node) {
  const isCard = String(node.label || '').startsWith('card') || node.ctype
  const [label, color] = isCard ? ['卡片', '#8b8cff'] : ftypeOf(node)
  const glyph = FT_ABBR[label] || label
  const cacheKey = color + '|' + glyph
  let tex = _iconCache.get(cacheKey)
  if (!tex) {
    const cv = document.createElement('canvas'); cv.width = 144; cv.height = 144
    const g = cv.getContext('2d')
    const pad = 20, size = 144 - pad * 2, r = 34
    // 外发光
    g.shadowColor = color; g.shadowBlur = 22; g.shadowOffsetY = 3
    const grad = g.createLinearGradient(0, pad, 0, pad + size)
    grad.addColorStop(0, lighten(color, 0.28)); grad.addColorStop(1, darken(color, 0.12))
    g.fillStyle = grad; roundRectPath(g, pad, pad, size, size, r); g.fill()
    g.shadowBlur = 0; g.shadowOffsetY = 0
    // 顶部高光
    g.fillStyle = 'rgba(255,255,255,0.20)'
    roundRectPath(g, pad + 7, pad + 7, size - 14, size * 0.44, r - 8); g.fill()
    // 描边
    g.strokeStyle = 'rgba(255,255,255,0.28)'; g.lineWidth = 2
    roundRectPath(g, pad + 1, pad + 1, size - 2, size - 2, r); g.stroke()
    // 类型字
    g.fillStyle = textOn(color)
    const fs = glyph.length <= 3 ? 40 : glyph.length === 4 ? 32 : 26
    g.font = `800 ${fs}px -apple-system, "PingFang SC", sans-serif`
    g.textAlign = 'center'; g.textBaseline = 'middle'
    g.fillText(glyph, 72, 76)
    tex = new THREE.CanvasTexture(cv); tex.anisotropy = 4
    _iconCache.set(cacheKey, tex)
  }
  const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false }))
  const s = 14 + Math.min(node.size || 1, 9)
  sp.scale.set(s, s, 1)
  return sp
}
function hash(s) { let h = 0; s = String(s); for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0; return h }
const nodeKey = (n) => (n.doc_id != null ? n.doc_id : n.id)

// 圆角矩形(canvas 2D)
function rr(ctx, x, y, w, h, r) {
  ctx.beginPath()
  ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r)
  ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath()
}

// 轻量径向力(不引 d3-force):按重要度把节点拉向不同半径 → 中心大、外围小的环状层次
function makeRadialForce(getR, strength) {
  let nodes = []
  function force(alpha) {
    for (const n of nodes) {
      const dx = n.x || 0, dy = n.y || 0
      const dist = Math.hypot(dx, dy) || 1e-6
      const k = (getR(n) - dist) / dist * strength * alpha
      n.vx += dx * k; n.vy += dy * k
    }
  }
  force.initialize = (nds) => { nodes = nds }
  return force
}
// 节点视觉半径:适中,按页数(重要度)sqrt 梯度
function nodeRadius(node) { return 2.4 + Math.sqrt(Math.min(node.size || 1, 50)) * 0.95 }

// ===== 星海:发光点精灵纹理(径向渐变,亮心→透明边)—— 让节点在纯黑底上是"会发光的星",bloom 只咬亮心 =====
let _glowTex = null
function glowTexture() {
  if (_glowTex) return _glowTex
  const cv = document.createElement('canvas'); cv.width = 128; cv.height = 128
  const g = cv.getContext('2d')
  const grd = g.createRadialGradient(64, 64, 0, 64, 64, 64)
  grd.addColorStop(0.0, 'rgba(255,255,255,1)')
  grd.addColorStop(0.16, 'rgba(255,255,255,0.96)')
  grd.addColorStop(0.32, 'rgba(255,255,255,0.42)')
  grd.addColorStop(0.58, 'rgba(255,255,255,0.08)')
  grd.addColorStop(1.0, 'rgba(255,255,255,0)')
  g.fillStyle = grd; g.fillRect(0, 0, 128, 128)
  _glowTex = new THREE.CanvasTexture(cv)
  return _glowTex
}
// 星尘专用纹理:更陡的衰减(几乎只有亮心,几乎无外晕)→ 背景是干净的点,不叠成一片泛蓝雾霭
let _dustTex = null
function dustTexture() {
  if (_dustTex) return _dustTex
  const cv = document.createElement('canvas'); cv.width = 64; cv.height = 64
  const g = cv.getContext('2d')
  const grd = g.createRadialGradient(32, 32, 0, 32, 32, 32)
  grd.addColorStop(0.0, 'rgba(255,255,255,1)')
  grd.addColorStop(0.28, 'rgba(255,255,255,0.55)')
  grd.addColorStop(0.55, 'rgba(255,255,255,0.08)')
  grd.addColorStop(1.0, 'rgba(255,255,255,0)')
  g.fillStyle = grd; g.fillRect(0, 0, 64, 64)
  _dustTex = new THREE.CanvasTexture(cv)
  return _dustTex
}
// 每颗星=一个上色的发光精灵;whiteCore 时高连通度(size 大)的节点趋近白/浅色 → 形成明亮密核
// registry:收集所有星点精灵,供 rAF 做错相位呼吸(闪烁)动画;卸载/切预设时清空
function makeStarSprite(node, preset, colorOf, registry, sizeMul = 1, glowOp = 0.96) {
  let col = colorOf(node)
  const imp = Math.min((node.size || 1) / 10, 1)          // 连通度 → 重要度 0..1
  if (preset.whiteCore && imp > 0.55) col = mix(col, [255, 255, 255], (imp - 0.55) / 0.45 * 0.85)
  const mat = new THREE.SpriteMaterial({
    map: glowTexture(), color: new THREE.Color(col),
    // ★正常混合(非叠加):星点重叠只互相遮挡,永不累加成白 → 永久根治整屏爆闪白
    transparent: true, depthWrite: false, blending: THREE.NormalBlending, opacity: glowOp,
  })
  const sp = new THREE.Sprite(mat)
  const base0 = nodeRadius(node) * (preset.sizeBoost || 1) * 2.15   // 未缩放基准(调节·节点用它×系数)
  const base = base0 * sizeMul
  sp.scale.set(base, base, 1)
  // 生命感呼吸元数据:错相位 + 亮核(大星)呼吸更明显一点,克制不浮夸
  sp.userData.pulse = {
    base, base0, baseOp: glowOp,
    phase: (Math.abs(hash(nodeKey(node))) % 6283) / 1000,   // 每颗星自身相位,不同步
    speed: 0.55 + (Math.abs(hash('s' + nodeKey(node))) % 40) / 100,  // 0.55~0.95 低频
    amp: 0.10 + imp * 0.10,                                  // 大星幅度略大(0.10~0.20)
  }
  if (registry) registry.push(sp)
  return sp
}
// 中央密核:一颗特大发光精灵(参照图核心那团白青强辉光)
function makeCoreSprite(preset) {
  const mat = new THREE.SpriteMaterial({ map: glowTexture(), color: new THREE.Color(preset.coreColor || '#eaf6ff'), transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, opacity: 0.4 })
  const sp = new THREE.Sprite(mat); const s = (preset.coreSize || 22) * 0.6
  sp.scale.set(s, s, 1); sp.renderOrder = -1
  return sp
}
// 暗星云层:FBM 噪声球壳,低强度、深色(星云/朦胧感,但绝不发白)
function makeNebula(preset) {
  const p = preset.nebula
  const geo = new THREE.SphereGeometry(560, 48, 48)
  const mat = new THREE.ShaderMaterial({
    transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.BackSide,
    uniforms: {
      uColor: { value: new THREE.Color(p.color) }, uColor2: { value: new THREE.Color(p.color2 || p.color) },
      uInt: { value: p.intensity }, uScale: { value: p.scale }, uTime: { value: 0 },
    },
    vertexShader: `varying vec3 vP; void main(){ vP = position; gl_Position = projectionMatrix*modelViewMatrix*vec4(position,1.0);} `,
    fragmentShader: `
      varying vec3 vP; uniform vec3 uColor; uniform vec3 uColor2; uniform float uInt; uniform float uScale; uniform float uTime;
      float hash(vec3 p){ p=fract(p*0.3183+0.1); p*=17.0; return fract(p.x*p.y*p.z*(p.x+p.y+p.z)); }
      float noise(vec3 x){ vec3 i=floor(x); vec3 f=fract(x); f=f*f*(3.0-2.0*f);
        return mix(mix(mix(hash(i+vec3(0,0,0)),hash(i+vec3(1,0,0)),f.x),mix(hash(i+vec3(0,1,0)),hash(i+vec3(1,1,0)),f.x),f.y),
                   mix(mix(hash(i+vec3(0,0,1)),hash(i+vec3(1,0,1)),f.x),mix(hash(i+vec3(0,1,1)),hash(i+vec3(1,1,1)),f.x),f.y),f.z); }
      float fbm(vec3 p){ float v=0.0,a=0.5; for(int i=0;i<5;i++){ v+=a*noise(p); p*=2.03; a*=0.5;} return v; }
      void main(){ vec3 dir=normalize(vP); float n=fbm(dir*uScale + vec3(0.0,uTime*0.02,0.0));
        n=smoothstep(0.58,0.98,n); vec3 col=mix(uColor2,uColor,n); float a=n*uInt;
        gl_FragColor=vec4(col*a, a); }`,
  })
  return new THREE.Mesh(geo, mat)
}
// 极光飘带:顶部一块波动的光带平面(shader),深色不透明区域→透明,青绿渐变
function makeAurora() {
  const geo = new THREE.PlaneGeometry(1700, 620, 1, 1)
  const mat = new THREE.ShaderMaterial({
    transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide,
    uniforms: { uTime: { value: 0 } },
    vertexShader: `varying vec2 vUv; void main(){ vUv=uv; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);} `,
    fragmentShader: `
      varying vec2 vUv; uniform float uTime;
      float hash(float n){ return fract(sin(n)*43758.5453); }
      float noise(vec2 p){ vec2 i=floor(p),f=fract(p); f=f*f*(3.0-2.0*f);
        float a=hash(i.x+i.y*57.0),b=hash(i.x+1.0+i.y*57.0),c=hash(i.x+(i.y+1.0)*57.0),d=hash(i.x+1.0+(i.y+1.0)*57.0);
        return mix(mix(a,b,f.x),mix(c,d,f.x),f.y); }
      void main(){
        float x=vUv.x, y=vUv.y;
        // 多条随时间漂动的极光帘幕
        float band=0.0;
        for(int i=0;i<3;i++){ float fi=float(i);
          float wob=noise(vec2(x*4.0+fi*10.0, uTime*0.15+fi))*0.22 + noise(vec2(x*9.0, uTime*0.25))*0.09;
          float cy=0.34+fi*0.12+wob;
          float d=abs(y-cy);
          band+=smoothstep(0.14,0.0,d)*(0.6+0.4*noise(vec2(x*20.0+fi, uTime*0.4)));
        }
        // 竖向帘幕纹理
        float curtain=0.6+0.4*noise(vec2(x*40.0, uTime*0.3+y*3.0));
        band*=curtain;
        // 青→绿→洋红渐变
        vec3 col=mix(vec3(0.15,0.95,0.7), vec3(0.55,1.0,0.45), noise(vec2(x*3.0,uTime*0.1)));
        col=mix(col, vec3(0.75,0.4,1.0), smoothstep(0.7,1.0,x)*0.5);
        float fade=smoothstep(1.0,0.55,y)*smoothstep(0.0,0.15,y);   // 上下淡出
        float a=band*fade*0.5;
        gl_FragColor=vec4(col*a, a);
      }`,
  })
  const m = new THREE.Mesh(geo, mat)
  m.position.set(0, 360, -260); m.rotation.x = -0.32
  return m
}

// 文件类型 → 真·文件格式图标(Font Awesome SVG 路径 → Path2D 画进 canvas)
const ICON_KEY = { PDF: 'pdf', 电子书: 'book', Word: 'word', PPT: 'ppt', Excel: 'excel', 笔记: 'txt', 文本: 'txt', 网页: 'web', 数据: 'csv', 邮件: 'mail', 截图: 'image', 视频: 'video', 录音: 'audio', 其它: 'file', 卡片: 'card' }
const _p2d = {}
function iconFor(key) {
  if (_p2d[key] === undefined) {
    const d = FILE_ICONS[key] || FILE_ICONS.file
    _p2d[key] = d ? { w: d.w, h: d.h, p: new Path2D(d.d) } : null
  }
  return _p2d[key]
}

// ===== 文档模式:2D 力导图(精致小巧 icon + Obsidian 式邻居高亮) =====
function DocGraph2D({ data, dim, colorOf, onOpen, hidden, groupKey, hiIds, adj, bg, clusterNames = [], chatOnly = false }) {
  const ref = useRef()
  const [hover, setHover] = useState(null)
  const hl = useRef({ nodes: new Set(), links: new Set() })
  const animRef = useRef({ ready: false, cx: 0, cy: 0 })   // 力导稳定后快照的旋转中心
  const rotRef = useRef(0)

  // 邻接表:每个节点 → 相连节点/连线(用于高亮邻居)
  const adj2 = useMemo(() => {
    const m = new Map()
    data.nodes.forEach((n) => m.set(nodeKey(n), { nb: new Set(), lk: new Set() }))
    data.links.forEach((l) => {
      const s = typeof l.source === 'object' ? nodeKey(l.source) : l.source
      const t = typeof l.target === 'object' ? nodeKey(l.target) : l.target
      const a = m.get(s), b = m.get(t)
      if (a) { a.nb.add(t); a.lk.add(l) }
      if (b) { b.nb.add(s); b.lk.add(l) }
    })
    return m
  }, [data])

  // 径向树布局(对标 @0xDezo):枢纽 → 【文件类型】(内圈)→ 每种类型的文档向外扇形展开
  const laid = useMemo(() => {
    const groups = {}
    data.nodes.forEach((n) => { const [t, col] = ftypeOf(n); if (!groups[t]) groups[t] = { label: t, col, docs: [] }; groups[t].docs.push(n) })
    const tkeys = Object.keys(groups).sort((a, b) => groups[b].docs.length - groups[a].docs.length)
    const NC = tkeys.length || 1
    // 有机星系(对标 @0xDezo/cyrilXBT):中央「脑」轻钉原点,其余交给力导散成自然簇;稳定后由旋转动画接管做 3D 自转
    const nodes = [{ id: '__hub', hub: true, display: '第二大脑', fx: 0, fy: 0 }]
    const treeLinks = []
    tkeys.forEach((t, gi) => {
      const g = groups[t]
      const a = (gi / NC) * Math.PI * 2
      const catId = '__cat_' + t
      nodes.push({ id: catId, cat: true, display: t, col: g.col, x: Math.cos(a) * 150, y: Math.sin(a) * 150 })
      treeLinks.push({ source: '__hub', target: catId, tree: true, strong: true })
      g.docs.forEach((n, i) => {
        const rr0 = 240 + (i % 5) * 40
        const spread = a + ((i * 2.399) % 1 - 0.5) * 0.9   // 黄金角抖动,同类文档散成有机一簇
        nodes.push({ ...n, x: Math.cos(spread) * rr0, y: Math.sin(spread) * rr0 })
        treeLinks.push({ source: catId, target: nodeKey(n), tree: true })
      })
    })
    return { nodes, links: [...treeLinks, ...data.links.map((l) => ({ ...l }))] }
  }, [data])

  const clickFx = useRef({ id: null, t: 0 })

  useEffect(() => {
    const fg = ref.current; if (!fg) return
    try {
      fg.d3Force('charge').strength(-90).distanceMax(620)
      fg.d3Force('link').distance((l) => (l.strong ? 150 : 66)).strength((l) => (l.tree ? (l.strong ? 0.85 : 0.16) : 0.02))
      const c = fg.d3Force('center'); if (c) c.strength(0.05)
      // 碰撞体积略大于图标,彻底不叠
      fg.d3Force('collide', forceCollide((n) => (n.hub ? 22 : n.cat ? 32 : Math.max(9, nodeRadius(n)) * 2.0 + 12)).strength(1).iterations(3))
    } catch (e) { /* noop */ }
    const t = setTimeout(() => { try { fg.zoomToFit(800, 70) } catch (e) {} }, 1600)
    return () => clearTimeout(t)
  }, [laid])

  const pinnedRef = useRef(null)   // 点击选中的节点(粘性聚焦)
  const nbOf = useCallback((node) => {
    const nodes = new Set(), links = new Set()
    if (node) { nodes.add(nodeKey(node)); const e = adj2.get(nodeKey(node)); if (e) { e.nb.forEach((k) => nodes.add(k)); e.lk.forEach((l) => links.add(l)) } }
    return { nodes, links }
  }, [adj2])
  const onHover = useCallback((node) => {
    if (node) { hl.current = nbOf(node); setHover(nodeKey(node)) }
    else if (pinnedRef.current) { hl.current = pinnedRef.current.hl; setHover(pinnedRef.current.key) }  // 悬停离开时保持聚焦选中项
    else { hl.current = { nodes: new Set(), links: new Set() }; setHover(null) }
  }, [nbOf])
  // 点节点:平滑飞入居中 + 高亮相连、淡化无关(对标 @0xDezo 交互)
  const focusNode = useCallback((node) => {
    const hlv = nbOf(node)
    pinnedRef.current = { key: nodeKey(node), hl: hlv }
    hl.current = hlv; setHover(nodeKey(node))
    try { const fg = ref.current; fg.centerAt(node.x, node.y, 650); const z = fg.zoom(); fg.zoom(Math.min(6, Math.max(z, node.cat ? 1.9 : 2.6)), 650) } catch (e) { /* noop */ }
    clickFx.current = { id: nodeKey(node), t: performance.now() * 0.001 }
    if (!node.cat) onOpen(nodeKey(node))   // 分类节点:只聚焦高亮它的文档,不弹详情
  }, [nbOf, onOpen])
  const clearFocus = useCallback(() => { pinnedRef.current = null; hl.current = { nodes: new Set(), links: new Set() }; setHover(null); try { ref.current.zoomToFit(600, 60) } catch (e) {} }, [])

  const anyHover = hover != null
  const searchMode = hiIds && hiIds.size > 0

  const paintNode = useCallback((node, ctx, scale) => {
    if (!Number.isFinite(node.x) || !Number.isFinite(node.y)) return  // 力导未定位前跳过,避免 non-finite
    if (node.hub) {  // 中心枢纽「脑」—— 深色圆角方块(对标参考图中央的黑色「D」块),非圆点
      const hs = 11
      ctx.shadowColor = 'rgba(139, 140, 255,0.55)'; ctx.shadowBlur = 14
      roundRectPath(ctx, node.x - hs, node.y - hs, hs * 2, hs * 2, hs * 0.42)
      ctx.fillStyle = '#0d1220'; ctx.fill()
      ctx.shadowBlur = 0; ctx.lineWidth = 1.2; ctx.strokeStyle = 'rgba(139, 140, 255,0.9)'; ctx.stroke()
      ctx.fillStyle = '#9fecff'; ctx.font = '800 11px -apple-system,"PingFang SC",sans-serif'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'
      ctx.fillText('脑', node.x, node.y + 0.5)
      return
    }
    const k = nodeKey(node)
    if (node.cat) {  // 文件类型中枢:一枚"大一号"的真·文件图标 + 类型名(不是发光圆点)
      const dim2 = anyHover && !hl.current.nodes.has(k)
      const col = node.col || colorOf(node)
      const abbr = FT_ABBR[node.display] || node.display
      const cs = 16                                        // 中枢更大,一眼可辨(类型名常驻)
      ctx.globalAlpha = dim2 ? 0.3 : 1
      drawFileTile(ctx, node.x, node.y, cs, abbr, col)
      ctx.fillStyle = dim2 ? 'rgba(210,220,235,0.45)' : '#eef3fb'
      ctx.font = `800 ${Math.round(cs * 0.66)}px -apple-system,"PingFang SC",sans-serif`; ctx.textAlign = 'center'; ctx.textBaseline = 'top'
      ctx.fillText(String(node.display || '').slice(0, 6), node.x, node.y + cs * 1.35)
      ctx.globalAlpha = 1
      return
    }
    const dimmed = (anyHover && !hl.current.nodes.has(k)) || (searchMode && !hiIds.has(k))
    const isHot = hl.current.nodes.has(k) || (searchMode && hiIds.has(k))
    const color = colorOf(node)
    const isCard = String(node.label || '').startsWith('card') || node.ctype
    const [label] = isCard ? ['卡片'] : ftypeOf(node)
    // 时间驱动的呼吸动画(每个节点相位错开,不同步)
    const t = performance.now() * 0.001
    const phase = (Math.abs(hash(k)) % 628) / 100
    const pulse = 0.5 + 0.5 * Math.sin(t * 1.25 + phase)
    // 只给"过小"的 icon 兜个下限(看得清),大的保持原来的大小,不整体放大
    const s = Math.max(9, nodeRadius(node)) * (isHot ? 1.25 : 1 + pulse * 0.05)
    const op = dimmed ? 0.18 : 1
    // 真·文件图标:白文档 + 折角 + 底部彩色类型徽标(PDF/DOC/PPT/XLS/BOOK…),精细可辨
    ctx.globalAlpha = op
    const abbr = isCard ? '卡片' : (FT_ABBR[label] || label)
    drawFileTile(ctx, node.x, node.y, s, abbr, color)
    ctx.globalAlpha = 1
    // 文件名标签:只在悬停/聚焦该节点及其邻居时显示 —— 平时不显,避免满屏文字墙
    if (isHot && !dimmed) {
      const name = String(node.label || '').split(' · ')[0]
      ctx.globalAlpha = 1
      const fs = Math.max(4.5, s * 0.62)
      ctx.font = `600 ${fs}px -apple-system, "PingFang SC", sans-serif`
      ctx.textAlign = 'center'; ctx.textBaseline = 'top'
      ctx.fillStyle = 'rgba(8,11,20,0.82)'
      const tw = ctx.measureText(name).width
      rr(ctx, node.x - tw / 2 - 3, node.y + s + 2, tw + 6, fs + 3, 2.5); ctx.fill()
      ctx.fillStyle = '#eef2f8'
      ctx.fillText(name, node.x, node.y + s + 3.5)
    }
    // 点击涟漪特效
    if (clickFx.current.id === k) {
      const dt = performance.now() * 0.001 - clickFx.current.t
      if (dt >= 0 && dt < 0.6) {
        const rr2 = s + dt * 46, a = (1 - dt / 0.6) * 0.7
        ctx.globalAlpha = a; ctx.strokeStyle = color; ctx.lineWidth = 1.6
        ctx.beginPath(); ctx.arc(node.x, node.y, rr2, 0, Math.PI * 2); ctx.stroke()
      }
    }
    ctx.globalAlpha = 1
  }, [anyHover, searchMode, hiIds, colorOf])

  const paintPointer = useCallback((node, color, ctx) => {
    if (!Number.isFinite(node.x) || !Number.isFinite(node.y)) return
    if (node.cat || node.hub) { const hs = node.hub ? 12 : 14; ctx.fillStyle = color; rr(ctx, node.x - hs / 2, node.y - hs / 2, hs, hs, hs * 0.3); ctx.fill(); return }
    const s = nodeRadius(node)
    ctx.fillStyle = color; rr(ctx, node.x - s, node.y - s, s * 2, s * 2, s * 0.42); ctx.fill()
  }, [])

  return (
    <ForceGraph2D
      ref={ref} width={dim.w} height={dim.h} graphData={laid}
      backgroundColor={bg} showNavInfo={false} autoPauseRedraw={false}
      nodeVisibility={(n) => n.hub || !hidden.has(groupKey(n))}
      nodeCanvasObjectMode={() => 'replace'}
      nodeCanvasObject={paintNode}
      nodePointerAreaPaint={paintPointer}
      nodeLabel={(n) => n.hub ? '第二大脑' : `<div style="padding:6px 10px;font-size:12px;font-weight:600;color:#edeff3;background:rgba(12,14,20,0.94);border:1px solid rgba(255,255,255,0.1);border-radius:8px">${String(n.label || '').split(' · ')[0]}<div style="font-size:10.5px;font-weight:400;color:#9aa0aa;margin-top:1px">${ftypeOf(n)[0]} · 点击打开</div></div>`}
      linkColor={(l) => (hl.current.links.has(l) ? 'rgba(150,180,255,0.95)' : (anyHover || searchMode ? 'rgba(130,145,180,0.04)' : (l.tree ? 'rgba(150,170,210,0.11)' : 'rgba(130,145,180,0.09)')))}
      linkWidth={(l) => (hl.current.links.has(l) ? 1.8 : 0.4)}
      linkCurvature={0.18}
      linkDirectionalParticles={(l) => (hl.current.links.has(l) ? 3 : 0)}
      linkDirectionalParticleWidth={2} linkDirectionalParticleSpeed={0.01}
      linkDirectionalParticleColor={() => '#aac4ff'}
      linkVisibility={(l) => { const s = l.source, t = l.target; const sk = typeof s === 'object' ? groupKey(s) : null; const tk = typeof t === 'object' ? groupKey(t) : null; return !(hidden.has(sk) || hidden.has(tk)) }}
      onNodeHover={onHover}
      onNodeClick={(n) => { if (n.hub) { clearFocus(); return } focusNode(n) }}
      onBackgroundClick={clearFocus}
      enableNodeDrag={true} enablePanInteraction={false}
      warmupTicks={80} cooldownTicks={Infinity} cooldownTime={Infinity}
      d3AlphaDecay={0} d3VelocityDecay={0.82}
    />
  )
}

// 文档模式:按文件类型排成同心环(对标 CyrilXBT),固定坐标
function radialLayout(nodes) {
  const groups = {}
  nodes.forEach((n) => { const k = ftypeOf(n)[0]; (groups[k] = groups[k] || []).push(n) })
  const keys = Object.keys(groups).sort((a, b) => groups[b].length - groups[a].length)
  keys.forEach((k, gi) => {
    const ring = groups[k]
    const radius = 55 + gi * 52
    ring.forEach((n, i) => {
      const a = (i / ring.length) * Math.PI * 2 + gi * 0.35
      n.fx = Math.cos(a) * radius; n.fy = Math.sin(a) * radius; n.fz = 0
    })
  })
}

// 现代、互相区分度高的社区配色(不用银河预设那套白/黄)
const CHAT_PAL = ['#5b8def', '#e0567a', '#28b487', '#e0a13a', '#9b6ef0', '#39a0c4', '#d16ba5', '#5fae5f', '#e07b53', '#4aa3a3', '#c05fe0', '#7a86e0']
// 探索视图偏好持久化(记住上次的风格/档位/调节)
function _lsGet(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v) } catch (e) { return d } }
function _lsSet(k, v) { try { localStorage.setItem(k, JSON.stringify(v)) } catch (e) { /* noop */ } }
// #rrggbb + alpha(0..1) → rgba();画星云光晕/描边用
function hexA(hex, a) {
  const h = (hex || '#000').replace('#', '')
  const r = parseInt(h.slice(0, 2), 16), g = parseInt(h.slice(2, 4), 16), b = parseInt(h.slice(4, 6), 16)
  return `rgba(${r},${g},${b},${a})`
}
// ===== 仅聊天:2D 社区力导图 =====
function ChatNet2D({ data, dim, colorOf, onOpen, hidden, groupKey }) {
  const ref = useRef()
  const [hover, setHover] = useState(null)
  const colorC = (n) => CHAT_PAL[Math.abs(n.cluster || 0) % CHAT_PAL.length]
  const adjm = useMemo(() => {
    const m = new Map()
    data.nodes.forEach((n) => m.set(n.id, new Set()))
    data.links.forEach((l) => {
      const s = typeof l.source === 'object' ? l.source.id : l.source
      const t = typeof l.target === 'object' ? l.target.id : l.target
      if (m.has(s)) m.get(s).add(t); if (m.has(t)) m.get(t).add(s)
    })
    return m
  }, [data])
  const nodeR = (n) => 3.5 + Math.min((n.degree || 0) * 0.85, 13)
  useEffect(() => {
    const fg = ref.current; if (!fg) return
    try {
      fg.d3Force('charge').strength(-150).distanceMax(340)
      fg.d3Force('link').distance(46).strength(0.09)
      const c = fg.d3Force('center'); if (c) c.strength(0.04)
      fg.d3Force('collide', forceCollide((n) => nodeR(n) + 5).strength(1).iterations(2))
    } catch (e) { /* noop */ }
    const t = setTimeout(() => { try { fg.zoomToFit(700, 60) } catch (e) {} }, 1400)
    return () => clearTimeout(t)
  }, [data])
  const paint = useCallback((n, ctx, scale) => {
    if (!Number.isFinite(n.x) || !Number.isFinite(n.y)) return
    const r = nodeR(n)
    const col = colorC(n)
    const active = !hover || n.id === hover || (adjm.get(hover) || new Set()).has(n.id)
    ctx.globalAlpha = active ? 1 : 0.12
    ctx.beginPath(); ctx.arc(n.x, n.y, r, 0, 2 * Math.PI)
    ctx.fillStyle = col; ctx.fill()
    ctx.lineWidth = 1 / scale; ctx.strokeStyle = 'rgba(8,11,20,0.9)'; ctx.stroke()
    // 标签只在:悬停高亮 / 极少数大枢纽 / 明显放大时显(治407个名字全糊一起)
    if ((hover && active) || (!hover && (n.degree || 0) >= 22) || scale > 2.6) {
      const label = String(n.label || n.id).slice(0, 10)
      const fs = Math.max(6, 11.5 / scale)
      ctx.font = `600 ${fs}px -apple-system, "SF Pro Text", sans-serif`
      ctx.textAlign = 'center'; ctx.textBaseline = 'top'
      const tw = ctx.measureText(label).width, pad = 4 / scale, ly = n.y + r + 4 / scale
      ctx.fillStyle = 'rgba(9,11,17,0.8)'
      ctx.beginPath()
      if (ctx.roundRect) ctx.roundRect(n.x - tw / 2 - pad, ly - pad * 0.4, tw + pad * 2, fs + pad, 3 / scale)
      else ctx.rect(n.x - tw / 2 - pad, ly - pad * 0.4, tw + pad * 2, fs + pad)
      ctx.fill()
      ctx.fillStyle = '#f2f4fa'; ctx.fillText(label, n.x, ly)
    }
    ctx.globalAlpha = 1
  }, [hover, adjm, colorOf])
  return (
    <ForceGraph2D ref={ref} width={dim.w} height={dim.h} graphData={data} backgroundColor="#080b14"
      nodeCanvasObject={paint} nodeCanvasObjectMode={() => 'replace'}
      nodePointerAreaPaint={(n, c, ctx) => { ctx.fillStyle = c; ctx.beginPath(); ctx.arc(n.x, n.y, nodeR(n) + 3, 0, 2 * Math.PI); ctx.fill() }}
      nodeVisibility={(n) => !hidden.has(groupKey(n))}
      linkVisibility={(l) => { const s = l.source, t = l.target; const sk = typeof s === 'object' ? groupKey(s) : null; const tk = typeof t === 'object' ? groupKey(t) : null; return !(hidden.has(sk) || hidden.has(tk)) }}
      linkColor={(l) => {
        if (!hover) return 'rgba(150,160,190,0.09)'
        const s = typeof l.source === 'object' ? l.source.id : l.source, t = typeof l.target === 'object' ? l.target.id : l.target
        return (s === hover || t === hover) ? 'rgba(190,205,255,0.6)' : 'rgba(150,160,190,0.03)'
      }}
      linkWidth={(l) => Math.min(2.4, (l.weight || 1) * 0.3)}
      onNodeHover={(n) => setHover(n ? n.id : null)}
      onNodeClick={(n) => onOpen && onOpen(nodeKey(n))}
      cooldownTicks={150} enableNodeDrag={true} />
  )
}

// 探索·仅聊天(方案A):把全部微信聊天内容按语义聚成「主题星系」。
// 每颗星=一段聊天,预置坐标(秒开·无白闪·不漂移),按主题上色;簇中心飘**真实主题名**(非簇1/簇2)。
// 设计参考:Nomic Atlas / embedding-atlas 的点云+区域标签范式——现代、克制,不用发光大球那种俗套。
function TopicGalaxy2D({ data, centers, dim, onOpen, focusReq }) {
  const ref = useRef()
  const tRef = useRef(0)          // 动画时钟(秒)
  const rotRef = useRef(0)        // 全景缓慢自转角(聚焦时暂停)
  const spreadRef = useRef(1)     // 聚焦某簇时该簇星点"绽放展开"系数(1=原状,聚焦→~2.4)
  const linksRef = useRef([])     // 同簇最近邻连线(星座感),载入时预算一次
  const bornRef = useRef(0)       // 本次数据载入时刻,做入场动画
  const [hoverC, setHoverC] = useState(null)   // 悬停的主题簇
  const [focusC, setFocusC] = useState(null)   // 已放大聚焦的主题簇(null=全景)
  const focusRef = useRef(null); focusRef.current = focusC
  const hoverRef = useRef(null); hoverRef.current = hoverC
  const colorC = (c) => CHAT_PAL[Math.abs(c || 0) % CHAT_PAL.length]
  // 预置坐标 → 关掉力学(节点靠 fx/fy 钉住不动),但让仿真"常热"(d3AlphaDecay=0)→ 每帧回调 onRenderFramePre 持续触发 →
  // 动画由此驱动(★1.29.1 没有 refresh(),之前用它驱动=一帧没动,这才是真正能跑的办法)。tRef 在 preFrame 里推进。
  useEffect(() => {
    const fg = ref.current; if (!fg) return
    tRef.current = 0; rotRef.current = 0; spreadRef.current = 1
    const nodes = data.nodes || []
    // 极坐标(自转用)+ 每颗星的浮动相位/速度(漂移动画)
    nodes.forEach((n) => {
      if (n._r0 == null) { n._r0 = Math.hypot(n.x || 0, n.y || 0); n._a0 = Math.atan2(n.y || 0, n.x || 0) }
      if (n._fp == null) { n._fp = (Math.abs(hash(n.id)) % 6283) / 1000; n._fs = 0.5 + (Math.abs(hash('f' + n.id)) % 60) / 100 }
    })
    ;(centers || []).forEach((c) => { if (c._r0 == null) { c._r0 = Math.hypot(c.x || 0, c.y || 0); c._a0 = Math.atan2(c.y || 0, c.x || 0) } })
    // 力学:全景时所有节点被 fx/fy 钉住→力不生效(靠 preFrame 手动动画);
    //       钻进某主题时解钉该簇→charge(局部斥力)+link(星座连线)+x/y(拉回簇心)让它变成"活的力导图",可拖、拖一个连着的跟着动。
    try {
      fg.d3Force('charge').strength(-42).distanceMax(150)
      fg.d3Force('link').distance(30).strength(0.35)
      fg.d3Force('center', null)
      fg.d3Force('x', d3ForceX((n) => (n.__tx != null ? n.__tx : 0)).strength((n) => (n.__unpin ? 0.07 : 0)))
      fg.d3Force('y', d3ForceY((n) => (n.__ty != null ? n.__ty : 0)).strength((n) => (n.__unpin ? 0.07 : 0)))
    } catch (e) {}
    try { fg.d3ReheatSimulation() } catch (e) {}
    const t = setTimeout(() => { try { fg.zoomToFit(700, 46) } catch (e) {} }, 120)  // 少留白=框得更近,文字更清
    return () => { clearTimeout(t) }
  }, [data, centers])
  // 右侧「语义簇」列表点某个主题 → 钻进该主题(放大聚焦),而不是隐藏
  useEffect(() => {
    if (focusReq && typeof focusReq.cluster !== 'undefined') focusCluster(focusReq.cluster)
    // eslint-disable-next-line
  }, [focusReq && focusReq.seq])
  const focusCluster = useCallback((cl) => {
    const fg = ref.current; if (!fg) return
    const nodes = (data && data.nodes) || []
    if (cl == null) {
      // 退出:所有节点重新钉回环形基准位置,回到全景手动动画
      const rot = rotRef.current
      for (const n of nodes) { n.__unpin = false; n.__drag = false; if (n._r0 != null) { n.fx = n.x = n._r0 * Math.cos(n._a0 + rot); n.fy = n.y = n._r0 * Math.sin(n._a0 + rot) } }
      setFocusC(null)
      try { fg.d3ReheatSimulation() } catch (e) {}
      setTimeout(() => { try { fg.zoomToFit(700, 46) } catch (e) {} }, 60)
      return
    }
    // 钻进:解钉该簇→力学接管(活的力导图,可拖、拖一个连着的跟着动);其余簇仍钉住(隐去)
    let cen = null; for (const c of centers) if (c.cluster === cl) cen = c
    const tx = cen ? cen.x : 0, ty = cen ? cen.y : 0
    for (const n of nodes) {
      if (n.cluster === cl) { n.__unpin = true; n.__tx = tx; n.__ty = ty; n.fx = null; n.fy = null }
      else { n.__unpin = false }
    }
    setFocusC(cl)
    try { fg.d3ReheatSimulation() } catch (e) {}
    try { fg.zoomToFit(700, 90, (n) => (n.cluster || 0) === cl) } catch (e) {}
    setTimeout(() => { try { fg.zoomToFit(700, 70, (n) => (n.cluster || 0) === cl) } catch (e) {} }, 900)
  }, [centers, data])
  // 点空白/点主题名 → 就近找簇心:在某簇星云范围内=放大聚焦该主题;空白处=复位全景
  const bgClick = useCallback((e) => {
    const fg = ref.current; if (!fg) return
    let gp; try { gp = fg.screen2GraphCoords(e.offsetX != null ? e.offsetX : e.layerX, e.offsetY != null ? e.offsetY : e.layerY) } catch (_) { return }
    let best = null, bd = 1e9
    for (const c of centers) { const d = Math.hypot(c.x - gp.x, c.y - gp.y); if (d < bd) { bd = d; best = c } }
    if (best && bd < 300) focusCluster(best.cluster)
    else focusCluster(null)
  }, [centers, focusCluster])
  // 某簇是否"点亮":无悬停无聚焦=全亮;否则命中悬停或聚焦簇才亮(用 ref,避免 rAF 里读到旧闭包)
  const lit = (cl) => (hoverRef.current == null && focusRef.current == null) || cl === hoverRef.current || cl === focusRef.current
  const ease = (p) => 1 - Math.pow(1 - Math.min(Math.max(p, 0), 1), 3)
  // 星云底光:每个主题一团柔和径向光晕(16 团,便宜),缓慢呼吸=有生命感又不俗
  const preFrame = useCallback((ctx, scale) => {
    tRef.current += 0.016   // ★动画时钟在每帧回调里推进(仿真常热→此回调持续被调用)
    const t = tRef.current, enter = ease(t / 0.9)
    const fc = focusRef.current
    const nodes = data.nodes || []
    // 全景态:所有节点钉住,手动做自转+浮动(活的星系);聚焦态:该簇解钉交给力学(preFrame 不覆盖它们)
    if (fc == null) {
      rotRef.current += 0.00055                              // 全景缓慢自转
      const rot = rotRef.current
      for (const c of centers) { if (c._r0 != null) { c.x = c._r0 * Math.cos(c._a0 + rot); c.y = c._r0 * Math.sin(c._a0 + rot) } }
      for (const n of nodes) {
        if (n._r0 == null || n.__drag) continue
        n.x = n.fx = n._r0 * Math.cos(n._a0 + rot) + Math.sin(t * n._fs + n._fp) * 3.4
        n.y = n.fy = n._r0 * Math.sin(n._a0 + rot) + Math.cos(t * n._fs * 0.92 + n._fp) * 3.4
      }
    }
    // 星云底光(簇心柔和光晕,缓慢呼吸)
    for (const c of centers) {
      const puls = 1 + 0.05 * Math.sin(t * 0.6 + c.cluster * 0.7)
      const rad = (60 + Math.sqrt(c.count || 1) * 26) * puls * (0.6 + 0.4 * enter)
      const g = ctx.createRadialGradient(c.x, c.y, 0, c.x, c.y, rad)
      const col = colorC(c.cluster)
      g.addColorStop(0, hexA(col, (lit(c.cluster) ? 0.17 : 0.04) * enter))
      g.addColorStop(1, hexA(col, 0))
      ctx.fillStyle = g
      ctx.beginPath(); ctx.arc(c.x, c.y, rad, 0, 2 * Math.PI); ctx.fill()
    }
  }, [centers, data])
  const paintNode = useCallback((n, ctx, scale) => {
    if (!Number.isFinite(n.x) || !Number.isFinite(n.y)) return
    const t = tRef.current
    const on = lit(n.cluster)
    const ph = (Math.abs(hash(n.id)) % 6283) / 1000
    const enter = ease((t - Math.abs(hash(n.id)) % 500 / 900))   // 逐颗错峰浮现
    const tw = 0.72 + 0.28 * Math.sin(t * 1.7 + ph)              // 闪烁
    const rScreen = (on && focusRef.current != null ? 2.6 : 2.0) // 恒定屏幕像素=拉近也清晰
    const r = (rScreen / scale) * (0.3 + 0.7 * enter)
    ctx.globalAlpha = (on ? 0.9 * tw : 0.07) * enter
    ctx.beginPath(); ctx.arc(n.x, n.y, r, 0, 2 * Math.PI)
    ctx.fillStyle = colorC(n.cluster); ctx.fill()
    ctx.globalAlpha = 1
  }, [])
  // 主题名:飘在每簇中心(始终可见=用户一眼读到真话题),恒定屏幕字号=远近都清楚
  const postFrame = useCallback((ctx, scale) => {
    const t = tRef.current, enter = ease((t - 0.35) / 0.8)
    if (enter <= 0.01) return
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle'
    const hot = (c) => c.cluster === hoverRef.current || c.cluster === focusRef.current
    const ordered = [...centers].sort((a, b) => (hot(a) ? 1 : 0) - (hot(b) ? 1 : 0))
    for (const c of ordered) {
      const active = lit(c.cluster)
      const fs = (hot(c) ? 15 : 12.5) / scale        // 恒定屏幕像素字号
      const label = c.name || '主题'
      ctx.font = `700 ${fs}px -apple-system, "SF Pro Text", sans-serif`
      const tw = ctx.measureText(label).width, padX = 8 / scale, padY = 4.5 / scale, h = fs + padY * 2
      ctx.globalAlpha = (active ? 1 : 0.3) * enter
      ctx.fillStyle = 'rgba(10,13,22,0.74)'
      ctx.beginPath()
      if (ctx.roundRect) ctx.roundRect(c.x - tw / 2 - padX, c.y - h / 2, tw + padX * 2, h, 6 / scale)
      else ctx.rect(c.x - tw / 2 - padX, c.y - h / 2, tw + padX * 2, h)
      ctx.fill()
      ctx.lineWidth = 1 / scale; ctx.strokeStyle = hexA(colorC(c.cluster), active ? 0.85 : 0.3); ctx.stroke()
      ctx.fillStyle = active ? '#fff' : 'rgba(240,243,250,0.6)'; ctx.fillText(label, c.x, c.y)
    }
    ctx.globalAlpha = 1
  }, [centers])
  return (
    <ForceGraph2D ref={ref} width={dim.w} height={dim.h} graphData={data} backgroundColor="#080b14"
      cooldownTicks={Infinity} warmupTicks={0} d3AlphaDecay={0} d3AlphaMin={0} d3VelocityDecay={0.45}
      enableNodeDrag={focusC != null}
      onNodeDrag={(n) => { n.__drag = true }}
      onNodeDragEnd={(n) => { n.__drag = false }}
      autoPauseRedraw={false}
      nodeCanvasObject={paintNode} nodeCanvasObjectMode={() => 'replace'}
      nodePointerAreaPaint={(n, c, ctx) => { ctx.fillStyle = c; ctx.beginPath(); ctx.arc(n.x, n.y, 6 / (ref.current ? Math.max(ref.current.zoom() || 1, 0.3) : 1), 0, 2 * Math.PI); ctx.fill() }}
      onRenderFramePre={preFrame} onRenderFramePost={postFrame}
      linkColor={(l) => { const cl = l.cluster != null ? l.cluster : (l.source && l.source.cluster); return hexA(colorC(cl), lit(cl) ? 0.16 : 0.02) }}
      linkWidth={(l) => { const cl = l.cluster != null ? l.cluster : (l.source && l.source.cluster); return lit(cl) ? 0.7 : 0.4 }}
      nodeLabel={(n) => `<div style="padding:5px 10px;font-size:12px;font-weight:600;color:#edeff3;background:rgba(12,14,20,0.95);border:1px solid rgba(255,255,255,0.12);border-radius:7px">与 ${n.label || ''} 的聊天<div style="font-size:10px;font-weight:400;color:#9aa0aa;margin-top:1px">点击看这位联系人的情报卡</div></div>`}
      onNodeHover={(n) => setHoverC(n ? n.cluster : null)}
      onNodeClick={(n) => onOpen && onOpen(n.doc_id != null ? n.doc_id : n.id)}
      onBackgroundClick={bgClick} />
  )
}

export default function Explore({ onOpen }) {
  const fgRef = useRef(); const hostRef = useRef(); const bloomRef = useRef(null); const starRef = useRef([])
  const coreRef = useRef(null); const nebRef = useRef(null); const auroraRef = useRef(null); const fxRafRef = useRef(null)
  const nodeSpritesRef = useRef([])   // 所有星点精灵(呼吸动画注册表)
  const coreBaseRef = useRef({ s: 22, op: 0.9 })  // 亮核基准尺寸/透明度(呼吸)
  const [data, setData] = useState(null)
  const [clusterNames, setClusterNames] = useState([])
  const [centers, setCenters] = useState([])   // 主题星系:簇中心(飘主题名)
  const [topicFocus, setTopicFocus] = useState({ cluster: null, seq: 0 })   // 点右侧主题→钻进哪个簇
  const [dim, setDim] = useState({ w: 800, h: 600 })
  const [q, setQ] = useState(''); const [hi, setHi] = useState(null)
  const [presetKey, setPresetKey] = useState(() => _lsGet('ex_preset', 'galaxy'))
  const [mode, setMode] = useState(() => _lsGet('ex_mode', 'star'))
  const [grain, setGrain] = useState(() => _lsGet('ex_grain', 'medium'))
  const [colorBy, setColorBy] = useState('ftype')  // 默认按文件类型上色(内圈=文件类型)
  const [hidden, setHidden] = useState(() => new Set())
  const [chatOnly, setChatOnly] = useState(false)   // 仅看微信聊天星云
  const [adj, setAdj] = useState(() => _lsGet('ex_adj', { bloom: 1.15, charge: -160, dist: 55, dims: 3, size: 7 }))
  const [showAdj, setShowAdj] = useState(false)
  // 颜色组面板收缩状态(记忆到 localStorage)
  const [groupsCollapsed, setGroupsCollapsed] = useState(() => {
    try { return localStorage.getItem('explore_groups_collapsed') === '1' } catch (e) { return false }
  })
  const toggleGroups = useCallback(() => setGroupsCollapsed((c) => {
    const nx = !c; try { localStorage.setItem('explore_groups_collapsed', nx ? '1' : '0') } catch (e) {}
    return nx
  }), [])

  const preset = PRESETS.find((p) => p.key === presetKey)
  const presetRef = useRef(preset); presetRef.current = preset
  const grainRef = useRef(grain); grainRef.current = grain   // 档位实时引用(供 buildStars/rAF/bloom 读,免陈旧闭包)
  const adjRef = useRef(adj); adjRef.current = adj            // 调节值实时引用(供记忆化的精灵工厂读当前值)
  // 调节·节点 → 尺寸系数;调节·辉光 → 星点亮度(bloom 已移除,辉光改控发光点透明度)
  const sizeMulOf = (a) => (a.size || 1.6) / 1.6
  const glowOpOf = (a) => Math.min(1, 0.32 + (a.bloom || 1.15) * 0.5)
  const isStar = mode === 'star'

  // 分组键:簇 index 或 文件类型 label
  const groupKey = useCallback((n) => (colorBy === 'ftype' ? ftypeOf(n)[0] : (n.cluster != null ? n.cluster : 0)), [colorBy])
  const colorOf = useCallback((n) => {
    if (colorBy === 'ftype') return ftypeOf(n)[1]
    const pal = presetRef.current.palette
    const c = n.cluster != null ? n.cluster : Math.abs(hash(n.id))
    return pal[Math.abs(c) % pal.length]
  }, [colorBy])

  // ★记忆化的星点工厂:只在预设/高亮/配色变时重建精灵;点「调节」等普通重绘不再重建(治闪白 + 保住滑杆效果)。
  //   尺寸/亮度从 adjRef 读当前值,所以重建出来的精灵也符合当前「节点/辉光」滑杆。
  const starObject = useCallback((n) => {
    if (hi && !hi.has(nodeKey(n))) { const d = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTexture(), color: new THREE.Color('#2b2f3a'), transparent: true, depthWrite: false, opacity: 0.4 })); d.scale.set(nodeRadius(n) * 1.6, nodeRadius(n) * 1.6, 1); return d }
    return makeStarSprite(n, presetRef.current, colorOf, nodeSpritesRef.current, sizeMulOf(adjRef.current), glowOpOf(adjRef.current))
  }, [hi, colorOf, presetKey])

  useEffect(() => {
    setData(null); setHi(null); setHidden(new Set())
    nodeSpritesRef.current = []   // 清空呼吸注册表,避免跨加载的陈旧精灵累积
    // 仅聊天:全部 1:1 联系人按聊天内容相似度连成语义星系(chat_galaxy,覆盖全部联系人,和洞察的机构关系网区分)
    if (chatOnly) {
      // 方案A:全部聊天内容按语义聚成「主题星系」——每颗星=一段聊天,预置坐标(秒开),簇=真实主题名
      api.chatTopicGalaxy().then((g) => {
        setClusterNames((g.communities || []).map((c) => c.name))
        setCenters(g.centers || [])
        const nodes = (g.nodes || []).map((n) => ({
          id: n.id, label: n.label, doc_id: n.doc_id, cluster: n.cluster || 0,
          x: n.x, y: n.y, fx: n.x, fy: n.y, wx: true,
        }))
        // 同簇最近邻连线(星座 + 聚焦力导用):每颗星连它同簇最近一颗,去重
        const byC = {}
        nodes.forEach((n, i) => { (byC[n.cluster] = byC[n.cluster] || []).push(i) })
        const links = [], seen = new Set()
        for (const ci in byC) {
          const idx = byC[ci]
          if (idx.length > 900) continue
          for (const i of idx) {
            let best = -1, bd = 1e18; const ni = nodes[i]
            for (const j of idx) { if (j === i) continue; const nj = nodes[j], dx = ni.x - nj.x, dy = ni.y - nj.y, d = dx * dx + dy * dy; if (d < bd) { bd = d; best = j } }
            if (best >= 0) { const key = i < best ? i + ',' + best : best + ',' + i; if (!seen.has(key)) { seen.add(key); links.push({ source: nodes[i].id, target: nodes[best].id, cluster: nodes[i].cluster }) } }
          }
        }
        setData({ nodes, links })
      }).catch(() => { setCenters([]); setData({ nodes: [], links: [] }) })
      return
    }
    const chunk = GRAINS.find((g) => g.key === grain).chunk
    const load = mode === 'star' ? api.starmap(chunk) : api.graph()
    load.then((g) => {
      setClusterNames(g.cluster_names || [])
      // ★根治"爆闪白":给每个节点预置一个散开的初始坐标(球面确定性分布),绝不让它们一开始堆在原点
      //   (发光精灵叠加=白;散开起步就不会有那一下白闪),力导再从散开状态自然收拢。
      const N = g.nodes.length, R = 260 + Math.sqrt(N) * 9
      const nodes = g.nodes.map((n, i) => {
        const y = 1 - (i + 0.5) / N * 2, rr = Math.sqrt(Math.max(0, 1 - y * y)), ph = i * 2.399963
        return { ...n, x: Math.cos(ph) * rr * R, y: y * R, z: Math.sin(ph) * rr * R }
      })
      setData({ nodes, links: g.edges.map((e) => ({ source: e.source, target: e.target, weight: e.weight })) })
    }).catch(() => setData({ nodes: [], links: [] }))
  }, [mode, grain, chatOnly])

  useEffect(() => { setHidden(new Set()) }, [colorBy])
  // 文档模式=按语义分类上色(同心圆环每圈一色);可切文件类型
  useEffect(() => { setColorBy(chatOnly ? 'cluster' : (mode === 'doc' ? 'ftype' : 'cluster')) }, [mode, chatOnly])

  useEffect(() => {
    const el = hostRef.current; if (!el) return
    const ro = new ResizeObserver(() => setDim({ w: el.clientWidth, h: el.clientHeight }))
    ro.observe(el); return () => ro.disconnect()
  }, [])

  // 图例分组
  const groups = useMemo(() => {
    if (!data) return []
    const pal = preset.palette; const map = new Map()
    for (const n of data.nodes) {
      let key, name, color
      if (!chatOnly && colorBy === 'ftype') { const [nm, col] = ftypeOf(n); key = nm; name = nm; color = col }
      else { const c = n.cluster != null ? n.cluster : 0; key = c; name = clusterNames[c] || ('主题' + (c + 1)); color = (chatOnly ? CHAT_PAL : pal)[Math.abs(c) % (chatOnly ? CHAT_PAL : pal).length] }
      if (!map.has(key)) map.set(key, { key, name, color, count: 0 })
      map.get(key).count++
    }
    return [...map.values()].sort((a, b) => b.count - a.count)
  }, [data, colorBy, clusterNames, presetKey])  // eslint-disable-line

  const toggleHidden = (key) => setHidden((s) => { const n = new Set(s); n.has(key) ? n.delete(key) : n.add(key); return n })

  // 多层星尘:远层暗小、近层疏亮;都推到外圈(rIn 起步),不糊中心 → 中心通透
  const buildStars = useCallback((p) => {
    const fg = fgRef.current; if (!fg) return
    const scene = fg.scene(); if (!scene) return
    for (const s of starRef.current) { scene.remove(s); s.geometry.dispose(); s.material.dispose() }
    starRef.current = []
    // 星尘密度随档位缩减(粗档只留 1/4 → draw 的点数大幅下降)
    const dustMul = grainPerf(grainRef.current).dustMul
    const layers = (p.starLayers || [{ n: 1400, c: '#9fb0d8', size: 0.7, op: 0.45, rIn: 640 }])
      .map((L) => ({ ...L, n: Math.max(40, Math.round(L.n * dustMul)) }))
    let seed = 1
    const rnd = () => { seed = (seed * 1664525 + 1013904223) % 4294967296; return seed / 4294967296 }
    layers.forEach((L) => {
      const pos = new Float32Array(L.n * 3)
      for (let i = 0; i < L.n; i++) {
        const r = L.rIn + Math.pow(rnd(), 0.7) * 1600
        const th = rnd() * Math.PI * 2, ph = Math.acos(1 - 2 * rnd())
        pos[i * 3] = r * Math.sin(ph) * Math.cos(th); pos[i * 3 + 1] = r * Math.sin(ph) * Math.sin(th); pos[i * 3 + 2] = r * Math.cos(ph)
      }
      const geo = new THREE.BufferGeometry(); geo.setAttribute('position', new THREE.BufferAttribute(pos, 3))
      const mat = new THREE.PointsMaterial({ map: dustTexture(), color: new THREE.Color(L.c), size: L.size * 2.6, sizeAttenuation: true, transparent: true, opacity: L.op, blending: THREE.AdditiveBlending, depthWrite: false })
      const pts = new THREE.Points(geo, mat); pts.renderOrder = -2; pts.userData.baseOp = L.op; scene.add(pts); starRef.current.push(pts)
    })
  }, [])

  // 按档位调 bloom: 粗档直接关(bloomMul=0),中/细降强度;并按 bloomRes 缩小 bloom 内部渲染分辨率(最贵的部分)
  const tuneBloom = useCallback(() => {
    const fg = fgRef.current, b = bloomRef.current; if (!fg || !b) return
    const on = mode === 'star'
    const p = presetRef.current, perf = grainPerf(grainRef.current)
    b.strength = on ? Math.min(1.5, p.bloom.s * perf.bloomMul) : 0   // 封顶,防辉光过曝把整屏冲成白
    b.radius = p.bloom.r; b.threshold = Math.max(0.55, p.bloom.t)   // 阈值下限,只让最亮的核发光,不糊全屏
    try {
      const el = fg.renderer && fg.renderer().domElement
      if (el) b.setSize(Math.max(64, Math.round(el.width * perf.bloomRes)), Math.max(64, Math.round(el.height * perf.bloomRes)))
    } catch (e) { /* noop */ }
  }, [mode])

  const applyPreset = useCallback((p) => {
    const fg = fgRef.current; if (!fg) return
    try {
      const on = mode === 'star'
      if (bloomRef.current) { const b = bloomRef.current; const perf = grainPerf(grainRef.current); b.strength = on ? Math.min(1.5, p.bloom.s * perf.bloomMul) : 0; b.radius = p.bloom.r; b.threshold = Math.max(0.55, p.bloom.t); tuneBloom() }
      if (fg.d3Force('charge')) fg.d3Force('charge').strength(p.charge)
      if (fg.d3Force('link')) fg.d3Force('link').distance(p.dist)
      const c = fg.d3Force('center'); if (c && c.strength) { try { c.strength(p.gravity || 0.06) } catch (e) {} }
      const scene = fg.scene()
      // 密核
      if (coreRef.current) { scene.remove(coreRef.current); coreRef.current.material.dispose(); coreRef.current = null }
      if (on && p.layout !== 'scatter' && p.layout !== 'disk') { coreRef.current = makeCoreSprite(p); coreBaseRef.current = { s: p.coreSize || 22, op: 0.9 }; scene.add(coreRef.current) }
      // 暗星云层
      if (nebRef.current) { scene.remove(nebRef.current); nebRef.current.geometry.dispose(); nebRef.current.material.dispose(); nebRef.current = null }
      if (on && p.nebula) { nebRef.current = makeNebula(p); scene.add(nebRef.current) }
      // 极光飘带
      if (auroraRef.current) { scene.remove(auroraRef.current); auroraRef.current.geometry.dispose(); auroraRef.current.material.dispose(); auroraRef.current = null }
      if (on && p.aurora) { auroraRef.current = makeAurora(); scene.add(auroraRef.current) }
      fg.d3ReheatSimulation && fg.d3ReheatSimulation(); buildStars(p)
    } catch (e) { /* noop */ }
  }, [buildStars, mode, tuneBloom])

  // ★ 星海生命感动画:shader 层(星云/极光漂动)+ 星点错相位呼吸 + 星尘极缓脉动 + 亮核呼吸。
  //   常驱 rAF(autoPauseRedraw={false} 配合),autoRotate 由 controls 每帧推进,画面持续微动不"卡死"。
  //   仅星海模式做重活;非星海只维持轻量(避免浪费)。切模式/卸载时 cancelAnimationFrame 清理。
  useEffect(() => {
    let alive = true
    let sliceCursor = 0                 // 分帧游标:每帧只处理精灵数组的一段
    let lastShader = 0                   // shader/星尘/核 的低频节流(30fps 足够)
    const tick = () => {
      if (!alive) return
      // B1:页面/App 不可见时跳过这一帧重活(移动端 webview 不一定自动降 rAF),下一帧再判;可见时完全照旧
      if (typeof document !== 'undefined' && document.hidden) { fxRafRef.current = requestAnimationFrame(tick); return }
      const t = performance.now() * 0.001
      // shader 层(便宜,但仍节流到 ~30fps)
      const doShader = (t - lastShader) > 0.033
      if (doShader) {
        lastShader = t
        if (nebRef.current) nebRef.current.material.uniforms.uTime.value = t
        if (auroraRef.current) auroraRef.current.material.uniforms.uTime.value = t
      }
      const perf = grainPerf(grainRef.current)
      if (isStar && perf.pulse) {
        // ★ 分帧呼吸:每帧只更新 1/pulseSlice 的精灵(其余帧轮到才更新)。
        //   2683 精灵不再每帧全遍历 → 逐帧 JS 成本降到 1/N,视觉上仍连续呼吸。
        const arr = nodeSpritesRef.current
        const n = arr.length
        if (n > 0) {
          const slices = Math.max(1, perf.pulseSlice)
          const per = Math.ceil(n / slices)
          const start = sliceCursor % n
          let compact = false
          for (let j = 0; j < per; j++) {
            const i = (start + j) % n
            const sp = arr[i]
            if (!sp || !sp.parent) { compact = true; continue }
            const u = sp.userData.pulse; if (!u) continue
            const b = 0.5 + 0.5 * Math.sin(t * u.speed + u.phase)
            sp.material.opacity = u.baseOp * (1 - u.amp * 0.9 * (1 - b))
            const sc = u.base * (1 + u.amp * 0.14 * (b - 0.5))
            sp.scale.set(sc, sc, 1)
          }
          sliceCursor = (start + per) % n
          if (compact) nodeSpritesRef.current = arr.filter((s) => s && s.parent)
        }
        if (doShader) {
          // 星尘 + 亮核呼吸:低频(30fps 节流),便宜
          for (const pts of starRef.current) {
            if (pts && pts.material) pts.material.opacity = (pts.userData.baseOp || pts.material.opacity) * (0.9 + 0.1 * Math.sin(t * 0.25))
          }
          if (coreRef.current) {
            const cb = coreBaseRef.current, cp = 0.5 + 0.5 * Math.sin(t * 0.6)
            coreRef.current.material.opacity = cb.op * (0.82 + 0.18 * cp)
            const cs = cb.s * (1 + 0.06 * (cp - 0.5))
            coreRef.current.scale.set(cs, cs, 1)
          }
        }
      }
      fxRafRef.current = requestAnimationFrame(tick)
    }
    fxRafRef.current = requestAnimationFrame(tick)
    return () => { alive = false; if (fxRafRef.current) cancelAnimationFrame(fxRafRef.current) }
  }, [isStar])

  useEffect(() => {
    const fg = fgRef.current; if (!fg || !data) return
    const t = setTimeout(() => {
      try {
        const perf = grainPerf(grainRef.current)
        // ★ 关键性能项: 硬顶 pixelRatio(高分屏默认 2~3x → 4~9 倍像素负载,这里按档位封到 1~1.5x)
        const r = fg.renderer && fg.renderer()
        if (r) r.setPixelRatio(Math.min(window.devicePixelRatio || 1, perf.pixelRatio))
        // ★ 已彻底移除 bloom:清晰发光点风格(像 Obsidian),密处不糊、也省掉最贵的后处理 pass。
        // 辉光感由节点自身的发光精灵纹理提供,不再需要 UnrealBloomPass。
        // 自转仅在中/细档开启(粗档=弱机,静止最省);极缓 autoRotateSpeed 0.34 → 整圈约 3 分钟
        const c = fg.controls(); if (c) { c.autoRotate = isStar && perf.autoRotate; c.autoRotateSpeed = 0.34 }
      } catch (e) { /* noop */ }
      applyPreset(presetRef.current)
      tuneBloom()
    }, 450)
    const t2 = setTimeout(() => { try { fg.zoomToFit(900, 24) } catch (e) {} }, 1900)   // 少留白=相机拉近(治"太遥远")
    return () => { clearTimeout(t); clearTimeout(t2) }
  }, [data, applyPreset, tuneBloom])

  useEffect(() => { if (data && bloomRef.current) applyPreset(preset) }, [presetKey])  // eslint-disable-line

  // ★ 自测/调试用:暴露负载计数(场景对象数/星点精灵数/星尘点数/bloom强度/pixelRatio)。headless 下测 FPS 不准,靠这些数验"档位真的降了负载"。
  useEffect(() => {
    const pub = () => {
      const fg = fgRef.current
      let sceneChildren = 0, dustPoints = 0, pr = 0, bloomStrength = 0
      try { const sc = fg && fg.scene(); if (sc) sceneChildren = sc.children.length } catch (e) {}
      try { for (const p of starRef.current) { const a = p.geometry.getAttribute('position'); if (a) dustPoints += a.count } } catch (e) {}
      try { const r = fg && fg.renderer && fg.renderer(); if (r) pr = r.getPixelRatio() } catch (e) {}
      try { if (bloomRef.current) bloomStrength = bloomRef.current.strength } catch (e) {}
      window.__starPerf = {
        mode, grain, preset: presetKey,
        nodes: data ? data.nodes.length : 0,
        sprites: nodeSpritesRef.current.length,
        sceneChildren, dustPoints, pixelRatio: pr, bloomStrength,
        pulse: grainPerf(grain).pulse, autoRotate: grainPerf(grain).autoRotate,
      }
    }
    const id = setInterval(pub, 700); pub()
    return () => clearInterval(id)
  }, [mode, grain, presetKey, data])
  // 文档模式关辉光(图标清晰),星海模式开;星海时乘以档位系数(粗档=0 关 bloom)
  useEffect(() => {
    const t = setTimeout(() => { if (bloomRef.current) bloomRef.current.strength = isStar ? preset.bloom.s * grainPerf(grainRef.current).bloomMul : 0 }, 500)
    return () => clearTimeout(t)
  }, [mode, data, presetKey])  // eslint-disable-line
  // 切预设时,调节回到"适中"值(带下限,绝不掉到最小把图搞塌);预设本身更强就保留其强度。
  // ★首次加载跳过:保住 localStorage 记住的上次调节,不被预设默认覆盖。
  const presetInit = useRef(true)
  useEffect(() => {
    if (presetInit.current) { presetInit.current = false; return }
    setAdj({
      bloom: Math.max(1.5, preset.bloom.s),
      charge: Math.min(-320, preset.charge),   // 斥力至少 -320(散开适中)
      dist: Math.max(120, preset.dist),        // 连距至少 120
      dims: preset.dims, size: 7,              // 节点默认偏大、清楚(滑杆 0.5–48)
    })
  }, [presetKey])  // eslint-disable-line
  // 记住上次的风格/档位/模式/调节(下次进来直接复用,不用重调)
  useEffect(() => { _lsSet('ex_preset', presetKey) }, [presetKey])
  useEffect(() => { _lsSet('ex_mode', mode) }, [mode])
  useEffect(() => { _lsSet('ex_grain', grain) }, [grain])
  useEffect(() => { _lsSet('ex_adj', adj) }, [adj])
  // 调节值实时作用到图
  useEffect(() => {
    const fg = fgRef.current; if (!fg) return
    try {
      // 散开 / 连距:改力 + 重新加热仿真(否则仿真已冷,节点不动=看着没反应)
      if (fg.d3Force('charge')) fg.d3Force('charge').strength(adj.charge)
      if (fg.d3Force('link')) fg.d3Force('link').distance(adj.dist)
      fg.d3ReheatSimulation && fg.d3ReheatSimulation()
      // ★辉光 / 节点:bloom 已移除、nodeVal 又被自定义精灵忽略 → 这俩滑块以前是死的。
      //   现在直接改每颗发光精灵的亮度(辉光)和尺寸(节点),即时生效(呼吸循环读 base/baseOp,能保持)。
      const op = glowOpOf(adj)
      const sizeMul = sizeMulOf(adj)
      for (const sp of nodeSpritesRef.current) {
        const u = sp && sp.userData && sp.userData.pulse; if (!u) continue
        if (u.base0 == null) u.base0 = u.base
        u.base = u.base0 * sizeMul
        u.baseOp = op
        sp.scale.set(u.base, u.base, 1)
        if (sp.material) sp.material.opacity = op
      }
    } catch (e) { /* noop */ }
  }, [adj])

  const flyTo = useCallback((docId) => {
    const fg = fgRef.current; if (!fg || !data) return
    const node = data.nodes.find((n) => nodeKey(n) === docId); if (!node) return
    const d = 1.25   // 别贴太近(贴近亮核=辉光过曝泛白),留点距离
    fg.cameraPosition({ x: (node.x || 1) * d, y: (node.y || 1) * d, z: (node.z || 120) * d }, node, 1600)
  }, [data])

  async function doSearch(e) {
    e.preventDefault()
    if (!q.trim()) { setHi(null); return }
    try {
      const r = await api.search(q)
      const ids = new Set((r.hits || []).map((h) => h.doc_id)); setHi(ids)
      if (r.hits && r.hits[0]) flyTo(r.hits[0].doc_id)
      else toast('没找到匹配「' + q.trim() + '」的内容', 'err')   // P1-15:无命中给明确反馈,不再只打灰
    } catch { toast('搜索失败,请稍后再试', 'err') }
  }

  const empty = data && data.nodes.length === 0

  return (
    <div className="main" style={{ position: 'absolute', inset: 0 }}>
      <div className="graph-overlay">
        <div className="graph-title glass">
          <h1>探索</h1>
          {data && (<p><span className="dot" style={{ background: 'var(--accent)', boxShadow: '0 0 8px var(--accent)' }} /><span className="num">{data.nodes.length}</span> {chatOnly ? '段聊天' : isStar ? '颗星' : '文档'}{chatOnly ? <><span style={{ color: 'var(--text-3)' }}>·</span><span className="num">{centers.length}</span> 主题</> : <><span style={{ color: 'var(--text-3)' }}>·</span><span className="num">{data.links.length}</span> 连线</>}</p>)}
        </div>
        {!chatOnly && (
        <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
          <div className="seg glass">
            <button className={!isStar ? 'on' : ''} onClick={() => setMode('doc')}>文档</button>
            <button className={isStar ? 'on' : ''} onClick={() => setMode('star')}>星海</button>
          </div>
          {isStar && (<div className="seg glass">{GRAINS.map((g) => (<button key={g.key} className={g.key === grain ? 'on' : ''} onClick={() => setGrain(g.key)}>{g.name}</button>))}</div>)}
          <form className="search-wrap" onSubmit={doSearch} style={{ width: 220 }}><IconSearch /><input className="search" placeholder="搜索飞向星系" value={q} onChange={(e) => setQ(e.target.value)} /></form>
        </div>
        )}
      </div>

      {/* 颜色组面板(可收缩) */}
      {!empty && data && (
        groupsCollapsed ? (
          <button className="groups-handle glass" onClick={toggleGroups} title="展开颜色组" aria-label="展开颜色组">
            <span className="gh-dots">
              {groups.slice(0, 4).map((g) => (<span key={g.key} className="gh-dot" style={{ background: g.color }} />))}
            </span>
            <span className="gh-chev">⟨</span>
          </button>
        ) : (
          <div className="groups-panel glass">
            <div className="gp-head">
              <span>颜色组</span>
              <button className="gp-collapse" onClick={toggleGroups} title="收起" aria-label="收起颜色组">⟩</button>
            </div>
            <div className="seg" style={{ padding: 3, marginBottom: 10 }}>
              <button className={colorBy === 'cluster' ? 'on' : ''} onClick={() => setColorBy('cluster')}>语义簇</button>
              <button className={colorBy === 'ftype' ? 'on' : ''} onClick={() => setColorBy('ftype')}>文件类型</button>
            </div>
            <div className="gp-list">
              {groups.map((g) => (
                <div key={g.key} className={'gp-item' + (hidden.has(g.key) ? ' off' : '') + (chatOnly && topicFocus.cluster === g.key ? ' focus' : '')}
                  onClick={() => chatOnly ? setTopicFocus((f) => ({ cluster: f.cluster === g.key ? null : g.key, seq: f.seq + 1 })) : toggleHidden(g.key)}
                  title={chatOnly ? '点击钻进这个主题' : '点击隐藏/显示'}>
                  <span className="sw" style={{ background: g.color }} />
                  <span className="gp-name">{g.name}</span>
                  <span className="gp-count num">{g.count}</span>
                </div>
              ))}
            </div>
          </div>
        )
      )}

      {/* 外观 / 力度调节 */}
      {!empty && data && isStar && !chatOnly && (
        <div className="adjust-panel glass">
          <div className="ap-head" onClick={() => setShowAdj((s) => !s)}>调节 <span>{showAdj ? '▾' : '▸'}</span></div>
          {showAdj && (
            <div className="ap-body">
              <label>辉光<input type="range" min="0" max="5" step="0.05" value={adj.bloom} onChange={(e) => setAdj((a) => ({ ...a, bloom: +e.target.value }))} /></label>
              <label>节点<input type="range" min="0.5" max="48" step="0.1" value={adj.size} onChange={(e) => setAdj((a) => ({ ...a, size: +e.target.value }))} /></label>
              <label>散开<input type="range" min="40" max="1000" step="10" value={-adj.charge} onChange={(e) => setAdj((a) => ({ ...a, charge: -(+e.target.value) }))} /></label>
              <label>连距<input type="range" min="20" max="400" step="2" value={adj.dist} onChange={(e) => setAdj((a) => ({ ...a, dist: +e.target.value }))} /></label>
              <div className="ap-dims">
                <button className={adj.dims === 3 ? 'on' : ''} onClick={() => setAdj((a) => ({ ...a, dims: 3 }))}>3D</button>
                <button className={adj.dims === 2 ? 'on' : ''} onClick={() => setAdj((a) => ({ ...a, dims: 2 }))}>2D</button>
              </div>
            </div>
          )}
        </div>
      )}

      {!empty && data && isStar && !chatOnly && (<div className="preset-bar glass">{PRESETS.map((p) => (<button key={p.key} className={p.key === presetKey ? 'on' : ''} onClick={() => setPresetKey(p.key)}>{p.name}</button>))}</div>)}
      {!empty && data && chatOnly && (<div className="preset-bar glass" style={{ pointerEvents: 'none', opacity: 0.82 }}><span style={{ padding: '0 8px', fontSize: 12, color: 'var(--text-2)' }}>点主题放大 · 点星看聊天 · 点空白返回全景</span></div>)}

      {!empty && data && (
        <button className={'chatonly-btn glass' + (chatOnly ? ' on' : '')} onClick={() => setChatOnly((v) => !v)} title="只看微信聊天节点">
          <span className="co-dot" />仅聊天
        </button>
      )}

      <div className="graph-host" ref={hostRef}
        onPointerEnter={() => { try { const c = fgRef.current && fgRef.current.controls(); if (c) c.autoRotate = false } catch (e) { } }}
        onPointerLeave={() => { try { const c = fgRef.current && fgRef.current.controls(); if (c) c.autoRotate = true } catch (e) { } }}>
        {!data ? (<div className="loading-wrap"><div className="spinner" /><div>正在生成你的知识星图…</div></div>)
          : empty ? (<Empty icon={<IconExplore />} title="还没有星图" sub="去「入库」灌入文档,语义连线会自动生长成你的知识星图" />)
            : chatOnly ? (
              <TopicGalaxy2D data={data} centers={centers} dim={dim} onOpen={onOpen} focusReq={topicFocus} />
            ) : !isStar ? (
              <DocGraph2D data={data} dim={dim} colorOf={colorOf} onOpen={onOpen}
                hidden={hidden} groupKey={groupKey} hiIds={hi} adj={adj} bg="#080b14" clusterNames={clusterNames} chatOnly={chatOnly} />
            ) : (
              <div className="star-fadein" style={{ width: '100%', height: '100%' }}>
              <ForceGraph3D
                ref={fgRef} width={dim.w} height={dim.h} graphData={data}
                backgroundColor={preset.bg} numDimensions={adj.dims} controlType="orbit" showNavInfo={false}
                autoPauseRedraw={false}
                nodeLabel={(n) => `<div style="padding:7px 11px;font-size:12.5px;font-weight:600;color:#edeff3;background:rgba(12,14,20,0.92);border:1px solid rgba(255,255,255,0.1);border-radius:8px;max-width:260px">${n.label}</div>`}
                nodeThreeObject={starObject}
                nodeThreeObjectExtend={false}
                nodeVal={(n) => (0.8 + Math.sqrt(Math.max(0.5, n.size || 1)) * 1.3) * adj.size}
                nodeVisibility={(n) => !hidden.has(groupKey(n))}
                linkColor={() => preset.link}
                linkWidth={preset.linkW || 0.4}
                linkOpacity={preset.linkVis === 0 ? 0 : 0.5}
                linkVisibility={(l) => { if (preset.linkVis === 0) return false; const s = l.source, t = l.target; const sk = typeof s === 'object' ? groupKey(s) : null; const tk = typeof t === 'object' ? groupKey(t) : null; return !(hidden.has(sk) || hidden.has(tk)) }}
                warmupTicks={70} cooldownTicks={90} cooldownTime={7000}
                d3AlphaDecay={0.026} d3VelocityDecay={0.42}
                onEngineStop={() => {
                  // 只框住主体(排除最远 8% 离群点),相机才不会为了迁就几颗飞点而缩得很远
                  try {
                    const fg = fgRef.current; if (!fg || !data) return
                    const ns = data.nodes.filter((n) => Number.isFinite(n.x))
                    if (ns.length > 30) {
                      let cx = 0, cy = 0, cz = 0
                      ns.forEach((n) => { cx += n.x; cy += n.y; cz += n.z || 0 })
                      cx /= ns.length; cy /= ns.length; cz /= ns.length
                      const dist = (n) => Math.hypot(n.x - cx, n.y - cy, (n.z || 0) - cz)
                      const sorted = ns.map(dist).sort((a, b) => a - b)
                      const cut = sorted[Math.floor(ns.length * 0.92)]
                      fg.zoomToFit(800, 28, (n) => Number.isFinite(n.x) && dist(n) <= cut)
                    } else { fg.zoomToFit(800, 28) }
                  } catch (e) {}
                }}
                onNodeClick={(n) => onOpen(nodeKey(n))} enableNodeDrag={false}
              />
              </div>
            )}
      </div>
    </div>
  )
}
