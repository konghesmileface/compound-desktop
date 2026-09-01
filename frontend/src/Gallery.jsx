import React, { useState, useEffect, useRef } from 'react'
import { api, apiUrl, openExternal } from './api'
import { IconPlay, IconDownload, IconGallery } from './icons'
import { Empty } from './ui'

// 确定性配色:同一标题永远同一色,让作品有稳定的"专辑封面"身份感
function hue(str) {
  let h = 0
  const s = str || 'x'
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0
  return h % 360
}

// ---- 黑胶唱片(一首歌一张) ----
function Vinyl({ song, playing, onPlay }) {
  const h = hue(song.title)
  const c1 = `hsl(${h} 70% 58%)`
  const c2 = `hsl(${(h + 42) % 360} 74% 52%)`
  return (
    <div className={'vinyl-card' + (playing ? ' spinning' : '')} onClick={onPlay}>
      <div className="vinyl-slab">
        <div className="vinyl-disc" style={{ '--lc1': c1, '--lc2': c2 }}>
          <div className="vinyl-grooves" />
          <div className="vinyl-shine" />
          <div className="vinyl-label">
            <div className="vl-title">{song.title}</div>
            <div className="vl-genre">{song.genre || '主题曲'}</div>
            <div className="vl-hole" />
            <div className="vl-date">{song.date}</div>
          </div>
        </div>
        <div className="vinyl-play"><IconPlay /></div>
      </div>
      <div className="vinyl-meta">
        <div className="vm-title">{song.title}</div>
        <div className="vm-sub">{song.genre}{song.date ? ' · ' + song.date : ''}</div>
      </div>
    </div>
  )
}

// ---- 电影海报(一部动画一张) ----
function Poster({ film, onPlay }) {
  const h = hue(film.title + film.mode)
  const g1 = `hsl(${h} 46% 22%)`
  const g2 = `hsl(${(h + 38) % 360} 52% 12%)`
  const accent = `hsl(${(h + 20) % 360} 72% 62%)`
  return (
    <div className="poster-card" onClick={onPlay}>
      <div className="poster-art" style={{ '--pg1': g1, '--pg2': g2, '--pacc': accent }}>
        <div className="poster-grain" />
        <div className="poster-sprock poster-sprock-l" />
        <div className="poster-sprock poster-sprock-r" />
        <div className="poster-mode">{film.mode_label || (film.mode === 'pencil' ? '铅笔手绘' : '微电影')}</div>
        <div className="poster-center">
          <div className="poster-kick">你的一生 · 一部动画</div>
          <div className="poster-title">{film.title}</div>
        </div>
        <div className="poster-bottom">
          <span className="poster-date">{film.date}</span>
          <span className="poster-brand">第二大脑</span>
        </div>
        <div className="poster-play"><IconPlay /></div>
        <div className="poster-glow" />
      </div>
    </div>
  )
}

// ---- 居中弹出播放器 ----
function Player({ item, onClose }) {
  const ref = useRef(null)
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    try { const _p = ref.current && ref.current.play && ref.current.play(); if (_p && _p.catch) _p.catch(() => {}) } catch (e) {}   // 08-DEF-06:吞掉 autoPlay 被打断的 Promise rejection
    return () => window.removeEventListener('keydown', onKey)
  }, [])
  const isSong = item.kind === 'song'
  const h = hue((item.title || '') + (item.mode || ''))
  return (
    <div className="gp-overlay" onClick={onClose}>
      <div className={'gp-modal ' + (isSong ? 'gp-song' : 'gp-film')} onClick={(e) => e.stopPropagation()}>
        <button className="gp-close" onClick={onClose} aria-label="关闭">✕</button>
        {isSong ? (
          <div className="gp-song-body">
            <div className="gp-vinyl-wrap">
              <div className="gp-vinyl spinning" style={{ '--lc1': `hsl(${h} 70% 58%)`, '--lc2': `hsl(${(h + 42) % 360} 74% 52%)` }}>
                <div className="vinyl-grooves" />
                <div className="vinyl-shine" />
                <div className="vinyl-label">
                  <div className="vl-title">{item.title}</div>
                  <div className="vl-hole" />
                </div>
              </div>
            </div>
            <div className="gp-song-info">
              <div className="gp-kick">你的专属主题曲</div>
              <h2>{item.title}</h2>
              {item.genre && <div className="gp-genre">{item.genre}</div>}
              {item.style && <div className="gp-style">{item.style}</div>}
              <div className="gp-date">{item.date}</div>
              <audio ref={ref} src={apiUrl(item.url)} controls autoPlay className="gp-audio" />
              {item.lyrics && (
                <div className="gp-lyrics">
                  {String(item.lyrics).split('\n').map((ln, i) => {
                    const tag = /^\[.+\]$/.test(ln.trim())
                    return <div key={i} className={tag ? 'lyr-tag' : 'lyr-line'}>{ln || '\u00A0'}</div>
                  })}
                </div>
              )}
              <button type="button" className="gp-dl" onClick={() => openExternal(item.url)}><span className="btn-ico"><IconDownload /></span>下载 MP3</button>
            </div>
          </div>
        ) : (
          <div className="gp-film-body">
            <video ref={ref} src={apiUrl(item.url)} controls autoPlay playsInline className="gp-video" />
            <div className="gp-film-cap">
              <span className="gp-film-title">{item.title}</span>
              <span className="gp-film-sub">{item.mode_label} · {item.date}</span>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default function Gallery({ embedded }) {
  const [d, setD] = useState(null)
  const [err, setErr] = useState(false)
  const [open, setOpen] = useState(null)   // {kind:'song'|'film', ...}

  useEffect(() => {
    api.mylibrary().then(setD).catch(() => setErr(true))
  }, [])

  if (err) {
    if (embedded) return null
    return (
      <div className="view"><Empty icon={<IconGallery />} title="还没有你的作品" sub="去「一生」生成你的动画与主题曲,它们会收藏到这里" /></div>
    )
  }
  if (!d) {
    if (embedded) return null
    return <div className="view"><div className="loading-wrap"><div className="spinner" /><div>正在打开你的作品集…</div></div></div>
  }

  const songs = d.songs || []
  const films = d.films || []
  const emptyAll = songs.length === 0 && films.length === 0
  if (embedded && emptyAll) return null

  return (
    <div className={embedded ? 'gallery-embed' : 'view gallery-view'}>
      {embedded
        ? <div className="gallery-embed-head"><h2>你的作品集</h2><p>每个月新的一首主题曲、一部动画,都会收藏在这里</p></div>
        : <div className="view-head">
            <h1>作品集</h1>
            <p>第二大脑每个月为你谱写一首主题曲、拍一部动画短片。它们在这里累积成你的专辑与故事集。</p>
          </div>}

      {!embedded && emptyAll && (
        <Empty icon={<IconGallery />} title="作品集还是空的" sub="去「一生」播放并生成你的动画短片与专属主题曲,之后会自动收藏到这里" />
      )}

      {songs.length > 0 && (
        <section className="gallery-sec">
          <div className="gsec-head"><span className="gsec-dot dot-song" /><h2>我的专辑</h2>
            <span className="gsec-count">{songs.length} 首</span></div>
          <div className="vinyl-shelf">
            {songs.map((s, i) => (
              <Vinyl key={s.url} song={s} playing={open && open.kind === 'song' && open.url === s.url}
                onPlay={() => setOpen({ kind: 'song', ...s })} />
            ))}
          </div>
        </section>
      )}

      {films.length > 0 && (
        <section className="gallery-sec">
          <div className="gsec-head"><span className="gsec-dot dot-film" /><h2>我的故事集</h2>
            <span className="gsec-count">{films.length} 部</span></div>
          <div className="poster-wall">
            {films.map((f) => (
              <Poster key={f.url} film={f} onPlay={() => setOpen({ kind: 'film', ...f })} />
            ))}
          </div>
        </section>
      )}

      {open && <Player item={open} onClose={() => setOpen(null)} />}
    </div>
  )
}
