# 客户端全功能测试矩阵 · 多轮审计（下一轮出包全面复测用）

**测试原则（用户定）：** 以**空数据全新用户**从**注册登录 → 每个 tab 每个功能**走一遍。空态/引导/崩溃是重点，不用旧库掩盖新用户问题。

**测试方法：** 打包 sidecar（不是我抽的临时版，要下最新 CI 产物）+ 全新注册的空账号 + Chrome CDP 驱动前端逐 tab 点 + 抓 console/截图 + 后端端点。

---

## A. 账号流程（空数据新用户第一步，之前没测）
| 功能 | 端点/组件 | 状态 | 备注 |
|------|-----------|------|------|
| 落地页 | Landing | ⬜ | 客户端应默认登录+可切注册 |
| **手机注册** | sendCode/phoneRegister | ⬜ | 全新号注册,SMS_DEV验证码 |
| **验证码登录** | sendCode/phoneLogin | ⬜ | |
| **密码登录** | pwdLogin | ⬜ | |
| 忘记密码 | resetPassword | ⬜ | |
| 支付宝登录 | (已隐藏) | — | 用户令暂隐藏 |
| **新用户引导** | Onboard | ⬜ | 注册后的引导流程 |
| 试用/订阅墙 | Paywall: account/plans/payCreate/payQuery/orders | ⬜ | 试用倒计时+付费流程 |

## B. 问答 tab（Home/Cards/Ask）
| 功能 | 端点 | 状态 |
|------|------|------|
| 首页空态 | today(空数组) | ✅已修(补Empty) |
| 新建目标/日记卡 | createCard | ✅ |
| 卡片改状态/编辑 | cardStatus/cardEdit | ✅ |
| 卡片关联历史 | cardRelated | ⬜ |
| 删卡 | deleteCard | ⬜ |
| **真实问答** | ask(LLM) | ✅真实DeepSeek |
| 连接发现 | links/entityLinks | ✅ |
| 产出PPT/Word/Excel | generate(officecli) | ✅officecli真出文件 |
| 今日发现 | today/news | ✅ |
| 发现红点 | discoveries | ⬜ |

## C. 探索 tab（Explore/StarCloud/NodeDetail）
| 功能 | 端点 | 状态 |
|------|------|------|
| 星海图 | starmap | ✅(空态"还没星图") |
| 文档图 | graph | ✅ |
| 主题星系 | chatTopicGalaxy | ✅ |
| 搜索 | search | ⬜ |
| 节点详情 | chatNode/connections/docSummary/similar | ⬜部分 |

## D. 画像 tab（Persona）
| persona 真实生成 | ✅ |

## E. 人脉 tab（Relationships/ContactGraph/GroupGraph/RelationTimeline）
| 功能 | 端点 | 状态 |
|------|------|------|
| 关系卡列表 | relationships | ✅ |
| 关系力导图 | relGraph | ✅ |
| 关系路径 | relPath | ⬜ |
| 见面简报 | briefing | ⬜ |
| 深聊 | deepen | ⬜(LLM,空库测不了) |
| 群图谱 | groupGraph | ⬜ |
| 关系时间线 | relationTimeline | ⬜ |
| dismiss各种 | dismissLoop/dismissReach | ✅ |

## F. 雷达 tab（Radar）
| commitments/matches/favors/cooling/dormant/numberLedger | ✅全200 |
| dismissCommitment | ✅ |

## G. 洞察 tab（Insights）
| balance/panorama/checkup/portrait | ✅ |

## H. 好友 tab（Friends）
| people | ✅ |
| friend加/删 | ✅(404正确校验) |
| match/{other} | ⬜(LLM) |

## I. 冥想 tab（Life）
| lifestory/lifesong/songMake/songStatus | 🔴→✅ lifesong曾崩已修 |
| stats/getSettings | ⬜ |

## J. 文库 tab（Library/Reader/Search/Gallery）
| library/mylibrary | ✅ |
| doc详情/mediaStructure/wechatMessages | ⬜部分 |
| search | ⬜ |

## K. 入库 tab（Ingest/WechatSync）—— ★重点,两个子tab
| 功能 | 状态 | ★问题 |
|------|------|-------|
| 文档上传 | ✅真入库(EPUB/PDF) | |
| URL入库 | ✅ | |
| 文件夹上传 | ⬜ | |
| **「实时同步」子tab(微信助手)** | ✅链路(handoff消费) | 需真机开助手测 |
| **「iPhone导入历史」子tab(iOS导入)** | ✅解析链路真机验证(47G备份→38会话) | 🔴**执行者import_iphone.py不在打包助手/sidecar里,前端点了谁执行?——下轮必查** |
| 微信助手下载 | ✅本地/dl | |
| 实时同步徽章 | ✅心跳门控 | |

## L. 设置 tab（Settings）
| getSettings/saveSettings | ✅ |
| **testSettings测连通** | ✅真回DeepSeek |
| getProfile/updateProfile | ✅ |
| setPassword | ⬜ |
| setAvatar/getAvatars | ✅ |

## M. 说明 tab（Help/Guide）
| 全平台手册/图文引导 | ⬜ |

---

## ★ 下一轮审计要补的盲区（我觉得不够全的地方）
1. **账号全流程完全没测**（注册/登录/引导/支付墙）——空数据新用户的第一步
2. **iOS导入执行链路断裂嫌疑**：import_iphone.py 不在打包产物里,前端有UI但可能无执行者
3. **微信助手「实时同步」子tab**需真机开助手端到端
4. LLM类端点(deepen/match/report/briefing)空库测不到真实输出,需有数据的账号
5. **前端全tab CDP截图**要在**空数据新账号**上重跑(之前用旧库测,掩盖了空态问题)
6. 说明/引导tab完全没测
7. **多轮审计**:每轮补一类盲区,不是一次测完

## 可复用脚本
`sidecar/client_smoke_test.py`(需扩展:加账号流程 + 空账号模式 + CDP前端截图)
