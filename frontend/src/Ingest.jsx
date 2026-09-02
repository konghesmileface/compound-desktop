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
  const [syncFolders, setSyncFolders] = useState([])
  const isTauri = typeof window !== 'undefined' && window.__TAURI__ && window.__TAURI__.core

  const poll = useCallback((id, { resumed = false } = {}) => {
    setBusy(true)
    let fails = 0
    const t = setInterval(async () => {
      let j
      try {
        j = await api.job(id)
      } catch (e) {
        // 404 = 任务在后端已不存在(服务重启过 / 已过期)。★别吓用户"重新上传":重启丢的是进度显示,
        //   文件多半已入库,先引导去文库看。
        if (String(e.message) === '404') {
          clearInterval(t); setBusy(false); localStorage.removeItem(JOB_KEY)
          if (resumed) { setJob(null); toast('上次的入库任务已结束', 'info') }
          else setJob({ phase: 'error', error: '进度显示中断了(后端刷新过)。你的文件多半已入库——去「文库」看看有没有;没有再重传即可,不用担心。' })
          return
        }
        // ★网络抖动 / sidecar 忙(大文件 ASR 时后端很忙、/job 响应慢很正常)→ 一直耐心重试,
        //   绝不因几秒抖动就报"出错"让用户误以为要重传/放弃。只挂个软提示。
        fails++
        setJob((p) => ({ ...(p || {}), phase: (p && p.phase) || 'ingesting', _stalled: fails }))
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

  // 定期同步文件夹:列表 + Tauri 原生目录选择器 + 增删
  const loadSync = useCallback(async () => {
    try { const r = await api.autosyncList(); setSyncFolders(r.folders || []) } catch { /* 后端未就绪,忽略 */ }
  }, [])
  // 挂载即拉一次 + 每 8s 轮询(后台首扫/巡检在入库,已同步数会持续涨,轮询让 UI 实时反映)
  useEffect(() => { loadSync(); const t = setInterval(loadSync, 8000); return () => clearInterval(t) }, [loadSync])
  async function addSyncFolder() {
    if (!isTauri) { toast('此功能需在桌面客户端里使用(浏览器拿不到文件夹真实路径)', 'err'); return }
    let path
    try { path = await window.__TAURI__.core.invoke('pick_folder') } catch { toast('打开文件夹选择器失败', 'err'); return }
    if (!path) return   // 用户取消
    try {
      await api.autosyncAdd(path)
      toast('已加入定期同步,正在后台导入现有文件,之后新增文件会自动入库', 'ok')
      loadSync(); onDone && onDone()
    } catch (e) { toast('添加失败:' + (e.message || ''), 'err') }
  }
  async function removeSyncFolder(path) {
    try { await api.autosyncRemove(path); loadSync() } catch { /* noop */ }
  }

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
        <input ref={fileRef} type="file" webkitdirectory="" directory="" multiple style={{ display: 'none' }} onChange={pick} />
        <input ref={oneRef} type="file" multiple style={{ display: 'none' }} onChange={pick} />
      </div>

      {/* 定期同步固定文件夹:选一个文件夹长期监听,新增/改动文件自动入库 */}
      <div className="autosync-box glass">
        <div className="asx-head">
          <div>
            <div className="asx-title">定期同步文件夹</div>
            <div className="asx-sub">选一个文件夹长期监听 —— 以后往里放新文件(下载、截图、录音…)会<b>自动入库</b>,不用每次手动选。</div>
          </div>
          <button className="btn btn-primary" disabled={busy} onClick={addSyncFolder}>+ 添加文件夹</button>
        </div>
        {syncFolders.length > 0 && (
          <div className="asx-list">
            {syncFolders.map((f) => (
              <div key={f.path} className={`asx-item${f.exists ? '' : ' asx-missing'}`}>
                <span className="asx-dot" />
                <div className="asx-info">
                  <div className="asx-path" title={f.path}>{f.path}</div>
                  <div className="asx-meta">
                    已同步 <b>{f.synced}</b> 个文件
                    {f.exists ? '' : ' · ⚠ 文件夹已不存在'}
                    {f.last_scan ? ` · 上次扫描 ${f.last_scan.replace('T', ' ')}` : ''}
                  </div>
                </div>
                <button className="asx-rm" onClick={() => removeSyncFolder(f.path)} title="取消同步此文件夹">✕</button>
              </div>
            ))}
          </div>
        )}
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
          {/* ★网络抖动/服务忙时的软安抚(不报错,让用户安心等,别重传/放弃)*/}
          {!done && job.phase !== 'error' && job._stalled > 3 && (
            <div className="progress-hint" style={{ marginTop: 8, fontSize: 12.5, color: 'var(--text-3)', lineHeight: 1.6 }}>
              还在处理中 —— 网络抖动或后端正忙(大文件转写很吃资源),已自动重连,请稍候,<b>不用重传</b>。
            </div>
          )}
          {!done && job.phase !== 'error' && (
            <div className="progress-hint" style={{ marginTop: 6, fontSize: 12, color: 'var(--text-3)', lineHeight: 1.6 }}>
              视频 / 长录音转写通常需几分钟,请保持应用打开、别重复上传;进度偶尔卡住是正常的。
            </div>
          )}
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
