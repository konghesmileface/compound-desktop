"""账号本人上下文(注入所有 LLM 调用,治"系统不知道用户是谁"根因B)。
★当前实例硬编码=孔贺;生产版应从用户画像/账号资料动态生成(与 graph_kg._SELF 同为待动态化项)。
"""

OWNER_NAME = "孔贺"

# 本人在聊天里的各种称呼(承诺归属、群图 is_me、卡片主客判定共用)
OWNER_SELF_NAMES = {"孔总", "孔贺", "孔", "孔生", "孔董", "我", "(我)", "（我）"}

# 一句话身份锚点,注入 system prompt,让 LLM 不再从对方聊天反推用户是谁
OWNER_PROFILE = (
    "账号本人是「孔贺」——联储证券的债券 / 银行间市场从业者,主做同业存单、利率债、"
    "债券代投 / 过券等经纪撮合业务;人脉集中在各家银行(浦发、兴业、农行、中行、宁波、广发等)"
    "金融市场部 / 同业部,以及券商同业。分析时把孔贺当作已知的固定主体,不要猜测他的身份或职业。"
)


def is_owner(name):
    """判断某个发言人名/who 是否指账号本人。"""
    n = (name or "").strip()
    if not n:
        return False
    if n.startswith("我"):
        return True
    return n in OWNER_SELF_NAMES or OWNER_NAME in n
