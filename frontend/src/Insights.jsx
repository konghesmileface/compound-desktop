import React, { useState, useEffect, useRef } from 'react'
import { api } from './api'
import { Thinking, Empty } from './ui'
import { IconNetwork, IconInsight } from './icons'
import ContactGraph from './ContactGraph'

// 画像叙述里的极简 markdown 渲染(## 标题 / **加粗**)
function renderMd(md) {
  return (md || '').split('\n').filter((l) => l.trim()).map((line, i) => {
    if (line.startsWith('## ')) return <div key={i} className="por-h">{line.slice(3)}</div>
    if (line.startsWith('# ')) return <div key={i} className="por-h">{line.slice(2)}</div>
    const parts = line.replace(/^[-*]\s+/, '· ').split(/(\*\*[^*]+\*\*)/g).map((p, j) =>
      p.startsWith('**') && p.endsWith('**') ? <b key={j}>{p.slice(2, -2)}</b> : p)
    return <div key={i} className="por-p">{parts}</div>
  })
}
const POR_BUCKETS = [
  ['机构 · 公司', ['公司', '机构'], '#8b8cff'],
  ['业务 · 项目', ['项目', '产品'], '#fb7185'],
  ['地域', ['地点'], '#38bdf8'],
]

// 洞察 · 复盘:你自己看不见的关系与业务全景
export default function Insights({ onOpen, onAsk }) {
  const [tab, setTab] = useState('portrait')
  const [portrait, setPortrait] = useState(null)
  const [porBusy, setPorBusy] = useState(false)
  const [balance, setBalance] = useState(null)
  const [panorama, setPanorama] = useState(null)
  const [checkup, setCheckup] = useState(null)

  useEffect(() => {
    if (tab === 'portrait' && portrait === null) api.portrait().then(setPortrait).catch(() => setPortrait({ by_type: {}, narrative: '' }))
    if (tab === 'balance' && balance === null) api.balance().then(setBalance).catch(() => setBalance({}))
    if (tab === 'panorama' && panorama === null) api.panorama().then(setPanorama).catch(() => setPanorama({ topics: [] }))
    if (tab === 'checkup' && checkup === null) api.checkup().then(setCheckup).catch(() => setCheckup({ they_wait: [], i_went_cold: [] }))
  }, [tab])

  const porInflight = useRef(false)
  const reloadPortrait = () => {
    if (porInflight.current) return   // P1-19:真并发去重(disabled 状态异步更新,快双击仍会漏进来)
    porInflight.current = true
    setPorBusy(true); setPortrait(null)
    api.portrait(true).then(setPortrait).catch(() => setPortrait({ by_type: {}, narrative: '' })).finally(() => { porInflight.current = false; setPorBusy(false) })
  }

  const group = (title, list, color, render) => (
    (list || []).length > 0 && (
      <div className="ins-group">
        <div className={'ins-group-t ' + color}>{title} · {list.length}</div>
        <div className="ins-chips">{list.map((x, i) => render(x, i))}</div>
      </div>
    )
  )

  return (
    <div className="view ins-view">
      <div className="view-head">
        <div>
          <h1>洞察</h1>
          <p>给你一面镜子:你的人脉在升值还是流失、精力花在谁身上、每件事进展到哪、你的沟通有没有漏。</p>
        </div>
      </div>

      <div className="radar-tabs">
        {[['portrait', '联系人画像'], ['balance', '关系资产负债表'], ['panorama', '业务全景'], ['checkup', '沟通体检']].map(([k, lab]) => (
          <button key={k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}>{lab}</button>
        ))}
      </div>

      {/* 联系人画像 */}
      {tab === 'portrait' && (
        portrait === null ? <Thinking phases={['扫描你所有联系人的身份与所在机构…', '归纳行业分布、核心机构、你们的交集…']} hint="正在给你的人脉画像" /> : (
          <div className="radar-body por-wrap">
            <div className="por-top">
              <div className="por-stats">
                <div className="por-stat" title="当前有效联系人数(已去重、过滤群聊与系统号)"><b>{portrait.contacts || 0}</b><span>联系人</span></div>
                <div className="por-stat" title="已生成人脉档案的对象数,含历史联系人与群内成员,可能多于当前联系人"><b>{portrait.with_cards || 0}</b><span>已画像</span></div>
              </div>
              <button className={'por-refresh' + (porBusy ? ' busy' : '')} disabled={porBusy} onClick={reloadPortrait}>{porBusy ? '重新生成中…' : '重新生成'}</button>
            </div>

            <div className="por-graph-wrap">
              <div className="por-graph-t">人脉关系网 · 每颗星是一个人,连线=共同的机构/项目/事,颜色=同一圈子</div>
              <ContactGraph onOpen={onOpen} />
            </div>

            {portrait.narrative && <div className="por-narr glass">{renderMd(portrait.narrative)}</div>}

            {(portrait.groups || []).length > 0 && (
              <div className="por-groups">
                <div className="por-sec-t">按领域分组的联系人</div>
                {portrait.groups.map((g, gi) => (
                  <div key={gi} className="por-grp">
                    <div className="por-grp-h"><span className="por-grp-name">{g.name}</span><span className="por-grp-n">{(g.members || []).length}</span></div>
                    <div className="por-grp-people">
                      {(g.members || []).map((m, mi) => (
                        <span key={mi} className={'por-person' + (m.doc_id != null ? '' : ' flat')}
                          onClick={() => m.doc_id != null && onOpen && onOpen(m.doc_id)}>{m.name}</span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {POR_BUCKETS.map(([label, etypes, color]) => {
              const ents = etypes.flatMap((et) => (portrait.by_type && portrait.by_type[et]) || [])
                .sort((a, b) => (b.people || 0) - (a.people || 0)).slice(0, 30)
              if (!ents.length) return null
              const max = ents[0].people || 1
              return (
                <div key={label} className="por-cloud-sec">
                  <div className="por-cloud-t" style={{ color }}>{label}</div>
                  <div className="por-cloud">
                    {ents.map((e, i) => {
                      const sz = 12 + Math.round((e.people / max) * 9)
                      return (
                        <span key={i} className="por-tag" style={{ fontSize: sz + 'px', borderColor: color + '66', color }}
                          onClick={() => onAsk && onAsk('我认识的人里,和「' + e.name + '」有关的都有谁?他们各自什么角色、和我什么交集?')}
                          title={e.people + ' 位联系人涉及'}>
                          {e.name}{e.people > 1 && <i className="por-tag-n">{e.people}</i>}
                        </span>
                      )
                    })}
                  </div>
                </div>
              )
            })}

            {!portrait.narrative && !(portrait.groups || []).length && !Object.values(portrait.by_type || {}).some((a) => (a || []).length) && (
              <Empty icon={<IconInsight />} title="还没有联系人画像" sub="导入微信聊天后,AI 会识别你的圈子、核心机构与人脉母题,自动为你生成画像" />
            )}
            {(portrait.narrative || (portrait.groups || []).length > 0) && !portrait.entity_ready && (
              <div className="por-note">聊天里的机构 / 行业 / 项目正在逐个分析入库,完成后这里会长出可视化标签云。</div>
            )}
          </div>
        )
      )}

      {/* 关系资产负债表 */}
      {tab === 'balance' && (
        balance === null ? <Thinking phases={['统计近 90 天的互动…', '分出升温/降温/流失/新增…']} hint="正在结算你的关系资产" /> : (
          <div className="radar-body">
            <div className="rad-sub">近 {balance.window_days || 90} 天 vs 上一个 {balance.window_days || 90} 天,你的人脉盘面</div>
            {group('升温中', balance.warming, 'good', (x, i) => <span key={i} className="ins-chip good" onClick={() => onOpen && onOpen(x.doc_id)}>{x.contact} <b>{x.recent}</b></span>)}
            {group('降温中', balance.cooling, 'warn', (x, i) => <span key={i} className="ins-chip warn" onClick={() => onOpen && onOpen(x.doc_id)}>{x.contact} {x.prior}→{x.recent}</span>)}
            {group('已流失', balance.fading, 'bad', (x, i) => <span key={i} className="ins-chip bad" onClick={() => onOpen && onOpen(x.doc_id)}>{x.contact}</span>)}
            {group('新拓关系', balance.fresh, 'good', (x, i) => <span key={i} className="ins-chip good" onClick={() => onOpen && onOpen(x.doc_id)}>{x.contact}</span>)}
            {!(balance.warming || []).length && !(balance.cooling || []).length && !(balance.fading || []).length && !(balance.fresh || []).length && !(balance.time_spent || []).length && (
              <Empty icon={<IconInsight />} title="还没有关系资产数据" sub="导入更多微信聊天后,这里会显示谁在升温、谁在流失、你的精力花在谁身上" />
            )}
            {(balance.time_spent || []).length > 0 && (
            <div className="ins-group">
              <div className="ins-group-t">精力花在谁身上(近 {balance.window_days || 90} 天消息量)</div>
              {(balance.time_spent || []).map((x, i) => {
                const max = (balance.time_spent && balance.time_spent[0] && balance.time_spent[0].recent) || 1
                return (
                  <div key={i} className="ins-bar-row" onClick={() => onOpen && onOpen(x.doc_id)}>
                    <span className="ins-bar-name">{x.contact}</span>
                    <span className="ins-bar-track"><span className="ins-bar-fill" style={{ width: Math.max(4, x.recent / max * 100) + '%' }} /></span>
                    <span className="ins-bar-val">{x.recent}{x.share ? ' · ' + x.share + '%' : ''}</span>
                  </div>
                )
              })}
            </div>
            )}
          </div>
        )
      )}

      {/* 业务全景 */}
      {tab === 'panorama' && (
        panorama === null ? <Thinking phases={['把散在各处的对话按事聚合…']} hint="正在拼你的业务全景" /> : (
          <div className="radar-body">
            <div className="rad-sub">不按人、按<b>事</b>看 —— 每件事/项目涉及哪些人,一眼看全</div>
            {(panorama.topics || []).length === 0 && <div className="rad-empty big">还没聚合出跨多人的项目。聊天里的公司/项目实体更丰富后,这里会长出来。</div>}
            {(panorama.topics || []).map((t, i) => (
              <div key={i} className="ins-topic">
                <div className="ins-topic-head"><span className="ins-topic-name">{t.topic}</span><span className="ins-topic-tag">{t.etype}</span><span className="ins-topic-n">{t.contact_count} 人涉及</span></div>
                <div className="ins-topic-people">{t.contacts.map((c, j) => <span key={j} className="ins-person">{c}</span>)}</div>
                {onAsk && <button className="rad-mini" onClick={() => onAsk('把「' + t.topic + '」这件事的来龙去脉、涉及的' + t.contacts.join('、') + '各自是什么角色、现在进展到哪,给我理一遍')}>理一遍这件事</button>}
              </div>
            ))}
          </div>
        )
      )}

      {/* 沟通体检 */}
      {tab === 'checkup' && (
        checkup === null ? <Thinking phases={['检查谁在等你回、你对谁变冷了…']} hint="正在做沟通体检" /> : (
          <div className="radar-body">
            <div className="rad-sub">你自己容易忽略的沟通漏洞 —— 点任意一个看聊天</div>
            {checkup.overview && (
              <div className="ins-stats">
                <div className="ins-stat"><b>{checkup.overview.analyzed}</b><span>分析了</span></div>
                <div className="ins-stat warn"><b>{checkup.overview.waiting}</b><span>对方在等你回</span></div>
                <div className="ins-stat bad"><b>{checkup.overview.cold}</b><span>你冷落了</span></div>
                <div className="ins-stat chase"><b>{checkup.overview.you_chase}</b><span>你在追</span></div>
                <div className="ins-stat warm"><b>{checkup.overview.they_chase}</b><span>TA在追你</span></div>
              </div>
            )}
            {group('对方在等你回(球在你这边)', checkup.they_wait, 'warn', (x, i) => <span key={i} className="ins-chip warn" onClick={() => onOpen && onOpen(x.doc_id)}>{x.contact} <b>{x.waiting_days}</b> 天</span>)}
            {group('你对这些人变冷了(还在联系但你退出了)', checkup.i_went_cold, 'bad', (x, i) => <span key={i} className="ins-chip bad" onClick={() => onOpen && onOpen(x.doc_id)}>{x.contact}</span>)}
            {group('你在追TA(你发得多、对方冷淡)', checkup.you_chase, 'chase', (x, i) => <span key={i} className="ins-chip chase" onClick={() => onOpen && onOpen(x.doc_id)}>{x.contact} <b>{x.me}:{x.them}</b></span>)}
            {group('TA在追你(对方发得多、你回得少)', checkup.they_chase, 'warm', (x, i) => <span key={i} className="ins-chip warm" onClick={() => onOpen && onOpen(x.doc_id)}>{x.contact} <b>{x.them}:{x.me}</b></span>)}
            {(checkup.they_wait || []).length === 0 && (checkup.i_went_cold || []).length === 0 && (checkup.you_chase || []).length === 0 && (checkup.they_chase || []).length === 0 && <div className="rad-empty big">沟通状况良好,没有明显漏掉的人。</div>}
          </div>
        )
      )}
    </div>
  )
}
