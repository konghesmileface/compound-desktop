import React from 'react'
import { IconClose } from './icons'

// 各数据源的「秒懂」分步引导。铁律:小白照着点,最少步骤把数据搞进来,最详细指导,搞不定我们帮接。
// 微信同步助手 · 自有三平台安装包(106 下载中心,公开可达)
export const SYNC_DL = [
  { label: 'Windows 版', file: '微信同步助手-Windows.exe', hint: 'Windows 10 / 11,双击安装' },
  { label: 'Mac · Intel 芯片', file: '微信同步助手-mac-Intel.dmg', hint: '较早的 Mac(约2020年前)' },
  { label: 'Mac · Apple 芯片', file: '微信同步助手-mac-arm64.dmg', hint: 'M1 / M2 / M3 / M4' },
]
// 助手安装包=打进包本地发(sidecar /dl,离线、区域无关,不连云端)。客户端 base=注入的本机
// sidecar 端口;网页版 base='' 同源(106 的 /dl)。客户端 webview 里 target=_blank 打不开外链,
// 故走 Tauri open_external 用系统浏览器打开本地 URL 触发下载。
const DL_BASE = ((typeof window !== 'undefined' && window.__COMPOUND_API_BASE__) || '') + '/dl/'
export function syncHref(file) { return DL_BASE + encodeURIComponent(file) }
export function onSyncDownload(e, file) {
  if (typeof window !== 'undefined' && window.__TAURI__ && window.__TAURI__.core) {
    e.preventDefault()
    window.__TAURI__.core.invoke('open_external', { url: DL_BASE + encodeURIComponent(file) })
  }
}
// tile:false 的不在「更多数据来源」网格里露出(只从微信同步卡的按钮打开)。
export const SOURCES = {
  // ── 微信 · 实时同步(电脑自动,日常主力)────────────────────────────
  realtime: {
    name: '微信 · 实时同步(电脑自动)', color: '#4ade80',
    reassure: ['全程只在你自己电脑', '聊天一个字都不上传', '读完即焚 · 开源可审计'],
    intro: '装一个「同步助手」,开着电脑版微信——你在手机上聊的每一条,几秒内自动进第二大脑帮你分析,你什么都不用做。全程在你自己电脑上完成,聊天内容一个字都不会传到我们这。',
    dls: SYNC_DL,
    steps: [
      { t: '第一步 · 点上面的按钮下载安装包(一次)', d: 'Windows 电脑点「Windows 版」下载 .exe,双击安装即可。Mac 先看自己是什么芯片:点屏幕左上角苹果标 → 「关于本机」→ 看「芯片」一行,写 Apple M1/M2/M3/M4 就点「Apple 芯片」版,写 Intel 就点「Intel 芯片」版;下载 .dmg 后双击打开,把图标拖进「应用程序」。Apple 芯片版首次打开如被拦,在应用上点右键 → 「打开」放行一次即可。装错版本会有提示,换另一个装就行。' },
      { t: '第二步 · 首次授权(一次,输一次电脑开机密码)', d: '第一次打开会弹一次系统授权,输入你电脑的开机密码点「允许」。这是让助手能读你自己微信的本地数据——只这一次,以后不再问。全程不联网、不碰你的微信账号密码。' },
      { t: '★第三步 · 点「抓取 / 更新密钥」(关键!不做这步会同步到空)', d: '微信聊天在电脑上是加密存的,助手要先拿到「解密钥匙」才能读。打开助手面板,点「抓取 / 更新密钥」按钮,按提示登录弹出的微信、在微信搜索框随便搜个词(触发它把所有聊天库都打开一次),助手就抓到钥匙了。面板上「密钥」数字从 0 变成有值,就成功了。换微信大版本后偶尔要再点一次。' },
      { t: '第四步 · 点「开始实时同步」,开着电脑版微信', d: '有了密钥,点「开始实时同步」。之后你手机收发的新消息会同步到电脑,助手几秒内自动读进第二大脑。本页顶部绿色徽章会亮起「正在实时同步」,还能看到今天进了多少条。想暂停,点一下开关即可。' },
    ],
    payoff: {
      title: '入库后,你就能在「问答 / 人脉 / 雷达」里这样用:',
      items: ['总结我和某某的聊天,还有什么要跟进', '我答应过谁什么还没做?按时间提醒我', '谁手上有资产、谁在找,能不能撮合', '我马上要见的这个人,给我份见面简报'],
    },
    faq: [
      { q: '我的聊天会不会泄露?你们看得到吗?', a: '看不到。解密和读取全在你自己电脑上完成,聊天内容一个字都不上传到我们服务器;助手读完即从本地临时文件删除(读完即焚),不留明文。我们连你的微信账号密码都接触不到,代码开源可审计。你也可以随时一键删除全部数据。' },
      { q: '要一直连着手机吗?', a: '不用。日常实时同步读的是电脑版微信的本地数据,跟手机没关系——只要电脑上开着微信就行,不插线。只有想「补早期历史」那一次,才用 iPhone 导入。' },
      { q: '换了新电脑怎么办?', a: '在新电脑上重新装一次助手、登录电脑版微信、走一遍首次授权即可;你已经进第二大脑的记忆都在云端账号里,不会丢。相当于把「数据入口」搬到新电脑。' },
      { q: '实时同步突然不动了?', a: '一般是微信升级了。助手会自动检测并修复,顶部徽章会提示「同步已暂停」。若长时间不恢复,可先用「iPhone 导入」把这期间的消息补上,我们也会尽快推送助手更新。' },
    ],
    tip: '一句话:装好助手 → 开着电脑版微信 → 自动实时入库。图片 / 语音 / 文件先标成 [图片] [语音] 占位,后续版本自动转文字。',
    help: '装不上或授权卡住?把你的系统(Win/Intel Mac/Apple Mac)发我们,我们远程陪你装到通,或替你打好一键包。',
  },

  // ── iPhone · 导入历史聊天(连一次线,补早期)──────────────────────
  ios: {
    name: 'iPhone · 导入历史聊天', color: '#38bdf8',
    reassure: ['只读你自己的备份', '不越狱 · 不改手机', '全程在本机完成'],
    intro: 'iPhone 上的微信记录本身就是明文,连一次数据线,就能把电脑版登录之前的全部老聊天一次性补进第二大脑。做一次即可,平时不用连。',
    steps: [
      { t: '第一步 · 装一次连接工具(一次)', d: 'Mac:助手会引导你装 libimobiledevice(一条命令,或助手内一键装)。Windows:装官方 iTunes 即可(提供同样的连接能力)。装过就不用再装。' },
      { t: '第二步 · 数据线连 iPhone,点「信任」', d: '用数据线把 iPhone 连上电脑,手机上弹出「要信任这台电脑吗?」点「信任」,并输入手机锁屏密码。保持手机解锁、别拔线。' },
      { t: '第三步 · 在助手里点「连手机导入历史」', d: '助手会自动:备份手机 → 找到微信明文库 → 抽成「[时间] 我/对方: 内容」的对话 → 逐个入库。每一步都有进度条(连接手机 / 备份中 / 解析库 / 上传中 / 完成),你只需等它跑完。' },
      { t: '第四步 · 完成后拔线', d: '导完就能拔线,历史聊天已经进第二大脑,可搜可问可分析。以后日常靠「电脑实时同步」增量更新,不用再连手机。' },
    ],
    payoff: {
      title: '补齐历史后,时间跨度拉满,这些才准:',
      items: ['我和这个人最早是怎么认识的?', '去年他跟我提过的那件事,后来怎样了', '这段关系这几年是升温还是降温'],
    },
    faq: [
      { q: '要越狱 / 会不会弄坏我手机?', a: '都不会。用的是苹果官方的本地备份能力(和 iTunes 备份同一套),只读、不写、不改你手机里任何东西,更不用越狱。' },
      { q: '备份好慢?', a: '第一次全量备份和你微信历史多少有关,聊天多可能十几分钟,插着线耐心等进度条即可。之后就不用再备份了。' },
      { q: '安卓手机能这样导吗?', a: '安卓不走这条线。安卓用户直接用「电脑实时同步」即可覆盖日常;想要老历史可联系我们代接。' },
    ],
    tip: '只需连这一次。全程在你自己电脑上完成,备份和明文库读完即清理,不外传。',
    help: '连不上手机 / 认不到设备?把你的电脑系统和手机型号发我们,我们远程帮你把这一次导入跑通。',
  },

  // ── 邮件 · Gmail 全量导入 ────────────────────────────────────────
  email: {
    name: '邮件 · 全量导入(Gmail / QQ / 163 / Outlook)', color: '#f0abfc',
    reassure: ['用邮箱官方导出', '不用给我们任何密码'],
    intro: '把你的邮件导出成文件(.mbox 或 .eml),回来这里一选,全部邮件自动逐封入库、可搜可问,再也不用一封封翻。不同邮箱导出方法不同,对号入座:',
    steps: [
      { t: 'Gmail · 用官方 Takeout(最简单)', d: '浏览器访问 takeout.google.com 登录 → 点「取消全选」后只勾「Mail」→ 拉到底「下一步 → 创建导出」→ 下载得到 .mbox 文件。邮件多会拆成几个包,全下载解压,里面的 .mbox 都要。' },
      { t: 'QQ 邮箱 / 163 邮箱 · 借邮件客户端导出', d: '这两家没有官方一键导出,走客户端:①先在网页版邮箱开启 IMAP(QQ:设置→账户→开启 IMAP/SMTP 服务,会给你一个授权码;163:设置→POP3/SMTP/IMAP 开启);②电脑装 Foxmail(免费),用邮箱账号+授权码登录,等它把全部邮件收下来;③在 Foxmail 里选中邮件(Ctrl+A 全选)→ 右键「导出邮件」,得到一批 .eml 文件。' },
      { t: 'Outlook / 其他邮箱', d: '任何能导出 .eml 或 .mbox 的都行:Outlook 可把邮件拖拽到文件夹自动存成 .eml;苹果 Mail 选中邮件 → 文件 → 存储为。拿到文件就行,格式我们都认。' },
      { t: '最后一步 · 回来点「选择文件」', d: '在本页把导出的 .mbox / .eml 一次性全选上传,系统自动逐封提取入库。几千封也没关系,后台会慢慢吃完。' },
    ],
    faq: [
      { q: '授权码是什么?安全吗?', a: '授权码是 QQ/163 给第三方客户端用的专用密码,只给你自己电脑上的 Foxmail 用,不经过我们。我们只接收你最终导出的邮件文件,拿不到你的任何密码或授权码。' },
      { q: '邮件太多、分了好几个压缩包?', a: '正常。全部下载解压后,把里面的 .mbox / .eml 一次性都选上上传即可,不用分批。' },
    ],
    tip: '全程在你和邮箱服务商之间完成,我们只接收导出好的文件,拿不到你的邮箱密码。',
    help: '导出步骤卡住?说一声你用的是什么邮箱+截图,我们一步步带你拿到文件,或远程替你导。',
  },

  // ── 网页 / 文章 ─────────────────────────────────────────────────
  web: {
    name: '网页 / 文章', color: '#38bdf8',
    intro: '任何网页都能存成 PDF 或 HTML 再入库;或直接在入库页粘贴网址一键抓取。',
    steps: [
      { t: '方式一 · 直接粘贴网址', d: '在上方入库框粘贴文章 / B站 / 播客链接,点「抓取入库」,正文(视频语音自动转文字)会被提取。' },
      { t: '方式二 · 存成 PDF 再选', d: '在浏览器打开网页,按 Cmd/Ctrl+P → 目标选「存储为 PDF」,再回来「选择文件」选它。' },
    ],
    tip: '整站 / 大量网页可后续用「网址抓取」连接器(规划中)。',
  },
}

export default function Guide({ sourceKey, onClose }) {
  const s = SOURCES[sourceKey]
  if (!s) return null
  return (
    <div className="guide-overlay" onClick={onClose}>
      <div className="guide glass" onClick={(e) => e.stopPropagation()}>
        <div className="x" onClick={onClose}><IconClose /></div>
        <div className="guide-badge" style={{ background: s.color }} />
        <h2>{s.name}</h2>
        {s.reassure && (
          <div className="guide-reassure">
            {s.reassure.map((r, i) => <span key={i} className="gr-chip" style={{ borderColor: s.color }}>{r}</span>)}
          </div>
        )}
        <p className="guide-intro">{s.intro}</p>
        {s.dl && <a className="guide-dl btn btn-primary" href={s.dl.url} target="_blank" rel="noreferrer">{s.dl.label}</a>}
        {s.dls && (
          <div className="guide-dls">
            {s.dls.map((d, i) => (
              <a key={i} className="guide-dl-btn" href={syncHref(d.file)} onClick={(e) => onSyncDownload(e, d.file)} target="_blank" rel="noreferrer">
                <b>{d.label}</b><span>{d.hint}</span>
              </a>
            ))}
          </div>
        )}
        <div className="guide-steps">
          {s.steps.map((st, i) => (
            <div key={i} className="guide-step">
              <div className="gs-num" style={{ background: s.color }}>{i + 1}</div>
              <div className="gs-body">
                <div className="gs-title">{st.t}</div>
                <div className="gs-desc">{st.d}</div>
              </div>
            </div>
          ))}
        </div>
        {s.payoff && (
          <div className="guide-payoff">
            <div className="gp-title">{s.payoff.title}</div>
            {s.payoff.items.map((it, i) => <div key={i} className="gp-item">“{it}”</div>)}
          </div>
        )}
        {s.faq && (
          <div className="guide-faq">
            {s.faq.map((f, i) => (
              <div key={i} className="gf-item">
                <div className="gf-q">{f.q}</div>
                <div className="gf-a">{f.a}</div>
              </div>
            ))}
          </div>
        )}
        {s.tip && <div className="guide-tip"><span className="gt-label">提示</span>{s.tip}</div>}
        {s.help && <div className="guide-help"><span className="gh-label">搞不定?</span>{s.help}</div>}
      </div>
    </div>
  )
}
