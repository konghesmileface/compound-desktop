import React, { useState, useEffect } from 'react'
import { api } from './api'
import { Thinking, toast, Empty } from './ui'
import { IconRadar } from './icons'

// 雷达 · 从聊天里主动扒出:该做的事(承诺)、能赚的钱(供需撮合)、别记错的数(数字台账)
export default function Radar({ onOpen, onAsk }) {
  const [tab, setTab] = useState('commit')
  const [commit, setCommit] = useState(null)
  const [match, setMatch] = useState(null)
  const [ledger, setLedger] = useState(null)
  const [cooling, setCooling] = useState(null)
  const [favors, setFavors] = useState(null)
  const [dormant, setDormant] = useState(null)
  const [showStale, setShowStale] = useState(false)
  const [dormSort, setDormSort] = useState('recent')   // recent=近期沉默优先 / old=最久优先
  const [favSort, setFavSort] = useState('count')      // 人情:count=人情多优先 / name=按名字
  const [coolSort, setCoolSort] = useState('near')     // 降温:near=由近及远(近期变冷先) / far=由远及近(最久先)
  // 全雷达统一"删除/隐藏"(不想看/没意义的条目)——本地持久化,不删聊天/数据
  const [hidden, setHidden] = useState(() => { try { return new Set(JSON.parse(localStorage.getItem('radarHidden') || '[]')) } catch { return new Set() } })
  const hide = (k) => { setHidden((s) => { const n = new Set(s); n.add(k); try { localStorage.setItem('radarHidden', JSON.stringify([...n].slice(-800))) } catch {} return n }) }
  const shown = (k) => !hidden.has(k)

  // 清除某条承诺(已了结/不再跟进)——只标记忽略,绝不删聊天记录
  // P1-06:先落服务端成功才从本地移除;失败给提示并保留(否则下次 load 会把它"捞回来"造成删了又冒出)
  const clearItem = async (key) => {
    if (!key || !commit) return
    try {
      await api.dismissCommitment(key)
      setCommit({
        ...commit,
        mine: (commit.mine || []).filter(x => x.key !== key),
        theirs: (commit.theirs || []).filter(x => x.key !== key),
        overdue: (commit.overdue || []).filter(x => x.key !== key),
      })
    } catch { toast('清除没成功,请稍后再试', 'err') }
  }

  useEffect(() => {
    if (tab === 'commit' && commit === null) api.commitments().then(setCommit).catch(() => setCommit({ mine: [], theirs: [] }))
    if (tab === 'match' && match === null) api.matches().then(setMatch).catch(() => setMatch({ matches: [] }))
    if (tab === 'ledger' && ledger === null) api.numberLedger().then(setLedger).catch(() => setLedger({ ledgers: [] }))
    if (tab === 'cooling' && cooling === null) api.cooling().then(setCooling).catch(() => setCooling({ alerts: [] }))
    if (tab === 'favors' && favors === null) api.favors().then(setFavors).catch(() => setFavors({ items: [] }))
    if (tab === 'dormant' && dormant === null) api.dormant().then(setDormant).catch(() => setDormant({ items: [] }))
  }, [tab])

  const dueLabel = (d) => {
    if (d == null) return null
    if (d < 0) return { t: '已逾期 ' + (-d) + ' 天', c: 'overdue' }
    if (d === 0) return { t: '今天到期', c: 'today' }
    if (d <= 3) return { t: d + ' 天后', c: 'soon' }
    return { t: d + ' 天后', c: 'far' }
  }

  return (
    <div className="view radar-view">
      <div className="view-head">
        <div>
          <h1>雷达</h1>
          <p>第二大脑替你盯着聊天:该做的事、能牵线的机会、别记错的数字 —— 主动扒给你。</p>
        </div>
      </div>

      <div className="radar-tabs">
        {[['commit', '承诺雷达'], ['match', '供需撮合'], ['cooling', '降温预警'], ['favors', '人情待还'], ['dormant', '沉默线索'], ['ledger', '数字台账']].map(([k, lab]) => (
          <button key={k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}>{lab}</button>
        ))}
      </div>

      {/* 承诺雷达 */}
      {tab === 'commit' && (
        commit === null ? <Thinking phases={['扫描你和每个人的约定…', '找出谁答应了什么、什么时候…']} hint="正在建承诺雷达" /> : (
          (() => {
            const mineAll = commit.mine || [], theirsAll = commit.theirs || []
            const mine = mineAll.filter(x => !x.stale), theirs = theirsAll.filter(x => !x.stale)
            const staleMine = mineAll.filter(x => x.stale), staleTheirs = theirsAll.filter(x => x.stale)
            const staleN = staleMine.length + staleTheirs.length
            const renderItem = (c, i, isMine) => {
              const dl = dueLabel(c.days_to)
              return (
                <div key={c.key || i} className="rad-item">
                  <button className="rad-clear" title="已了结 / 不再跟进(不删聊天)" onClick={(e) => { e.stopPropagation(); clearItem(c.key) }}>✕</button>
                  <div className="rad-item-top" onClick={() => c.doc_id != null && onOpen && onOpen(c.doc_id)}>
                    <span className="rad-who">{c.contact}</span>{dl && <span className={'rad-due ' + dl.c}>{dl.t}</span>}
                  </div>
                  <div className="rad-what">{c.what}</div>
                  {isMine && c.quote && <div className="rad-quote">“{c.quote}”</div>}
                  {!isMine && onAsk && <button className="rad-mini" onClick={() => onAsk('帮我起草一句话,体面地问' + c.contact + '关于「' + c.what + '」的进展,别催得太急')}>催一下</button>}
                </div>
              )
            }
            const allEmpty = mine.length === 0 && theirs.length === 0 && staleN === 0 && !(commit.overdue || []).length
            if (allEmpty) return (
              <div className="radar-body"><Empty icon={<IconRadar />} title="还没有承诺记录" sub="导入微信聊天后,AI 会自动扒出谁答应了什么、什么时候,替你盯着该做的事" /></div>
            )
            return (
          <div className="radar-body">
            {commit.overdue && commit.overdue.length > 0 && (
              <div className="rad-alert">有 {commit.overdue.length} 件近期逾期,尽快处理</div>
            )}
            <div className="rad-cols">
              <div className="rad-col">
                <div className="rad-col-head rad-mine">我欠的事(我答应过别人) · {mine.length}</div>
                {mine.length === 0 && <div className="rad-empty">没有待办的承诺</div>}
                {mine.map((c, i) => renderItem(c, i, true))}
              </div>
              <div className="rad-col">
                <div className="rad-col-head rad-theirs">等对方的事(别人答应我的) · {theirs.length}</div>
                {theirs.length === 0 && <div className="rad-empty">没有等待中的承诺</div>}
                {theirs.map((c, i) => renderItem(c, i, false))}
              </div>
            </div>
            {staleN > 0 && (
              <div className="rad-stale-wrap">
                <button className="rad-stale-toggle" onClick={() => setShowStale(v => !v)}>
                  {showStale ? '收起' : '展开'} {staleN} 件很久以前的未了结(逾期 60 天以上)
                </button>
                {showStale && (
                  <div className="rad-cols rad-stale">
                    <div className="rad-col">{staleMine.map((c, i) => renderItem(c, i, true))}</div>
                    <div className="rad-col">{staleTheirs.map((c, i) => renderItem(c, i, false))}</div>
                  </div>
                )}
              </div>
            )}
          </div>
            )
          })()
        )
      )}

      {/* 供需撮合 */}
      {tab === 'match' && (
        match === null ? <Thinking phases={['收集谁手上有什么、谁在找什么…', '把供给和需求配对…']} hint="正在找可撮合的机会" /> : (
          <div className="radar-body">
            <div className="rad-sub">从 {match.supply_count || 0} 条供给信号 × {match.demand_count || 0} 条需求信号里,找到能牵线的机会</div>
            {(match.matches || []).length === 0 && <Empty icon={<IconRadar />} title="暂时没找到能撮合的机会" sub="聊天里出现更多「谁有 / 谁要」的信息后,这里会自动浮现可撮合的机会" />}
            {(match.matches || []).map((m, i) => ({ m, i })).filter(({ m, i }) => shown('match:' + i + ':' + m.supply_from + ':' + m.demand_from)).map(({ m, i }) => (
              <div key={i} className="rad-match">
                <button className="rad-clear" title="删除(不想看/没意义)" onClick={() => hide('match:' + i + ':' + m.supply_from + ':' + m.demand_from)}>✕</button>
                <div className="rad-match-head">
                  <span className="rad-match-conf">{m.confidence || ''}</span>
                  可撮合机会
                </div>
                <div className="rad-match-body">
                  <div className="rad-match-side"><span className="rad-match-name">{m.supply_from}</span> 有:{m.supply}</div>
                  <div className="rad-match-link">配</div>
                  <div className="rad-match-side"><span className="rad-match-name">{m.demand_from}</span> 找:{m.demand}</div>
                </div>
                <div className="rad-match-why">{m.why}</div>
                {onAsk && <button className="rad-mini" onClick={() => onAsk('我想撮合' + m.supply_from + '和' + m.demand_from + '(' + m.supply + ' 对 ' + m.demand + '),帮我想想怎么牵这个线、分别跟他俩怎么说')}>怎么牵线</button>}
              </div>
            ))}
          </div>
        )
      )}

      {/* 数字台账 */}
      {tab === 'ledger' && (
        ledger === null ? <Thinking phases={['翻出聊天里所有的报价、额度、期限…', '按人整理成台账…']} hint="正在建数字台账" /> : (
          <div className="radar-body">
            <div className="rad-sub">聊天里谈过的报价 / 额度 / 期限 / 利率等,按人整理 —— 别再翻记录、别记错数</div>
            {(ledger.ledgers || []).length === 0 && <Empty icon={<IconRadar />} title="还没有数字台账" sub="聊天里出现金额、日期、单号等结构化信息后,会自动抽取成台账" />}
            {(ledger.ledgers || []).map((l, i) => (
              <div key={i} className="rad-ledger">
                <div className="rad-ledger-head" onClick={() => l.doc_id != null && onOpen && onOpen(l.doc_id)}>{l.contact} · {l.numbers.length} 条</div>
                <table className="rad-ntable">
                  <tbody>
                    {l.numbers.map((n, j) => (
                      <tr key={j}>
                        <td className="rad-nitem">{n.item}</td>
                        <td className="rad-nval">{n.value}</td>
                        <td className="rad-ndate">{n.date || ''}</td>
                        <td className="rad-nctx">{n.context || ''}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
          </div>
        )
      )}

      {/* 降温预警 */}
      {tab === 'cooling' && (
        cooling === null ? <Thinking phases={['分析你和每个人的互动节奏…', '找出明显变冷的关系…']} hint="正在做降温预警" /> : (
          <div className="radar-body">
            <div className="rad-bar">
              <div className="rad-sub" style={{ margin: 0 }}>按你和每个人的互动节奏变化判断(不是绝对天数)—— 平时热络、突然安静的关系,该主动了</div>
              <div className="rad-sortsel">
                <button className={coolSort === 'near' ? 'on' : ''} onClick={() => setCoolSort('near')}>由近及远</button>
                <button className={coolSort === 'far' ? 'on' : ''} onClick={() => setCoolSort('far')}>由远及近</button>
              </div>
            </div>
            {(cooling.alerts || []).length === 0 && <Empty icon={<IconRadar />} title="没有降温预警" sub="目前没有明显降温的关系。导入更多聊天后,这里会提醒你哪些关系在变冷" />}
            {[...(cooling.alerts || [])].filter((a) => shown('cool:' + a.contact)).sort((a, b) => coolSort === 'near' ? ((a.last_gap || 0) - (b.last_gap || 0)) : ((b.last_gap || 0) - (a.last_gap || 0))).map((a, i) => (
              <div key={i} className="rad-item" onClick={() => a.doc_id != null && onOpen && onOpen(a.doc_id)}>
                <button className="rad-clear" title="删除(不想看/没意义,不删聊天)" onClick={(e) => { e.stopPropagation(); hide('cool:' + a.contact) }}>✕</button>
                <div className="rad-item-top"><span className="rad-who">{a.contact}</span><span className={'rad-due ' + (a.level === '严重' ? 'overdue' : 'soon')}>{a.level}</span></div>
                <div className="rad-what">{a.reason}</div>
                {onAsk && <button className="rad-mini" onClick={(e) => { e.stopPropagation(); onAsk('我和' + a.contact + '有阵子没联系了,回顾下我们聊到哪、有什么该跟进的,帮我想个自然的开场白') }}>想个开场白</button>}
              </div>
            ))}
          </div>
        )
      )}

      {/* 人情待还 */}
      {tab === 'favors' && (
        favors === null ? <Thinking phases={['翻出人情往来…', '找可借的联系由头…']} hint="正在整理人情账本" /> : (
          <div className="radar-body">
            <div className="rad-bar">
              <div className="rad-sub" style={{ margin: 0 }}>谁帮过你、你欠谁 —— 人情放久了会贬值,趁有由头还上</div>
              <div className="rad-sortsel">
                <button className={favSort === 'count' ? 'on' : ''} onClick={() => setFavSort('count')}>人情多优先</button>
                <button className={favSort === 'near' ? 'on' : ''} onClick={() => setFavSort('near')}>由近及远</button>
                <button className={favSort === 'far' ? 'on' : ''} onClick={() => setFavSort('far')}>由远及近</button>
              </div>
            </div>
            {(favors.items || []).length === 0 && <Empty icon={<IconRadar />} title="还没有人情往来" sub="聊天里出现帮忙、请客、送礼等往来后,这里会记下谁欠谁的人情" />}
            {[...(favors.items || [])].filter((f) => shown('fav:' + f.contact)).sort((a, b) => favSort === 'count' ? ((b.favors || []).length - (a.favors || []).length) : favSort === 'near' ? ((a.last_days ?? 1e9) - (b.last_days ?? 1e9)) : ((b.last_days ?? -1) - (a.last_days ?? -1))).map((f, i) => (
              <div key={i} className="rad-favor-card">
                <button className="rad-clear" title="删除(不想看/没意义,不删聊天)" onClick={() => hide('fav:' + f.contact)}>✕</button>
                <div className="rad-favor-name">{f.contact}<span className="rad-favor-n">{(f.favors || []).length} 笔人情</span>{f.last_days != null && <span className="rad-favor-days">{f.last_days} 天没联系</span>}</div>
                <div className="rad-favor-list">
                  {(f.favors || []).map((v, j) => <div key={j} className="rad-favor-li"><span className="rad-favor-dot" />{v}</div>)}
                </div>
                {(f.warm_topics || []).length > 0 && (
                  <div className="rad-favor-hook"><span className="rad-favor-hook-l">可借由头</span>{f.warm_topics.map((t, k) => <span key={k} className="rad-hook-chip">{t}</span>)}</div>
                )}
              </div>
            ))}
          </div>
        )
      )}

      {/* 沉默线索复活 */}
      {tab === 'dormant' && (
        dormant === null ? <Thinking phases={['找聊过没成、搁置的线索…', '看哪些时机可能到了…']} hint="正在复活沉默线索" /> : (
          <div className="radar-body">
            <div className="rad-bar">
              <div className="rad-sub" style={{ margin: 0 }}>曾经聊过、没成、又很久没联系的线索 —— 也许现在时机到了</div>
              <div className="rad-sortsel">
                <button className={dormSort === 'recent' ? 'on' : ''} onClick={() => setDormSort('recent')}>由近及远</button>
                <button className={dormSort === 'old' ? 'on' : ''} onClick={() => setDormSort('old')}>由远及近</button>
              </div>
            </div>
            {(dormant.items || []).length === 0 && <Empty icon={<IconRadar />} title="没有沉默线索" sub="曾经聊得火热、最近却断了联系的人,会出现在这里提醒你复活" />}
            {[...(dormant.items || [])].filter((d) => shown('dorm:' + d.contact)).sort((a, b) => dormSort === 'recent' ? (a.silent_days - b.silent_days) : (b.silent_days - a.silent_days)).map((d, i) => (
              <div key={i} className="rad-item">
                <button className="rad-clear" title="删除(不想看/没意义,不删聊天)" onClick={() => hide('dorm:' + d.contact)}>✕</button>
                <div className="rad-item-top"><span className="rad-who">{d.contact}</span><span className="rad-due far">{d.silent_days} 天没联系</span></div>
                {d.leads.map((l, j) => <div key={j} className="rad-what">· {l}</div>)}
                {onAsk && <button className="rad-mini" onClick={() => onAsk('我和' + d.contact + '之前聊过一些事没跟进,帮我回顾下、看看现在有没有由头再联系上')}>看看能不能复活</button>}
              </div>
            ))}
          </div>
        )
      )}
    </div>
  )
}
