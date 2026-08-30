import React, { useState } from 'react'
import Guide, { SOURCES, SYNC_DL } from './Guide'

// 「说明」独立页:全平台使用手册 —— 功能总览 + 数据导入图文 + 同步状态 + AI模型/OCR/账号关键设置。
// 铁律:入口藏了=等于没做 —— 这页常驻左侧导航,不再埋在任何页面底部。

const FEATURES = [
  { name: '问答', desc: '对你的全部数据提问,答案带出处;新发现和提醒也在这里推给你。' },
  { name: '探索', desc: '主题星系:全库自动聚成主题簇,点任意主题看背后的原文。' },
  { name: '画像', desc: '基于你的全部数据生成的本人画像。' },
  { name: '人脉', desc: '每个联系人一张关系卡:情报、走势、群熟络度图,可直接「问TA」。' },
  { name: '雷达', desc: '主动盯:承诺待办、供需撮合、风险预警,不用你自己翻。' },
  { name: '洞察', desc: '跨文档的主动发现,系统替你把散落的线索连起来。' },
  { name: '好友', desc: '好友与匹配报告(只基于你真实填写的资料)。' },
  { name: '一生', desc: '用你的真实数据生成的「一生」脚本、动画与专属主题曲。' },
  { name: '文库', desc: '所有入库文档都在这,可读、可搜、可跳转出处。' },
  { name: '入库', desc: '导入数据的总入口:微信、文件、邮件、网页、拍照都从这进。' },
]

const SETTING_DOCS = [
  {
    t: 'AI 模型怎么填(设置 · AI 模型)',
    lines: [
      '选一家厂商,粘贴你自己的 API key —— key 只存在你机器上,不外传。',
      '「质量模型」和「快模型」都必填:点输入框会弹出推荐下拉,直接选即可;新模型出了也可以手动输入名字,不用等我们更新。',
      '质量模型跑交付物(报告 / PPT / 深度分析),快模型跑批量和交互(联系人情报 / 主题命名 / 问答)—— 又快又省钱,质量不受影响。',
      '填完点「测试连通」确认能用;若提示模型已下线,回设置换个新模型名即可。',
    ],
  },
  {
    t: 'OCR 识别:内置 vs 自选高精度(设置 · OCR 服务器地址)',
    lines: [
      '默认用内置轻量 OCR:纯本地、免费、开箱即用,普通截图和照片够用。',
      '扫描件多、版面复杂、追求更高识别率时,可填你自己的 OCR 服务地址(如百度 Unlimited-OCR / 自建 GPU 服务)切到高精度。',
      '留空 = 内置。随时可切换,不影响已入库内容。',
    ],
  },
  {
    t: '账号与安全(设置 · 账号安全)',
    lines: [
      '三种登录:手机验证码 / 手机号 + 密码;密码忘了在登录页用验证码重置,数据不丢。',
      '密码要求至少 8 位、混合两类以上字符 —— 你的聊天、人脉、文档都是核心隐私,值得一个强密码。',
      '指纹 / Face ID 免密登录、扫码登录正在接入中,上线后这里会更新说明。',
    ],
  },
]

const SYNC_STATES = [
  { key: 'detect', color: '#38bdf8', label: '检测中', desc: '正在探测你电脑上的「同步助手」,几秒内出结果。' },
  { key: 'live', color: '#4ade80', label: '实时同步中', desc: '一切正常:助手在线,你手机上的新消息几秒内自动进第二大脑。徽章旁能看到今天已同步多少条。' },
  { key: 'waiting', color: '#f59e0b', label: '等待客户端', desc: '云端账号正常,但你电脑上的助手没在跑 —— 打开「微信同步助手」并登录同一账号,即自动恢复。' },
  { key: 'off', color: '#5f6672', label: '已关闭', desc: '你手动暂停了同步。到「入库」页微信卡上点一下开关即恢复,期间的消息恢复后会自动补上。' },
]

export default function Help() {
  const [guideKey, setGuideKey] = useState(null)
  return (
    <div className="view">
      <div className="view-head">
        <h1>说明 · 三步用上第二大脑</h1>
        <p>照着下面 1 → 2 → 3 做,十分钟内你的微信聊天就会自动进大脑。任何一步卡住,截图发我们,远程带你跑通。</p>
      </div>

      {/* ===== 主线:跟着做 ===== */}
      <div className="hstep glass">
        <div className="hstep-head"><span className="hstep-n">1</span><b>下载并安装「微信同步助手」</b><span className="hstep-time">约 2 分钟 · 只装一次</span></div>
        <div className="hstep-body">
          <p>点下面对应你电脑的按钮下载。<b>不知道选哪个?</b>用 Windows 电脑就点第一个;用 Mac 就点屏幕左上角的苹果标 → 「关于本机」,看「芯片」那一行:写 <b>Apple M1/M2/M3/M4</b> 选第三个,写 <b>Intel</b> 选第二个。</p>
          <div className="help-dl-row">
            {SYNC_DL.map((d, i) => (
              <a key={i} className="guide-dl-btn" href={'/dl/' + encodeURIComponent(d.file)} download>
                <b>{d.label}</b><span>{d.hint}</span>
              </a>
            ))}
          </div>
          <p className="hstep-note">下载后:Windows 双击 .exe 一路下一步;Mac 双击 .dmg,把图标拖进「应用程序」。Mac 首次打开如果提示"无法验证开发者":在应用图标上<b>点右键 → 打开</b>,再点一次「打开」就好了(只需一次)。</p>
        </div>
      </div>

      <div className="hstep glass">
        <div className="hstep-head"><span className="hstep-n">2</span><b>在助手里点三下:抓密钥 → 开始同步</b><span className="hstep-time">约 2 分钟 · 一次搞定</span></div>
        <div className="hstep-body">
          <p>装好后助手<b>没有窗口</b>——它藏在电脑<b>右上角菜单栏</b>(Mac)或<b>右下角托盘</b>(Windows,小三角里),图标是一个圆点「微信同步」。点它,弹出菜单,按顺序做:</p>
          <ol className="hstep-ol">
            <li><b>点「抓取 / 更新密钥」</b> —— 会拉起微信,按提示<b>扫码登录一次</b>,然后在微信搜索框<b>随便搜一个词</b>(让它打开所有聊天库),等十几秒提示"已覆盖 N 个数据库"即可。密钥只抓这一次,以后一直有效。<span className="hstep-note">Windows 上:助手需<b>右键 → 以管理员身份运行</b>,抓密钥要重新登录一次微信。</span></li>
            <li><b>点「开始实时同步」</b> —— 图标变成绿色,状态显示"实时同步中"。</li>
            <li><b>(想核对就点)「打开控制面板」</b> —— 浏览器弹出深色面板,能看到"今日已同步 XX 条""覆盖 XX 个数据库"和最近消息滚动。还有个<b>「保存本地聊天数据」开关</b>:开=留在本地供分析,关=即焚不留档,你自己定。</li>
          </ol>
          <p className="hstep-note">之后只要<b>电脑版微信开着</b>,你手机上聊的每条消息几秒内自动进大脑。全程数据只在你自己电脑,连你的微信密码我们都碰不到。回到本站「入库」页看到顶部动画变<b>绿色"实时同步中"</b>就成了。</p>
        </div>
      </div>

      <div className="hstep glass optional">
        <div className="hstep-head"><span className="hstep-n">3</span><b>(可选)把以前的老聊天也补进来</b><span className="hstep-time">插一次 iPhone,约 10-20 分钟</span></div>
        <div className="hstep-body">
          <p>第 2 步只同步从今天开始的新消息。想让大脑认识"过去的你":用数据线把 iPhone 连上电脑,手机上点「信任」,然后在助手里点<b>「连手机导入历史」</b>,等进度条跑完拔线即可,以后不用再连。</p>
          <button className="btn" onClick={() => setGuideKey('ios')}>看 iPhone 导入的详细图文 →</button>
        </div>
      </div>

      <div className="hstep-done glass">
        做完以上,去<b>「问答」</b>页问一句试试:"我最近和谁聊得最多?" —— 从这一刻起,人脉、雷达、洞察都会自动开始为你工作。
      </div>

      <div className="help-sec-h" style={{ marginTop: 34 }}>其他数据怎么导入(邮件 / 网页 / 文件)</div>

      <div className="help-grid">
        {Object.entries(SOURCES).map(([k, s]) => (
          <div key={k} className="help-card glass" onClick={() => setGuideKey(k)}>
            <div className="hc-top">
              <span className="hc-dot" style={{ background: s.color }} />
              <span className="hc-name">{s.name}</span>
            </div>
            <div className="hc-intro">{s.intro}</div>
            <div className="hc-meta">
              <span>{(s.steps || []).length} 步图文</span>
              {s.faq && <span>· 常见问题 {s.faq.length} 条</span>}
              <span className="hc-go">查看步骤 →</span>
            </div>
          </div>
        ))}
      </div>

      <div className="help-sec-h" style={{ marginTop: 34 }}>遇到问题再看 · 状态徽章含义</div>
      <div className="help-states glass">
        {SYNC_STATES.map((s) => (
          <div key={s.key} className="hs-row">
            <span className="hs-badge"><span className="hs-dot" style={{ background: s.color }} />{s.label}</span>
            <span className="hs-desc">{s.desc}</span>
          </div>
        ))}
      </div>

      <div className="help-sec-h" style={{ marginTop: 30 }}>每一页是干什么的</div>
      <div className="help-states glass" style={{ marginBottom: 26 }}>
        {FEATURES.map((f) => (
          <div key={f.name} className="hs-row">
            <span className="hs-badge">{f.name}</span>
            <span className="hs-desc">{f.desc}</span>
          </div>
        ))}
      </div>

      <div className="help-sec-h" style={{ marginTop: 30 }}>关键设置说明</div>
      {SETTING_DOCS.map((d) => (
        <div key={d.t} className="help-doc glass">
          <div className="hd-title">{d.t}</div>
          {d.lines.map((l, i) => <div key={i} className="hd-line"><span className="hd-dash" />{l}</div>)}
        </div>
      ))}

      <div className="help-contact glass">
        <b>搞不定?我们帮接。</b>把卡住那一步的截图和你的电脑系统(Windows / Intel Mac / Apple 芯片 Mac)发给我们,远程陪你装到通;数据量大的也可以整体交给我们代接。
      </div>

      {guideKey && <Guide sourceKey={guideKey} onClose={() => setGuideKey(null)} />}
    </div>
  )
}
