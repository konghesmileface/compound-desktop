import React, { useState, useEffect, useRef, useCallback } from 'react'
import { api } from './api'
import { IconDownload, IconPlay } from './icons'
import { toast } from './ui'

// 同一标题永远同一色,给每首歌稳定的"专辑封面"身份
function hue(str) {
  let h = 0
  const s = str || 'x'
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0
  return h % 360
}
function fmt(t) {
  if (!t || isNaN(t)) return '0:00'
  const m = Math.floor(t / 60), s = Math.floor(t % 60)
  return m + ':' + (s < 10 ? '0' : '') + s
}

// ===== 歌词面板:随播放进度自动滚动 + 高亮当前行([段落标签]淡化)=====
function Lyrics({ lyrics, ratio }) {
  const boxRef = useRef(null)
  const lines = (lyrics || '').split('\n')
  // 内容行(非[标签]、非空)索引,用于按进度推算"当前行"
  const contentIdx = lines.map((l, i) => ({ l, i })).filter(x => x.l.trim() && !/^\[.+\]$/.test(x.l.trim()))
  const activeContent = Math.min(contentIdx.length - 1, Math.max(0, Math.floor(ratio * contentIdx.length)))
  const activeLine = contentIdx.length ? contentIdx[activeContent].i : -1
  useEffect(() => {
    const box = boxRef.current
    if (!box) return
    const el = box.querySelector('.lyr-line.on')
    if (el) box.scrollTo({ top: el.offsetTop - box.clientHeight / 2 + el.clientHeight / 2, behavior: 'smooth' })
  }, [activeLine])
  if (!lyrics) return <div className="ms-lyr-empty">这首歌暂无歌词</div>
  return (
    <div className="ms-lyr" ref={boxRef}>
      {lines.map((ln, i) => {
        const t = ln.trim()
        if (!t) return <div key={i} className="lyr-gap">&nbsp;</div>
        if (/^\[.+\]$/.test(t)) return <div key={i} className="lyr-tag">{t.replace(/[[\]]/g, '')}</div>
        return <div key={i} className={'lyr-line' + (i === activeLine ? ' on' : (i < activeLine ? ' past' : ''))}>{ln}</div>
      })}
    </div>
  )
}

// ===== 炫酷播放器:动态专辑(音频可视化)+ 自定义控制 + 歌词 =====
function SongStage({ song }) {
  const audioRef = useRef(null)
  const canvasRef = useRef(null)
  const acRef = useRef(null), anRef = useRef(null), dataRef = useRef(null), rafRef = useRef(0)
  const [playing, setPlaying] = useState(false)
  const [cur, setCur] = useState(0)
  const [dur, setDur] = useState(0)
  const h = hue(song.title)
  const c1 = `hsl(${h} 78% 62%)`, c2 = `hsl(${(h + 48) % 360} 80% 56%)`

  // 换歌:重置
  useEffect(() => { setCur(0); setDur(0); setPlaying(false) }, [song.url])

  const setupAudio = useCallback(() => {
    if (acRef.current) return
    try {
      const AC = window.AudioContext || window.webkitAudioContext
      const ac = new AC()
      const src = ac.createMediaElementSource(audioRef.current)
      const an = ac.createAnalyser(); an.fftSize = 256; an.smoothingTimeConstant = 0.82
      src.connect(an); an.connect(ac.destination)
      acRef.current = ac; anRef.current = an; dataRef.current = new Uint8Array(an.frequencyBinCount)
    } catch (e) { /* 跨域/不支持 → 退回纯 CSS 动效 */ }
  }, [])

  // 环形频谱可视化(围绕专辑);无音频分析时画柔和呼吸圆
  useEffect(() => {
    const cv = canvasRef.current; if (!cv) return
    const ctx = cv.getContext('2d')
    const DPR = Math.min(2, window.devicePixelRatio || 1)
    const size = 320; cv.width = size * DPR; cv.height = size * DPR; ctx.scale(DPR, DPR)
    const cx = size / 2, cy = size / 2, R = 118
    let t = 0
    const loop = () => {
      rafRef.current = requestAnimationFrame(loop)
      t += 0.02
      ctx.clearRect(0, 0, size, size)
      let data = null
      if (anRef.current && playing) { anRef.current.getByteFrequencyData(dataRef.current); data = dataRef.current }
      const N = 72
      for (let i = 0; i < N; i++) {
        const ang = (i / N) * Math.PI * 2 - Math.PI / 2
        let amp
        if (data) { amp = (data[i % data.length] / 255) * 46 }
        else { amp = playing ? (Math.sin(t * 2 + i * 0.5) * 0.5 + 0.5) * 22 + 6 : (Math.sin(t + i * 0.5) * 0.5 + 0.5) * 8 + 2 }
        const r1 = R + 6, r2 = R + 6 + amp
        const x1 = cx + Math.cos(ang) * r1, y1 = cy + Math.sin(ang) * r1
        const x2 = cx + Math.cos(ang) * r2, y2 = cy + Math.sin(ang) * r2
        const g = ctx.createLinearGradient(x1, y1, x2, y2)
        g.addColorStop(0, `hsla(${(h + i * 2) % 360} 80% 62% / .25)`)
        g.addColorStop(1, `hsla(${(h + i * 2) % 360} 85% 66% / .9)`)
        ctx.strokeStyle = g; ctx.lineWidth = 3; ctx.lineCap = 'round'
        ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke()
      }
    }
    loop()
    return () => cancelAnimationFrame(rafRef.current)
  }, [playing, h])

  const toggle = () => {
    const a = audioRef.current; if (!a) return
    if (a.paused) { setupAudio(); if (acRef.current && acRef.current.state === 'suspended') acRef.current.resume(); a.play().catch(() => {}) }
    else a.pause()
  }
  const seek = (e) => { const a = audioRef.current; if (a && dur) a.currentTime = (e.target.value / 100) * dur }
  const ratio = dur ? cur / dur : 0

  return (
    <div className="ms-stage" style={{ '--c1': c1, '--c2': c2 }}>
      <div className="ms-aura" aria-hidden />
      <div className="ms-left">
        <div className={'ms-disc-wrap' + (playing ? ' spinning' : '')}>
          <canvas ref={canvasRef} className="ms-viz" style={{ width: 320, height: 320 }} />
          <div className="ms-disc">
            <div className="ms-disc-grooves" />
            <div className="ms-disc-shine" />
            <div className="ms-disc-core"><span>♪</span></div>
          </div>
        </div>
      </div>

      <div className="ms-right">
        <div className="ms-kick">你的专属主题曲 · AI 为你谱写</div>
        <h1 className="ms-title">《{song.title}》</h1>
        <div className="ms-meta">{[song.genre, song.date].filter(Boolean).join(' · ')}</div>

        <Lyrics lyrics={song.lyrics} ratio={ratio} />

        <div className="ms-controls">
          <button className="ms-play" onClick={toggle} aria-label={playing ? '暂停' : '播放'}>
            {playing
              ? <svg viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="5" width="4" height="14" rx="1" /><rect x="14" y="5" width="4" height="14" rx="1" /></svg>
              : <svg viewBox="0 0 24 24" fill="currentColor"><path d="M7 4.8v14.4c0 .9 1 1.5 1.8 1L21 13c.8-.5.8-1.6 0-2.1L8.8 3.8C8 3.3 7 3.9 7 4.8z" /></svg>}
          </button>
          <span className="ms-t">{fmt(cur)}</span>
          <input className="ms-seek" type="range" min="0" max="100" value={ratio * 100 || 0} onChange={seek} style={{ '--p': (ratio * 100 || 0) + '%' }} />
          <span className="ms-t">{fmt(dur)}</span>
          <a className="ms-dl" href={song.url} download={(song.title || '专属主题曲') + '.mp3'} title="下载 MP3"><IconDownload /></a>
        </div>
        <audio ref={audioRef} src={song.url} preload="metadata"
          onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)}
          onTimeUpdate={(e) => setCur(e.target.currentTime)}
          onLoadedMetadata={(e) => setDur(e.target.duration)} />
      </div>
    </div>
  )
}

// 台灯 + 伏案小人 铅笔线稿(自己画出自己),呼应"夜里,AI 把你写成一首歌"
function LampSketch({ loop }) {
  return (
    <div className="le-canvas" aria-hidden>
      <svg viewBox="0 0 240 150" className={'le-sketch' + (loop ? ' loop' : '')}>
        <path className="le-glow" d="M78 62 L128 132 L34 132 Z" />
        <path className="le-p p1" pathLength="1" d="M40 132 h34" />
        <path className="le-p p2" pathLength="1" d="M57 132 C57 104 60 92 76 80" />
        <path className="le-p p3" pathLength="1" d="M68 74 a12 12 0 0 1 22 10" />
        <path className="le-p p4" pathLength="1" d="M104 118 h100" />
        <circle className="le-p p5" pathLength="1" cx="168" cy="88" r="10" fill="none" />
        <path className="le-p p6" pathLength="1" d="M164 98 C158 106 150 112 138 117 M170 98 C172 106 172 112 171 117" />
        <path className="le-p p7" pathLength="1" d="M150 112 L128 117" />
        <circle className="le-pen" cx="128" cy="117" r="2" />
      </svg>
    </div>
  )
}

// ===== 空态:引导导入(以前的好版式,文案改为"只出歌曲") =====
function EmptyLife({ onGoto, noKey, noData, noPersona, eligible }) {
  return (
    <div className="view life-empty">
      <div className="le-stars" aria-hidden>
        {Array.from({ length: 26 }, (_, i) => <i key={i} style={{ left: (i * 37 % 100) + '%', top: (i * 53 % 100) + '%', animationDelay: (i % 7) * 0.7 + 's' }} />)}
      </div>
      <div className="le-kicker">你的一生 · 一首 AI 专属主题曲</div>
      <h1 className="le-title">配齐这些,自动为你谱第一首歌</h1>
      <p className="le-sub">用你自己配置的 AI 通读你导入的聊天、笔记与文档,读懂你这个人 —— <b>配齐下面三步、导入完就自动为你谱第一首</b>专属主题曲,之后每月月底再自动更新一首。连歌词都是你的故事,数据越多越懂你。</p>
      <LampSketch />
      <div className="le-steps">
        <div className={'le-step' + (noKey ? ' le-todo' : ' le-ok')}><span className="le-n">1</span><b>配置你的 AI</b><span>{noKey ? '设置里填模型 + Key' : '已配置 ✓'}</span></div>
        <div className={'le-step' + (noData ? ' le-todo' : ' le-ok')}><span className="le-n">2</span><b>导入你的数据</b><span>{noData ? '聊天 / 文档 / 邮件,越多越懂你' : '已导入 ✓'}</span></div>
        <div className={'le-step' + (noPersona ? ' le-todo' : ' le-ok')}><span className="le-n">3</span><b>生成人格画像</b><span>{noPersona ? 'AI 读懂你是谁、在意什么' : '已生成 ✓'}</span></div>
      </div>
      <div className="le-actions">
        {noKey && <button className="btn btn-primary" onClick={() => onGoto && onGoto('settings')}>去配置 AI</button>}
        {noData && <button className={noKey ? 'btn' : 'btn btn-primary'} onClick={() => onGoto && onGoto('ingest')}>去导入数据</button>}
        {!noKey && !noData && noPersona && <button className="btn btn-primary" onClick={() => onGoto && onGoto('persona')}>去生成画像</button>}
        {eligible && <div className="le-auto-hint">已就绪 · 正在为你谱第一首歌…</div>}
      </div>
    </div>
  )
}

// ===== 生成中 =====
function GeneratingLife() {
  return (
    <div className="view life-empty">
      <div className="le-kicker">你的一生 · 一首 AI 专属主题曲</div>
      <h1 className="le-title">AI 正在为你谱曲</h1>
      <p className="le-sub">通读你的全部记录 → 读懂你这个人 → 谱一首只属于你的主题曲,连歌词都是你的故事。好了会自动出现在这里。</p>
      <LampSketch loop />
      <div className="le-sub" style={{ opacity: 0.7 }}><span className="spinner sm" /> 谱曲中,通常几分钟…</div>
    </div>
  )
}

export default function Life({ onGoto }) {
  const [lib, setLib] = useState(null)
  const [gen, setGen] = useState(null)   // lifestory 生成状态(驱动出曲)
  const [err, setErr] = useState(false)
  const [sel, setSel] = useState(0)
  const [making, setMaking] = useState(false)
  const [elig, setElig] = useState({ key: null, docs: null, persona: null })   // 资格:配了AI key? 有数据? 有人格画像?
  const pollN = useRef(0), timerRef = useRef(null), makeTimer = useRef(null), firstRef = useRef(false)

  const loadLib = useCallback(() => api.mylibrary().then(setLib).catch(() => setLib({ songs: [] })), [])

  useEffect(() => {
    api.getSettings().then((s) => setElig((e) => ({ ...e, key: !!s.has_key }))).catch(() => setElig((e) => ({ ...e, key: false })))
    api.stats().then((s) => setElig((e) => ({ ...e, docs: (s.documents || 0) }))).catch(() => setElig((e) => ({ ...e, docs: 0 })))
    api.persona().then((p) => setElig((e) => ({ ...e, persona: !!(p && (p.one_liner || (p.tags && p.tags.length) || (p.domains && p.domains.length))) }))).catch(() => setElig((e) => ({ ...e, persona: false })))
    try { localStorage.setItem('life_seen', String(Date.now())) } catch (e) { }   // 打开冥想=已读,清 tab 小圆点
    window.dispatchEvent(new CustomEvent('life-seen'))
  }, [])
  const noKey = elig.key === false
  const noData = elig.docs === 0
  const noPersona = elig.persona === false
  const eligible = elig.key && (elig.docs || 0) > 0 && elig.persona

  useEffect(() => () => clearTimeout(makeTimer.current), [])
  const pollMake = useCallback(function pm() {
    api.songStatus().then((s) => {
      if (!s || s.status === 'done') { setMaking(false); try { localStorage.setItem('life_first_done', '1') } catch (e) { } loadLib(); if (s && s.title) toast('你的第一首歌谱好了:《' + s.title + '》', 'ok') }
      else if (s.status === 'error') { setMaking(false); toast('谱曲失败:' + (s.note || '稍后再试'), 'err') }
      else { makeTimer.current = setTimeout(pm, 5000) }
    }).catch(() => { makeTimer.current = setTimeout(pm, 6000) })
  }, [loadLib])
  // auto=首次自动触发(不弹提示、失败不跳转);手动=带引导
  const makeSong = useCallback((auto) => {
    if (noKey) { if (!auto) { toast('先在「设置」配置你的 AI 模型和 Key', 'err'); onGoto && onGoto('settings') } return }
    if (noData) { if (!auto) { toast('先导入你的数据(聊天 / 笔记 / 文档)', 'err'); onGoto && onGoto('ingest') } return }
    setMaking(true); if (!auto) toast('开始为你谱一首,约几分钟…', 'ok')
    api.lifesong(true).then(() => api.songMake()).then(() => pollMake())   // 先出词稿(需人格画像)→ 成曲
      .catch((e) => {
        const m = String(e && e.message)
        if (m.includes('409') || m.includes('composing')) { setMaking(true); pollMake(); return }
        setMaking(false)
        if (m === '402') return   // 会员墙全局接管
        if (!auto) { toast('还差一步:先去生成人格画像,AI 才懂你、才能为你写歌', 'err'); onGoto && onGoto('persona') }
      })
  }, [pollMake, noKey, noData, onGoto])

  // ★首次:符合条件(会员+key+数据+画像)且还没有歌 → 自动为TA谱第一首(不用等月底、不用点按钮)
  useEffect(() => {
    if (firstRef.current || !lib) return
    if (((lib.songs) || []).length) return
    if (!eligible) return
    try { if (localStorage.getItem('life_first_done') === '1') return } catch (e) { }
    firstRef.current = true
    makeSong(true)
  }, [lib, eligible, makeSong])

  useEffect(() => {
    loadLib()
    let stop = false; pollN.current = 0; clearTimeout(timerRef.current)
    const poll = (refresh) => api.lifestory(refresh, 'pencil').then((r) => {
      if (stop) return
      setGen(r)
      if (r.theme_song) loadLib()   // 有新曲了 → 刷新曲库
      if (!r.empty && r.generating && pollN.current < 90) { pollN.current++; timerRef.current = setTimeout(() => poll(false), 5000) }
    }).catch(() => { })
    poll(false)
    return () => { stop = true; clearTimeout(timerRef.current) }
  }, [loadLib])

  if (err) return <EmptyLife onGoto={onGoto} />

  const songs = (lib && lib.songs) || []

  if (!songs.length) {
    // 还没有歌:生成中 or 空态引导
    if (making || (gen && gen.generating)) return <GeneratingLife />
    if (!lib) return <div className="view"><div className="loading-wrap"><div className="spinner" /><div>正在打开你的冥想…</div></div></div>
    return <EmptyLife onGoto={onGoto} noKey={noKey} noData={noData} noPersona={noPersona} eligible={eligible} />
  }

  const featured = songs[Math.min(sel, songs.length - 1)]

  return (
    <div className="view ms-page">
      <div className="ms-page-head">
        <div className="ms-page-kick">冥想 · 你的人生专辑</div>
        <p className="ms-page-sub"><b>每到月底,AI 自动为你谱一首最懂你的歌</b> —— 用你自己配置的 AI 读遍你导入的聊天、笔记与文档,连歌词都是你的故事。<b>数据越多,它越懂你,歌也越像你。</b></p>
        {(noKey || noData || noPersona) && (
          <div className="ms-note">
            <span className="ms-note-t">配齐这些,导入完就自动为你谱第一首:</span>
            {noKey && <button className="ms-note-btn" onClick={() => onGoto && onGoto('settings')}>配置你的 AI</button>}
            {noData && <button className="ms-note-btn" onClick={() => onGoto && onGoto('ingest')}>导入你的数据</button>}
            {noPersona && <button className="ms-note-btn" onClick={() => onGoto && onGoto('persona')}>生成人格画像</button>}
          </div>
        )}
      </div>

      <SongStage key={featured.url} song={featured} />

      {songs.length > 1 && (
        <section className="ms-shelf-wrap">
          <div className="ms-shelf-head"><span className="ms-shelf-dot" /><h2>我的专辑</h2><span className="ms-shelf-n">{songs.length} 首</span></div>
          <div className="vinyl-shelf">
            {songs.map((s, i) => {
              const sh = hue(s.title)
              const active = i === Math.min(sel, songs.length - 1)
              return (
                <div key={s.url} className={'vinyl-card' + (active ? ' spinning' : '')} onClick={() => setSel(i)}>
                  <div className="vinyl-slab">
                    <div className="vinyl-disc" style={{ '--lc1': `hsl(${sh} 70% 58%)`, '--lc2': `hsl(${(sh + 42) % 360} 74% 52%)` }}>
                      <div className="vinyl-grooves" /><div className="vinyl-shine" />
                      <div className="vinyl-label">
                        <div className="vl-title">{s.title}</div>
                        <div className="vl-genre">{s.genre || '主题曲'}</div>
                        <div className="vl-hole" />
                        <div className="vl-date">{s.date}</div>
                      </div>
                    </div>
                    <div className="vinyl-play"><IconPlay /></div>
                  </div>
                  <div className="vinyl-meta">
                    <div className="vm-title">{s.title}</div>
                    <div className="vm-sub">{[s.genre, s.date].filter(Boolean).join(' · ')}</div>
                  </div>
                </div>
              )
            })}
          </div>
        </section>
      )}
    </div>
  )
}
