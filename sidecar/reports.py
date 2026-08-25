# reports.py — 按需总结 + 群/聊天→输出文档(营销复盘/周报/会议纪要)。可选时间段。
import re
import llm as LLM

# mode -> (标题, system提示, 是否用pro)
_R = {
    "summary": ("聊天总结", (
        "你是用户的第二大脑。把用户与「%s」的这段微信聊天,总结成一份**可下钻**的摘要。"
        "要点必须来自原文、尽量标注日期,不编造。只输出 Markdown:\n"
        "## 聊了什么(按话题,每条带日期)\n## 关键信息 / 数字(报价/额度/时间/地点/联系方式等)\n"
        "## 待你回应 / 未了结\n## 待办\n最后用一行『**一句话:**…』收尾。"), False),
    "marketing": ("营销分析报告", (
        "你是资深营销/客户运营分析师。基于用户与「%s」(客户或客户群)的聊天,产出一份**营销分析报告**。"
        "事实来自原文、带日期,不编造。只输出 Markdown:\n"
        "## 客户画像与关注点\n## 提出的异议 / 顾虑\n## 购买 / 合作信号\n## 竞品或对比提及\n"
        "## 成交线索与机会\n## 建议下一步动作(具体、可执行)"), True),
    "weekly": ("周报", (
        "你是用户的第二大脑。基于这段时间用户与「%s」的聊天,产出一份**周报式进展摘要**。"
        "带日期、来自原文。只输出 Markdown:\n## 本期进展\n## 推进的事 / 达成\n## 卡点 / 风险\n## 下一步计划"), True),
    "meeting": ("会议纪要", (
        "你是会议纪要助手。把用户与「%s」的这段群聊 / 讨论整理成**会议纪要**。来自原文、带日期。"
        "只输出 Markdown:\n## 讨论议题\n## 结论 / 决议\n## 待办事项(谁负责 · 何时前)\n## 遗留问题"), True),
}


def _filter_range(text, since, until):
    """按日期过滤聊天行(行首形如 [YYYY-MM-DD ...]);续行(无日期)跟随保留。"""
    if not since and not until:
        return text
    out = []
    for ln in (text or "").split("\n"):
        m = re.match(r"\[(\d{4}-\d{2}-\d{2})", ln)
        if not m:
            out.append(ln); continue
        d = m.group(1)
        if since and d < since:
            continue
        if until and d > until:
            continue
        out.append(ln)
    return "\n".join(out)


def build_report(contact, chat_text, mode="summary", since="", until=""):
    title, sysp, use_pro = _R.get(mode, _R["summary"])
    text = _filter_range(chat_text or "", since, until)
    if not text.strip():
        return {"title": title, "mode": mode, "markdown": "这段时间没有聊天记录。"}
    if len(text) > 18000:   # 控时长:取首尾(重点多在近期)
        text = text[:3000] + "\n…(中间略)…\n" + text[-15000:]
    model = None if use_pro else LLM.fast_model()   # 报告类用pro质量;总结用flash求快
    try:
        out = LLM.chat([{"role": "system", "content": sysp % contact},
                        {"role": "user", "content": text}],
                       temperature=0.3, max_tokens=3200, model=model)
    except Exception as e:
        return {"title": title, "mode": mode, "markdown": "生成失败,请重试(%s)" % e}
    return {"title": title, "mode": mode, "markdown": (out or "").strip()}
