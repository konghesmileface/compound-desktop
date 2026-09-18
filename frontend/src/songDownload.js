// 冥想歌下载(桌面):现场打 ID3(歌词+黑胶封面,复用手机端已实证的 id3.js)→
// sidecar /api/save_song 直接落「下载」文件夹 + 文件管理器高亮。
// ★不再 openExternal:那会拉起系统浏览器在线播放,既没存盘也看不到歌词封面(机主暴怒的那个)。
import { apiUrl, saveSongLocally } from './api'
import { tagSongBlob } from './id3'
import { toast } from './ui'

export async function downloadSongTagged(song) {
  try {
    const resp = await fetch(apiUrl(song.url))
    if (!resp.ok) throw new Error('取音频失败 ' + resp.status)
    const tagged = await tagSongBlob(await resp.blob(), song)
    const name = (song.title || '主题曲').replace(/[/\\:*?"<>|]/g, '').slice(0, 40) + '.mp3'
    if (typeof window !== 'undefined' && window.__TAURI__ && window.__TAURI__.core) {
      const b64 = await new Promise((res, rej) => {
        const fr = new FileReader()
        fr.onloadend = () => res(String(fr.result).split(',')[1] || '')
        fr.onerror = rej
        fr.readAsDataURL(tagged)
      })
      const path = await saveSongLocally(name, b64)
      if (!path) throw new Error('保存失败')
      toast('已存到「下载」文件夹:' + name + '(含歌词+封面)', 'ok')
    } else {
      // 纯浏览器环境:blob 直接触发下载(成品同样带标签)
      const u = URL.createObjectURL(tagged)
      const a = document.createElement('a')
      a.href = u; a.download = name
      document.body.appendChild(a); a.click()
      setTimeout(() => { a.remove(); URL.revokeObjectURL(u) }, 1000)
    }
    return true
  } catch (e) {
    toast('下载失败:' + ((e && e.message) || '稍后再试'), 'err')
    return false
  }
}
