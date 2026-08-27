# 客户端全功能测试报告(2026-08-27)

蓝本:`unlimited-ocr/docs/TEST_REPORT_2026-08-07.md`(多用户安全+功能全域用例)。
本轮针对**打包客户端**在真机(macOS 12.7.6 / Intel / 8GB)补强并实测。

测法:把打包 sidecar 拷到可写目录,`BRAIN_DATA` 指向用户 library.db 副本(不动真库),
用从 webview localStorage 取的真实 token 打 API。可复用脚本:`sidecar/client_smoke_test.py`。

## 结论:全绿

| 测项 | 结果 | 证据 |
|------|------|------|
| **scipy→bge-m3→嵌入 端到端** | ✅ 通 | macOS12.7 上 `import sentence_transformers` OK;`page_embeddings` 0→48 真产出向量 |
| **CA→云端鉴权** | ✅ 通 | 真 token 所有鉴权端点 200(证明 cacert 打包+https 校验通) |
| **GET 端点契约(29 个)** | ✅ 全 200 json | stats/library/people/persona/today/graph/relationships/commitments/news/analysis_status/realtime/mylibrary/links/entity_links/cards/discoveries/cooling/favors/dormant/balance/panorama/checkup/starmap… |
| **微信 handoff 消费链路** | ✅ 通 | `/api/wechat/watch`→ok;注入测试消息 5s 内入库;`realtime_status` 返回 importing/hist 进度 |
| **onnxruntime(OCR)** | ✅ 1.19.2 | macОС12 兼容,selftest 加载 OK |
| **数据文件打包** | ✅ 全在 | cacert/schema_full/bge-m3权重/rapidocr×3/微信助手×3 |

**非 bug 的正常现象**:
- 星图 0 节点 = 才嵌 48/7262,需更多向量成形(按 owner 过滤);嵌够即长出。
- `/api/ask` 400「未配置 AI key」= 测试 DB 副本没带 key 的**友好报错**(非 500),端点本身正常。

## 本轮测试发现并已修的 2 个真 bug

1. **generate.py 产出文件写进包内 + import 时崩**
   `BRAIN=os.path.dirname(__file__)` → 冻结包内 `generated/`,且 import 时 `makedirs`。
   只读安装(签名/公证/DMG 挂载运行)直接崩;产出的 PPT/Word/Excel 写进包里重装即丢。
   修:`BRAIN=BRAIN_DATA`,makedirs 包 try。

2. **sidecar_main 缺 `multiprocessing.freeze_support()`**
   冻结包里库起 multiprocessing 子进程时,子进程重入冻结二进制带 `-c/-B/-S`,被 argparse
   当未知参数崩(`unrecognized arguments: -c from multiprocessing.resource_tracker`)。
   修:`__main__` 最前 `freeze_support()` + `TOKENIZERS_PARALLELISM=false`。
   (注:嵌入实测 48 向量证明当前未阻断,此为健壮性加固。)

## 真机环境注意(非 bug,产品体感)

- **8GB 内存**:bge-m3(2.1G)+ torch 加载慢,首次嵌入要等模型加载;嵌 7262 页微信历史是
  后台增量、耗时较久,`分析中%` 会缓慢爬升。属预期,不是卡死。
- 下载大包务必走 clash(隧道不篡改);直连撞 mitmdump 透明拦截会 `bad record MAC`。

## 历史(本轮之前已修,均含在最终包)

onnxruntime 1.23→1.19.2(macOS12 OCR)、cacert 打包(DeepSeek/云端 https)、scipy 1.12→1.11.4
(嵌入)、后台嵌入驱动、HF 离线、handoff 游标持久化+历史进度、心跳门控、易懂报错、下载本地化、
问答空态、隐藏支付宝、微信助手 Intel/arm64 退出真停。

最终包:commit `2ebd855`。
