// 双色调图标:低透明填充体 + 描边细节,继承 currentColor。24 网格。
const St = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.7, strokeLinecap: 'round', strokeLinejoin: 'round' }
const fillOp = 0.2

// 品牌 mark:Compound(复利)—— 粗体字母标"C"(彗尾)+ 顶端金色彗头=复利的下一颗。经得起缩成 app 图标。
export const Logo = () => (
  <svg viewBox="0 0 24 24" fill="none">
    <defs>
      <linearGradient id="lgc" x1="4.5" y1="20" x2="19" y2="4.5" gradientUnits="userSpaceOnUse">
        <stop offset="0" stopColor="#5b6ef5" /><stop offset="0.52" stopColor="#41c6ef" /><stop offset="1" stopColor="#8fe9ff" />
      </linearGradient>
      <radialGradient id="lgdot" cx="40%" cy="36%" r="70%">
        <stop offset="0" stopColor="#fff4d6" /><stop offset="0.4" stopColor="#fbbf24" /><stop offset="1" stopColor="#f59e0b" />
      </radialGradient>
    </defs>
    {/* 粗体 C 弧:开口朝右上,笔画由细到粗(复利加速) */}
    <path d="M16.4 17.8 A 7.7 7.7 0 1 1 17.6 7.2" stroke="url(#lgc)" strokeWidth="3.7" strokeLinecap="round" />
    {/* 顶端金色彗头 = 下一颗 */}
    <circle cx="17.6" cy="7.2" r="3.3" fill="#fbbf24" opacity="0.2" />
    <circle cx="17.6" cy="7.2" r="2.55" fill="url(#lgdot)" />
    <circle cx="16.8" cy="6.5" r="0.75" fill="#fffdf5" opacity="0.72" />
  </svg>
)

// 探索:星系(中心大节点 + 卫星 + 轨道)
export const IconExplore = () => (
  <svg viewBox="0 0 24 24">
    <circle cx="12" cy="12" r="3.2" fill="currentColor" opacity={fillOp} />
    <circle cx="12" cy="12" r="3.2" {...St} />
    <circle cx="12" cy="4.4" r="1.7" fill="currentColor" />
    <circle cx="18.6" cy="15.6" r="1.7" fill="currentColor" />
    <circle cx="5.4" cy="15.6" r="1.7" fill="currentColor" />
    <path d="M12 6v2.8M14 13.6l3 1.2M10 13.6l-3 1.2" {...St} strokeWidth="1.5" />
  </svg>
)

// 搜索:放大镜(镜片填充)
export const IconSearchNav = () => (
  <svg viewBox="0 0 24 24">
    <circle cx="10.5" cy="10.5" r="6.5" fill="currentColor" opacity={fillOp} />
    <circle cx="10.5" cy="10.5" r="6.5" {...St} />
    <path d="m20 20-4.3-4.3" {...St} />
  </svg>
)

// 问答:对话气泡 + 火花
export const IconLife = () => (
  <svg viewBox="0 0 24 24">
    <path d="M3 15c3-6 5-9 6-9s1.5 3 3 3 2-2 3-2 3 3 6 8" {...St} />
    <circle cx="18" cy="6.5" r="2.4" fill="currentColor" opacity={fillOp} />
    <circle cx="18" cy="6.5" r="2.4" {...St} />
    <circle cx="9" cy="6" r="1.2" fill="currentColor" />
  </svg>
)

export const IconFriends = () => (
  <svg viewBox="0 0 24 24">
    <circle cx="8.5" cy="9" r="2.6" fill="currentColor" opacity={fillOp} />
    <circle cx="8.5" cy="9" r="2.6" {...St} />
    <circle cx="16" cy="10.5" r="2" {...St} />
    <path d="M3.5 18.5a5 5 0 0 1 10 0M14 18.5a4.2 4.2 0 0 1 6.5-3.5" {...St} />
    <path d="M11 8.5l2.5 1.2" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" opacity="0.6" />
  </svg>
)

export const IconNetwork = () => (
  <svg viewBox="0 0 24 24">
    <path d="M6.6 7.2L10.4 10.6M17.4 8L13.7 10.7M16.8 16.6L13.6 13.6M7.2 16.6L10.4 13.6" {...St} />
    <circle cx="12" cy="12" r="2.5" fill="currentColor" opacity={fillOp} />
    <circle cx="12" cy="12" r="2.5" {...St} />
    <circle cx="5" cy="6" r="1.9" {...St} />
    <circle cx="19" cy="6.6" r="1.9" {...St} />
    <circle cx="18.2" cy="18" r="1.9" {...St} />
    <circle cx="5.8" cy="18" r="1.9" {...St} />
  </svg>
)

export const IconRadar = () => (
  <svg viewBox="0 0 24 24">
    <circle cx="12" cy="12" r="9" {...St} />
    <circle cx="12" cy="12" r="5.4" {...St} opacity="0.55" />
    <circle cx="12" cy="12" r="1.6" fill="currentColor" opacity={fillOp} />
    <path d="M12 12L18.4 7.2" {...St} />
    <path d="M12 3v3.2" {...St} opacity="0.5" />
  </svg>
)

export const IconInsight = () => (
  <svg viewBox="0 0 24 24">
    <path d="M5 19V11M12 19V5M19 19V14" {...St} />
    <path d="M4 21h16" {...St} opacity="0.6" />
  </svg>
)

export const IconPersona = () => (
  <svg viewBox="0 0 24 24">
    <circle cx="12" cy="8" r="3.4" fill="currentColor" opacity={fillOp} />
    <circle cx="12" cy="8" r="3.4" {...St} />
    <path d="M5.5 19.5a6.5 6.5 0 0 1 13 0" {...St} />
    <circle cx="18.5" cy="6" r="1.5" fill="currentColor" />
    <circle cx="6" cy="6.5" r="1.1" fill="currentColor" opacity="0.7" />
  </svg>
)

export const IconAsk = () => (
  <svg viewBox="0 0 24 24">
    <path d="M4 6a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2H9l-4 3.5V14H6a2 2 0 0 1-2-2z" fill="currentColor" opacity={fillOp} />
    <path d="M4 6a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2H9l-4 3.5V14a2 2 0 0 1-1-2z" {...St} />
    <path d="M19.5 8.5l.6 1.5 1.5.6-1.5.6-.6 1.5-.6-1.5-1.5-.6 1.5-.6z" fill="currentColor" />
  </svg>
)

// 文库:堆叠文档
export const IconLibrary = () => (
  <svg viewBox="0 0 24 24">
    <rect x="4" y="3.5" width="11" height="14.5" rx="2" fill="currentColor" opacity={fillOp} />
    <rect x="4" y="3.5" width="11" height="14.5" rx="2" {...St} />
    <path d="M7.5 7.5h4M7.5 11h4" {...St} strokeWidth="1.5" />
    <path d="M18.5 6.8A2 2 0 0 1 19.5 8.5v10a2 2 0 0 1-2 2H8.2" {...St} />
  </svg>
)

// 入库:向上导入托盘
export const IconIngest = () => (
  <svg viewBox="0 0 24 24">
    <path d="M4.5 13.5h4L9.5 15h5l1-1.5h4v4.5a2 2 0 0 1-2 2h-11a2 2 0 0 1-2-2z" fill="currentColor" opacity={fillOp} />
    <path d="M12 14.5V4M8.5 7.5 12 4l3.5 3.5" {...St} />
    <path d="M4.5 14v4a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2v-4" {...St} />
  </svg>
)

// 设置:滑杆
export const IconSettings = () => (
  <svg viewBox="0 0 24 24">
    <path d="M4 7h16M4 12h16M4 17h16" {...St} opacity="0.4" />
    <circle cx="9" cy="7" r="2.4" fill="currentColor" opacity={fillOp} /><circle cx="9" cy="7" r="2.4" {...St} />
    <circle cx="15" cy="12" r="2.4" fill="currentColor" opacity={fillOp} /><circle cx="15" cy="12" r="2.4" {...St} />
    <circle cx="8" cy="17" r="2.4" fill="currentColor" opacity={fillOp} /><circle cx="8" cy="17" r="2.4" {...St} />
  </svg>
)

// 作品集:黑胶唱片(碟 + 中心标签 + 反光)
export const IconGallery = () => (
  <svg viewBox="0 0 24 24">
    <circle cx="12" cy="12" r="8.4" fill="currentColor" opacity={fillOp} />
    <circle cx="12" cy="12" r="8.4" {...St} />
    <circle cx="12" cy="12" r="4.6" {...St} strokeWidth="1.3" opacity="0.55" />
    <circle cx="12" cy="12" r="2.2" fill="currentColor" opacity={fillOp} />
    <circle cx="12" cy="12" r="2.2" {...St} strokeWidth="1.3" />
    <circle cx="12" cy="12" r="0.7" fill="currentColor" />
    <path d="M14.6 6.2a6 6 0 0 1 3.2 3.2" {...St} strokeWidth="1.3" opacity="0.7" />
  </svg>
)

// 抽屉/搜索框内用的细线图标
export const IconSearch = () => (
  <svg viewBox="0 0 24 24" {...St}><circle cx="11" cy="11" r="7" /><path d="m21 21-4.1-4.1" /></svg>
)
export const IconClose = () => (
  <svg viewBox="0 0 24 24" {...St}><path d="M6 6l12 12M18 6 6 18" /></svg>
)
// 下载:向下箭头 + 托盘底(替代 ⬇ emoji)
export const IconDownload = () => (
  <svg viewBox="0 0 24 24" {...St}><path d="M12 4v10m0 0 4-4m-4 4-4-4" /><path d="M5 18.5h14" /></svg>
)
// 播放:实心三角(替代 ▶ emoji),用 currentColor 单色
export const IconPlay = () => (
  <svg viewBox="0 0 24 24"><path d="M8 5.5v13l11-6.5z" fill="currentColor" /></svg>
)

// 说明:摊开的手册(左右页 + 中缝)
export const IconHelp = () => (
  <svg viewBox="0 0 24 24">
    <path d="M4.5 5.6c2.4-1.2 5-1.2 7.5.2 2.5-1.4 5.1-1.4 7.5-.2v12.8c-2.4-1.2-5-1.2-7.5.2-2.5-1.4-5.1-1.4-7.5-.2z" fill="currentColor" opacity={fillOp} />
    <path d="M4.5 5.6c2.4-1.2 5-1.2 7.5.2 2.5-1.4 5.1-1.4 7.5-.2v12.8c-2.4-1.2-5-1.2-7.5.2-2.5-1.4-5.1-1.4-7.5-.2z" {...St} />
    <path d="M12 5.8v12.8" {...St} strokeWidth="1.5" />
    <path d="M7 9.2c1.2-.3 2.3-.3 3.2 0M7 12.2c1.2-.3 2.3-.3 3.2 0M13.8 9.2c1.2-.3 2.3-.3 3.2 0M13.8 12.2c1.2-.3 2.3-.3 3.2 0" {...St} strokeWidth="1.3" opacity="0.75" />
  </svg>
)
