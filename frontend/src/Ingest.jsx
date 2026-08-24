import React, { useRef, useState, useEffect, useCallback } from 'react'
import { api } from './api'
import { IconIngest } from './icons'
import Guide, { SOURCES } from './Guide'
import WechatSync from './WechatSync'
import { toast } from './ui'

const EXTS = ['.pdf', '.epub', '.mobi', '.azw3', '.azw', '.fb2', '.xps', '.cbz',
  '.docx', '.pptx', '.xlsx', '.xlsm', '.md', '.markdown', '.txt',
  '.html', '.htm', '.csv', '.json', '.eml', '.mbox',
  '.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tiff', '.tif', '.gif', '.heic',
  '.mp3', '.wav', '.m4a', '.flac', '.aac', '.ogg', '.wma', '.amr',
  '.mp4', '.mov', '.mkv', '.avi', '.webm', '.flv', '.ts']
const PHASE = { uploading: '上传中', queued: '排队中', ingesting: '识别中', embedding: '语义嵌入', done: '完成', error: '出错' }
const JOB_KEY = 'ingestJob'

export default function Ingest({ onDone }) {
  const fileRef = useRef()
  const oneRef = useRef()
  const [guideKey, setGuideKey] = useState(null)
  const [busy, setBusy] = useState(false)
  const [job, setJob] = useState(null)
  const [autoSync, setAutoSync] = useState(() => localStorage.getItem('autoSync') === '1')

  const poll = useCallback((id, { resumed = false } = {}) => {
    setBusy(true)
    let fails = 0
    const t = setInterval(async () => {
      let j
      try {
        j = await api.job(id)
      } catch (e) {
        // 404 = 任务在后端已不存在(服务重启过 / 已过期)→ 立即放弃,不再重试
        if (String(e.message) === '404') {
          clearInterval(t); setBusy(false); localStorage.removeItem(JOB_KEY)
          if (resumed) { setJob(null); toast('上次的入库任务已结束或已过期', 'info') }
          else setJob({ phase: 'error', error: '任务已失效(服务可能重启过),请重新上传' })
          return
        }
        // 其它错误(网络抖动 / 5xx)→ 容忍几次再放弃,别让一次抖动丢掉进行中的任务
        if (++fails >= 6) {
          clearInterval(t); setBusy(false)
          setJob((p) => ({ ...(p || {}), phase: 'error', error: '网络不稳,已暂停刷新进度,请稍后重试' }))
        }
        return
      }
      fails = 0
      setJob(j)
      onDone && onDone()
      if (j.phase === 'done' || j.phase === 'error') {
        clearInterval(t); setBusy(false); localStorage.removeItem(JOB_KEY)
      }
    }, 800)
    return t
  }, [onDone])

  // 刷新后恢复进行中的任务(#1:刷新不丢进度;旧任务 404 则温和放弃并提示)
  useEffect(() => {
    const id = localStorage.getItem(JOB_KEY)
    if (id) { const t = poll(id, { resumed: true }); return () => clearInterval(t) }
  }, [poll])

  const [url, setUrl] = useState('')
  async function grabUrl() {
    const u = url.trim()
    if (!/^https?:\/\//.test(u)) { toast('请粘贴一个 http(s) 链接', 'err'); return }
    setBusy(true); setJob({ phase: 'ingesting', files_total: 1, file_index: 1, current_file: '抓取网页/视频…' })
    try {
      const { job_id } = await api.uploadUrl(u)
      localStorage.setItem(JOB_KEY, job_id)
      setUrl(''); poll(job_id)
    } catch { setBusy(false); setJob({ phase: 'error', error: '抓取失败,请检查链接' }) }
  }
  async function pick(e) {
    const all = Array.from(e.target.files || [])
    const docs = all.filter((f) => EXTS.some((x) => f.name.toLowerCase().endsWith(x)))
    if (!docs.length) { toast('没有可入库的文件(PDF/Word/录音/视频/…)', 'err'); return }
    setBusy(true)
    setJob({ phase: 'uploading', files_total: docs.length, file_index: 0 })
    try {
      const { job_id } = await api.upload(docs, 'auto')
      localStorage.setItem(JOB_KEY, job_id)
      poll(job_id)
    } catch { setBusy(false); setJob({ phase: 'error', error: '上传失败,请重试' }) }
  }

  const toggleAuto = () => setAutoSync((v) => { const n = !v; localStorage.setItem('autoSync', n ? '1' : '0'); return n })

  const filePct = job && job.files_total ? Math.round(((job.file_index || 0) / job.files_total) * 100) : 0
  const pagePct = job && job.page_total ? Math.round((job.page / job.page_total) * 100) : 0
  const done = job && job.phase === 'done'

  return (
    <div className="view">
      <div className="view-head">
        <h1>入库</h1>
        <p>选文件夹(含子文件夹)或文件 → 逐个识别 → 语义嵌入。支持 PDF/EPUB/MOBI/AZW3/Word/PPT/Excel/网页/邮件等。</p>
      </div>

      {/* 微信同步(主角):实时徽章 + 开关 + 进度条 */}
      <WechatSync onGuide={(k) => setGuideKey(k)} />

      {/* 隐私文案(#3)*/}
      <div className="privacy-note glass">
        <span className="pn-dot" />
        <span>你的文档<b>只存在本地</b>,<b>不会上传到任何服务器</b>。识别与向量化都在你自己的设备/局域网内完成。</span>
      </div>

      <div className="dropzone glass">
        <div className="zicon"><IconIngest /></div>
        <div className="big">{busy ? '入库进行中…' : '选择要入库的内容'}</div>
        <div className="sub">PDF · Word · PPT · Excel · 电子书 · 网页 · 截图 · 录音 · 视频</div>
        <div style={{ display: 'flex', gap: 10, justifyContent: 'center', marginTop: 18 }}>
          <button className="btn btn-primary" disabled={busy} onClick={() => fileRef.current.click()}>选择文件夹</button>
          <button className="btn" disabled={busy} onClick={() => oneRef.current.click()}>选择文件</button>
        </div>
        <div style={{ display: 'flex', gap: 8, justifyContent: 'center', marginTop: 14, width: '100%', maxWidth: 560, marginLeft: 'auto', marginRight: 'auto' }} onClick={(e) => e.stopPropagation()}>
          <input className="auth-in" style={{ marginBottom: 0, flex: 1 }} placeholder="或粘贴一个网址(B站/网页/播客链接), 视频语音自动转文字入库" value={url} onChange={(e) => setUrl(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') grabUrl() }} />
          <button className="btn" disabled={busy} onClick={grabUrl}>抓取入库</button>
        </div>
        {/* 自动同步勾选(#2)*/}
        <label className="autosync" onClick={(e) => e.stopPropagation()}>
          <input type="checkbox" checked={autoSync} onChange={toggleAuto} />
          <span>实时同步此文件夹(勾选后,文件夹里新增的文件会自动入库)</span>
        </label>
        <input ref={fileRef} type="file" webkitdirectory="" directory="" multiple style={{ display: 'none' }} onChange={pick} />
        <input ref={oneRef} type="file" multiple style={{ display: 'none' }} onChange={pick} />
      </div>

      {job && (
        <div className="progress-card glass">
          <div className="progress-row">
            <span className="file">{done ? '全部完成' : (job.current_file || '准备中…')}</span>
            <span className="phase">{PHASE[job.phase] || job.phase}</span>
          </div>
          <div className="bar"><i style={{ width: `${done ? 100 : filePct}%` }} /></div>
          {job.page_total > 0 && job.phase === 'ingesting' && (
            <div className="sub-bar bar"><i style={{ width: `${pagePct}%` }} /></div>
          )}
          <div className="progress-meta">
            <span>文件 <span className="num">{job.file_index || 0}/{job.files_total || 0}</span></span>
            {job.page_total > 0 && <span>本文件 第 <span className="num">{job.page}/{job.page_total}</span> 页</span>}
            {job.embedded_pages > 0 && <span>已嵌入 <span className="num">{job.embedded_pages}</span> 页</span>}
            {job.error && <span style={{ color: 'var(--bad)' }}>{job.error}</span>}
          </div>
        </div>
      )}

      <div className="src-head t-label" style={{ marginTop: 34, marginBottom: 4 }}>怎么把数据导进来 · 每种都有一步步图文说明</div>
      <p style={{ fontSize: 12.5, color: 'var(--text-3)', margin: '0 0 14px', lineHeight: 1.6 }}>点任意一张卡看详细步骤 —— 微信实时同步、iPhone 导入历史、邮件全量导入、网页文章,小白照着点就能搞定;搞不定我们远程帮你接。</p>
      <div className="src-grid">
        {Object.entries(SOURCES).filter(([, s]) => s.tile !== false).map(([k, s]) => (
          <div key={k} className="src-card glass" onClick={() => setGuideKey(k)}>
            <div className="src-dot" style={{ background: s.color }} />
            <div className="src-info">
              <div className="src-name">{s.name}</div>
              <div className="src-sub">{s.intro}</div>
            </div>
            <div className="src-go">查看步骤 →</div>
          </div>
        ))}
      </div>

      {guideKey && <Guide sourceKey={guideKey} onClose={() => setGuideKey(null)} />}
    </div>
  )
}
