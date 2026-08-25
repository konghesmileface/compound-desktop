# -*- coding: utf-8 -*-
"""
song_factory.py —— 歌曲工厂服务端闭环(2026-08-24)。
链路: 词稿(song_cache, /api/lifesong产出) → 情绪感知 → 情绪协议卡(EMOTION_ATLAS)
     → 曲风×声线(月度禁重ledger) → 驻厂精修(锚点保全+曲风韵律) → Suno成曲
     → themes/<me>_<YYYYMM>[b].mp3 + .lyrics.json (冥想页黑胶架自动上架)
门控: 本模块只认 gate 钩子(支付会话设置 song_factory.gate = fn(me, con)), 默认放行。
"""
import json
import os
import re
import sys
import threading
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ingest as I    # noqa: E402
import llm as LLM     # noqa: E402

BRAIN_DATA = os.environ.get("BRAIN_DATA", "/home/kb/brain")
THEMES_DIR = os.path.join(BRAIN_DATA, "themes")
SUNO_BASE = "https://api.302.ai/suno"
# 连通性:境内 106 连不上 302/音频CDN,经 SUNO_PROXY(spark 香港中转)出海;未设则直连(本地开发不受影响)
_SUNO_PROXY = os.environ.get("SUNO_PROXY", "")
_OPENER = (urllib.request.build_opener(urllib.request.ProxyHandler({"http": _SUNO_PROXY, "https": _SUNO_PROXY}))
           if _SUNO_PROXY else urllib.request.build_opener())

gate = None            # 付费门控钩子(另一会话接管): fn(me, con) 不通过时 raise HTTPException
JOBS = {}              # me -> {"status": queued|polishing|composing|done|error, ...}
_LOCK = threading.Lock()

# ---------------- 情绪协议 × 曲风声线(与本机 song_studio.py 同源) ----------------
VOICES = ["温柔女声", "清亮女声", "爽朗女声", "软糯女声", "阳光男声", "磁性男声", "沙哑叙事男声",
          "书卷男声", "少年", "长者", "气声女声", "慵懒男rapper", "利落女rapper", "戏腔女声", "男女对唱"]
STYLE_KEYS = ["治愈民谣", "叙事民谣", "煽情通俗", "嘻哈说唱", "轻快俏皮", "深夜氛围",
              "摇滚", "国风", "R&B抒情", "电子暖潮", "爵士慵懒", "史诗弦乐"]
BPM_BANDS = ["slow60-75", "mid80-95", "up100+"]
STYLE_PROSODY = {
    "治愈民谣": "行8-12字, 口语, 松韵, 副歌轻上扬",
    "叙事民谣": "行10-14字念白感, 允许长句, 尾韵宽松, 山丘式白话",
    "煽情通俗": "行9-12字, 副歌开阔上行, 情绪词直给但不喊",
    "嘻哈说唱": "押韵密度高(句内韵+连环韵), 行12-16字有flow律动, verse可翻倍行数, punchline收段",
    "轻快俏皮": "行6-10字短句, 跳跃节奏, 可加语气词(哒/啦), 幽默押韵",
    "深夜氛围": "行4-8字极简, 大量留白, 重复吟唱句, 气声词",
    "摇滚": "行8-12字, 副歌怒放式重复短句, 桥段安静对比",
    "国风": "意象古典(灯/月/舟/巷), 五七字句式穿插, 平仄感, 可留戏腔句",
    "R&B抒情": "行8-12字, 转音友好的开元音结尾, 慢板深情",
    "电子暖潮": "行6-10字, hook洗脑重复, 合成器空间留白",
    "爵士慵懒": "行8-14字松弛摇摆, 口语呢喃, 不规则断句",
    "史诗弦乐": "短句庄重重复, 副歌颂歌式, 少而重的词",
}
VOICE_FIT = {
    "嘻哈说唱": {"慵懒男rapper", "利落女rapper"},
    "国风": {"戏腔女声", "书卷男声", "清亮女声", "温柔女声"},
    "史诗弦乐": {"磁性男声", "爽朗女声", "男女对唱"},
    "摇滚": {"沙哑叙事男声", "爽朗女声", "阳光男声"},
}
EMOTION_ATLAS = {
    "安慰": {"词法": "先接住(承认难)→再肯定(看见TA做到的)→后陪伴(允许休息); 高潮=泪点(副歌第二遍最柔那句)",
             "styles": {"治愈民谣", "深夜氛围", "R&B抒情", "煽情通俗"}, "voices": {"温柔女声", "书卷男声", "气声女声"}, "bpm": "slow60-75"},
    "鼓励": {"词法": "看见TA的拼→为TA骄傲→轻推一把(不施压); 高潮=暖燃点(副歌上行但不嘶吼)",
             "styles": {"叙事民谣", "煽情通俗", "轻快俏皮", "R&B抒情"}, "voices": {"阳光男声", "爽朗女声", "磁性男声"}, "bpm": "mid80-95"},
    "激发": {"词法": "点火式: 祈使短句钩子+层层加码的排比+punchline收段; 高潮=燃点(bridge蓄力→末副歌爆)",
             "styles": {"摇滚", "嘻哈说唱", "史诗弦乐", "电子暖潮"}, "voices": {"沙哑叙事男声", "利落女rapper", "慵懒男rapper", "男女对唱"}, "bpm": "up100+"},
    "陪伴": {"词法": "坐在身边的口吻, 第二人称, 碎碎念白+重复安抚句; 不解决问题只在场",
             "styles": {"深夜氛围", "爵士慵懒", "治愈民谣"}, "voices": {"气声女声", "书卷男声", "温柔女声"}, "bpm": "slow60-75"},
    "庆祝": {"词法": "把这个月的具体成就唱进词里, 点名那件事; 高潮=合唱感副歌",
             "styles": {"轻快俏皮", "嘻哈说唱", "摇滚", "国风"}, "voices": {"爽朗女声", "阳光男声", "男女对唱"}, "bpm": "up100+"},
    "释怀": {"词法": "把放不下的那件事说轻(自嘲+温柔), 结尾把它放下的动作写出来; 高潮=呼气感的降落",
             "styles": {"叙事民谣", "爵士慵懒", "治愈民谣"}, "voices": {"沙哑叙事男声", "温柔女声", "长者"}, "bpm": "slow60-75"},
    "思念": {"词法": "一件旧物/一个场景当信物, 不点名的人称留白; 高潮=副歌问句",
             "styles": {"国风", "治愈民谣", "R&B抒情", "深夜氛围"}, "voices": {"戏腔女声", "温柔女声", "书卷男声"}, "bpm": "slow60-75"},
    "感恩": {"词法": "细数对方做过的小事(清单装置), 结尾第一次说出口的谢; 高潮=清单最后一件最小最重",
             "styles": {"叙事民谣", "煽情通俗", "治愈民谣"}, "voices": {"温柔女声", "少年", "男女对唱"}, "bpm": "mid80-95"},
    "告别": {"词法": "好好收尾: 回忆两幕→祝福→转身; 禁哭腔滥情, 高潮=祝福句",
             "styles": {"煽情通俗", "叙事民谣", "史诗弦乐"}, "voices": {"磁性男声", "爽朗女声"}, "bpm": "mid80-95"},
    "纪念": {"词法": "庄重白描, 名词多动词少, 留白最多; 高潮=一句最平静的事实",
             "styles": {"史诗弦乐", "深夜氛围", "国风"}, "voices": {"长者", "气声女声", "男女对唱"}, "bpm": "slow60-75"},
    "示爱": {"词法": "具体的日常瞬间当证据, 克制到最后一句才说破; 高潮=说破那句",
             "styles": {"R&B抒情", "轻快俏皮", "爵士慵懒"}, "voices": {"磁性男声", "软糯女声", "男女对唱"}, "bpm": "mid80-95"},
    "解压": {"词法": "自嘲幽默, 把糟心事唱成段子, 语气词和怪韵; 高潮=最惨那句配最欢的曲",
             "styles": {"轻快俏皮", "嘻哈说唱", "爵士慵懒"}, "voices": {"利落女rapper", "清亮女声", "慵懒男rapper"}, "bpm": "mid80-95"},
}
STYLE_EN = {
    "治愈民谣": "warm healing Chinese folk, gentle fingerstyle guitar and soft piano",
    "叙事民谣": "Chinese storytelling folk ballad, acoustic guitar, harmonica",
    "煽情通俗": "emotional Chinese pop ballad, piano and building strings",
    "嘻哈说唱": "laid-back Chinese hip-hop boom bap, warm bass, vinyl texture",
    "轻快俏皮": "playful light Chinese folk-pop, whistle, handclaps",
    "深夜氛围": "minimal late-night ambient pop, electric piano, airy space",
    "摇滚": "Chinese rock anthem, driving guitars, quiet bridge dynamics",
    "国风": "Chinese guofeng, guzheng and dizi with modern beat, poetic classical imagery",
    "R&B抒情": "soulful Chinese R&B ballad, smooth runs, warm keys",
    "电子暖潮": "warm synthwave electronic pop, dreamy pads, hooky repetition",
    "爵士慵懒": "lazy jazz lounge, brushed drums, upright bass, murmured vocal",
    "史诗弦乐": "epic cinematic orchestral pop, choir touches, solemn build",
}
VOICE_EN = {
    "温柔女声": "tender warm female vocal", "清亮女声": "clear bright female vocal",
    "爽朗女声": "hearty open female vocal", "软糯女声": "soft sweet female vocal",
    "阳光男声": "sunny young male vocal", "磁性男声": "magnetic deep male vocal",
    "沙哑叙事男声": "weathered raspy storytelling male vocal", "书卷男声": "soft bookish male vocal",
    "少年": "youthful boyish vocal", "长者": "aged wise vocal", "气声女声": "breathy female vocal",
    "慵懒男rapper": "laid-back male rapper with warm grit", "利落女rapper": "crisp agile female rapper",
    "戏腔女声": "Chinese opera-inflected female vocal accents", "男女对唱": "male and female duet, call and response",
}
BPM_EN = {"slow60-75": "68bpm slow", "mid80-95": "88bpm mid-tempo", "up100+": "104bpm upbeat"}


def style_tags(pick):
    return "%s, %s, %s" % (STYLE_EN.get(pick["style"], ""), VOICE_EN.get(pick["voice"], ""), BPM_EN.get(pick["bpm"], ""))


def atlas_pick(need, ledger):
    """情绪协议卡→在其曲风白名单内跑月度禁重(与最近3月距离最大, 曲风不连月, 组合3月禁重)。"""
    import itertools
    card = EMOTION_ATLAS.get(need) or EMOTION_ATLAS["陪伴"]
    recent = ledger[-3:]

    def dist(combo):
        st, vo = combo
        d = 0
        for r in recent:
            d += (st != r.get("style")) + (vo != r.get("voice"))
        if recent and st == recent[-1].get("style"):
            d -= 5
        if any(st == r.get("style") and vo == r.get("voice") for r in recent):
            d -= 9
        return d

    vs = (card["voices"] & set(VOICES)) or set(VOICES)
    st, vo = max(itertools.product(card["styles"], vs), key=dist)
    return {"style": st, "voice": vo, "bpm": card["bpm"], "prosody": STYLE_PROSODY.get(st, ""), "词法": card["词法"]}


# ---------------- 工艺质检 + 驻厂精修(锚点保全) ----------------
BAN_WORDS = ["坚持", "梦想", "星辰大海", "远方的诗", "破茧", "翻山越海", "奔赴山海"]
PUA_WORDS = ["你还不够", "继续加油", "不能停下", "必须坚强"]
STRUCT_REQ = ["[Intro]", "[Verse 1]", "[Chorus]", "[Verse 2]", "[Bridge]", "[Outro]"]


def craft_lint(lyrics):
    errs = []
    for tag in STRUCT_REQ:
        if tag not in lyrics:
            errs.append("缺结构段 %s" % tag)
    for ln in lyrics.splitlines():
        t = ln.strip()
        if not t or t.startswith("["):
            continue
        n = len(re.sub(r"[ ,。!?、\"'()（）—-]", "", t))
        if n > 16:
            errs.append("行过长(%d字): %s" % (n, t[:18]))
    for w in BAN_WORDS:
        if w in lyrics:
            errs.append("鸡汤禁词: " + w)
    for w in PUA_WORDS:
        if w in lyrics:
            errs.append("PUA禁词: " + w)
    if lyrics.count("[Chorus]") < 2:
        errs.append("副歌须完整出现≥2次")
    blocks = re.findall(r"\[Chorus\]\n(.+?)(?=\n\[|\Z)", lyrics, re.S)
    if len(blocks) >= 2:
        if blocks[0].strip().splitlines()[0] != blocks[1].strip().splitlines()[0]:
            errs.append("两次副歌首句(钩子)不一致")
    return errs


def _anchors(text):
    a = set(re.findall(r"\d+", text))
    a |= set(re.findall(r"[“‘\"']([^”’\"']{1,6})[”’\"']", text))
    return {x for x in a if x}


def generalize_privacy(lyrics):
    out = re.sub(r"(北京|上海|广州|深圳|杭州|成都|武汉|重庆|南京|西安|苏州|天津)", "这座城", lyrics)
    return re.sub(r"[@＠]\S+", "有人", out)


POLISH_SYS = ("你是驻厂词作(李宗盛式白话+法典约束)。收到一份从用户数据总结出的'素材稿'(可能粗糙不可唱), "
              "把它精修成完整可唱的歌词。铁律:\n"
              "1.【锚点保全】素材里的每个数字/引号词/私人意象必须原样保留(那是TA认出自己的锚, 一个不许丢不许改);\n"
              "2. 结构: [Intro]2行+[Verse 1]6-8行+[Chorus]4行+[Verse 2]6-8行+[Chorus]4行(首句与第一次一致,末行可变)+[Bridge]4行+[Outro]2行;\n"
              "3. 每行≤14字大白话; 副歌首句=钩子≤10字; 结尾=标题翻转或轻落;\n"
              "4. 禁词: 坚持/梦想/星辰大海/破茧/翻山越海; 禁PUA: 你还不够/继续加油;\n"
              "5.【歌名】起一个像真正流行歌的名字: 意象化、有美感、留白、勾情绪; 严禁职业/行业/机构/术语/单据当歌名(利率走廊/撮合者/报价单 这种行话名不行); 2-6字, 可从副歌意象或最动人一句凝练(如 把夜熬成微光/微光里的河/替两边取暖/还亮着的窗);\n"
              '只输出JSON: {"title":"意象化有美感,严禁行话/职业/术语","lyrics":"..."}')


def _llm_json(sysp, userp, temperature=0.7, max_tokens=1800):
    out = LLM.chat([{"role": "system", "content": sysp}, {"role": "user", "content": userp}],
                   temperature=temperature, max_tokens=max_tokens)
    m = re.search(r"\{.*\}", out, re.S)
    raw = m.group(0) if m else out
    try:
        return json.loads(raw, strict=False)
    except Exception:
        return json.loads(re.sub(r",\s*([}\]])", r"\1", re.sub(r"^```(?:json)?|```$", "", raw.strip()).strip()), strict=False)


def sense_need(material):
    """从词稿感知这个月最该给TA的情绪(EMOTION_ATLAS键之一)。失败=陪伴。"""
    keys = "/".join(EMOTION_ATLAS)
    try:
        out = _llm_json("从这份歌词素材判断: 这个人此刻最需要哪种情绪的歌。只输出JSON: "
                        '{"need":"%s 其中之一","state":"tired|sad|calm|happy|striving"}' % keys,
                        material[:1500], temperature=0.2, max_tokens=100)
        return (out.get("need") if out.get("need") in EMOTION_ATLAS else "陪伴"), out.get("state", "calm")
    except Exception:
        return "陪伴", "calm"


def polish(raw, need, prosody):
    """精修+确定性校验(锚点/工艺), 2次重试, 兜底=原稿泛化直出(宁朴素不空手)。"""
    orig = raw
    anchors = _anchors(raw)
    checklist = "、".join(sorted(anchors))
    for att in range(2):
        try:
            out = _llm_json(POLISH_SYS + "\nneed=%s\n【本曲风韵律要求(词必须服从)】%s\n"
                            "【锚点清单(每一个必须原样出现, 软歌也不许丢——数字就是TA的人生)】%s" % (need, prosody, checklist),
                            "素材稿:\n" + raw)
            lyr = generalize_privacy(out.get("lyrics", ""))
            missing = [a for a in anchors if a not in lyr]
            errs = craft_lint(lyr)
            if not missing and not errs:
                return {"title": out.get("title", "无题"), "lyrics": lyr, "repair": []}
            raw = raw + "\n【上版问题必须修正】" + ("丢失锚点:%s " % missing if missing else "") + ("工艺:%s" % errs[:3] if errs else "")
        except Exception as e:
            print("[song_factory] 精修失败:", str(e)[:80])
    return {"title": "无题", "lyrics": generalize_privacy(orig), "repair": ["精修未收敛, 原稿泛化兜底"]}


# ---------------- Suno(302.AI) 成曲 ----------------
def _suno_key():
    k = os.environ.get("SUNO302_KEY", "")
    if not k:
        p = os.path.join(BRAIN_DATA, "suno302_key.txt")
        if os.path.exists(p):
            k = open(p).read().strip()
    if not k:
        raise RuntimeError("缺 302 key: 设 SUNO302_KEY 或放 %s/suno302_key.txt" % BRAIN_DATA)
    return k


def _sreq(url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers={
        "Authorization": "Bearer " + _suno_key(), "Content-Type": "application/json"})
    with _OPENER.open(req, timeout=60) as r:
        return json.load(r)


def compose(lyrics, tags, title, timeout_s=600):
    """提交Suno→轮询→返回[(audio_url, duration), ...](通常2候选)。"""
    sub = _sreq(SUNO_BASE + "/submit/music",
                {"prompt": lyrics, "tags": tags, "title": title, "mv": "chirp-auk", "custom_mode": True})
    tid = sub.get("data")
    if not tid:
        raise RuntimeError("Suno提交失败: %s" % json.dumps(sub, ensure_ascii=False)[:200])
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        time.sleep(20)
        try:
            r = _sreq(SUNO_BASE + "/fetch/" + tid)
        except Exception:
            continue
        d = r.get("data") or {}
        if d.get("status") in ("SUCCESS", "complete"):
            urls = [(s.get("audio_url"), s.get("duration")) for s in (d.get("data") or []) if s.get("audio_url")]
            if urls:
                return urls
        if d.get("status") in ("FAILURE", "failed"):
            raise RuntimeError("Suno生成失败")
    raise RuntimeError("Suno超时(%ds)" % timeout_s)


def _download(url, dst):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    for _ in range(3):
        try:
            with _OPENER.open(req, timeout=120) as r, open(dst, "wb") as f:
                f.write(r.read())
            if os.path.getsize(dst) > 300000:
                return True
        except Exception as e:
            print("[song_factory] 下载重试:", str(e)[:60])
            time.sleep(5)
    return False


# ---------------- 月度账本 + 主流程 ----------------
def _ledger(con, me):
    con.execute("CREATE TABLE IF NOT EXISTS song_ledger (username TEXT, month TEXT, style TEXT, voice TEXT, "
                "bpm TEXT, need TEXT, title TEXT, PRIMARY KEY(username, month))")
    rows = con.execute("SELECT month,style,voice,bpm,need,title FROM song_ledger WHERE username=? ORDER BY month", (me,)).fetchall()
    return [dict(zip(("month", "style", "voice", "bpm", "need", "title"), r)) for r in rows]


def make_song(me, force=False):
    """全链出歌(阻塞数分钟, 应由 start_make 起线程跑)。"""
    ym = time.strftime("%Y%m")
    con = I.db_connect(I.DEFAULT_DB)
    try:
        led = _ledger(con, me)
        if not force and any(r["month"] == ym for r in led):
            JOBS[me] = {"status": "done", "note": "本月已出歌"}
            return
        row = con.execute("SELECT data FROM song_cache WHERE username=?", (me,)).fetchone()
        if not row:
            JOBS[me] = {"status": "error", "note": "先生成词稿(/api/lifesong)"}
            return
        spec = json.loads(row[0])
        material = spec.get("lyrics") or ""
        JOBS[me] = {"status": "polishing"}
        need, state = sense_need(material)
        pick = atlas_pick(need, led)
        song = polish(material, need, pick["prosody"] + " | 词法: " + pick["词法"])
        title = song["title"] if song["title"] != "无题" else (spec.get("title") or "我的主题曲")
        tags = style_tags(pick)
        JOBS[me] = {"status": "composing", "title": title, "need": need, "pick": {k: pick[k] for k in ("style", "voice", "bpm")}}
        urls = compose(song["lyrics"], tags, title)
        os.makedirs(THEMES_DIR, exist_ok=True)
        saved = []
        for i, (u, _dur) in enumerate(urls[:1]):   # 每月只保留1个候选(黑胶架一月一首,干净)
            fp = os.path.join(THEMES_DIR, "%s_%s%s.mp3" % (me, ym, "" if i == 0 else "b"))
            if _download(u, fp):
                json.dump({"title": title, "genre": pick["style"], "style": tags, "lyrics": song["lyrics"],
                           "need": need, "voice": pick["voice"], "date": time.strftime("%Y-%m")},
                          open(os.path.splitext(fp)[0] + ".lyrics.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
                saved.append(os.path.basename(fp))
        if not saved:
            JOBS[me] = {"status": "error", "note": "音频下载失败"}
            return
        con.execute("INSERT OR REPLACE INTO song_ledger(username,month,style,voice,bpm,need,title) VALUES(?,?,?,?,?,?,?)",
                    (me, ym, pick["style"], pick["voice"], pick["bpm"], need, title))
        con.commit()
        JOBS[me] = {"status": "done", "title": title, "need": need, "files": saved, "repair": song["repair"]}
    except Exception as e:
        JOBS[me] = {"status": "error", "note": str(e)[:200]}
    finally:
        con.close()


def start_make(me, force=False):
    """异步入口(app.py 调用): 起后台线程, 立即返回状态; 冥想页照常轮询 mylibrary 即见新歌。"""
    with _LOCK:
        j = JOBS.get(me) or {}
        if j.get("status") in ("polishing", "composing"):
            return {"started": False, **j}
        JOBS[me] = {"status": "queued"}
    threading.Thread(target=make_song, args=(me, force), daemon=True).start()
    return {"started": True, "status": "queued"}


def status(me):
    return JOBS.get(me) or {"status": "idle"}
