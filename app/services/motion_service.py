import asyncio
from copy import deepcopy
import logging
import re
import shutil
from pathlib import Path
from typing import Any

from app.auth.security import utcnow_ms
from app.db.session import get_db_session
from app.services.analysis_ai_service import AnalysisAIService
from app.services.asset_service import AssetService
from app.services.job_service import JobService
from app.services.project_service import ProjectService
from app.services.system_settings_service import SystemSettingsService
from app.workflows.motion_extraction import MOTION_EXTRACTION_STEPS

logger = logging.getLogger(__name__)

MOTION_KEYWORDS = {
    # --- Original 12 dramatic actions ---
    "walk_in": [
        "走进", "走入", "步入", "进来", "进入", "进门", "进屋", "迈入", "迈步进", "闯入",
        "现身", "出场", "迎面走来", "walk in", "walk into", "come in", "enter", "stride",
    ],
    "push_door": [
        "推门", "推开门", "推开房门", "拉开门", "开门", "开房门", "打开门",
        "push door", "open door",
    ],
    "turn_back": [
        "回头", "回身", "回眸", "转身", "转头", "扭头", "回过头", "转过头",
        "look back", "turn back",
    ],
    "approach": [
        "靠近", "走向", "走近", "接近", "逼近", "上前", "来到面前", "逼到面前",
        "approach", "walk toward", "close in",
    ],
    "stare": [
        "凝视", "注视", "盯", "盯着", "看向", "望向", "对视", "抬眼", "抬眸",
        "stare", "gaze",
    ],
    "sit_down": ["坐下", "落座", "坐回", "跌坐", "瘫坐", "sit down"],
    "stand_up": ["站起", "起身", "起立", "猛地站起", "站定", "stand up"],
    "slap": ["扇", "打耳光", "甩巴掌", "slap"],
    "embrace": ["拥抱", "抱住", "抱紧", "搂住", "embrace", "hug"],
    "collapse": ["倒下", "摔倒", "瘫倒", "崩溃", "跌倒", "collapse"],
    "throw": ["扔", "摔", "砸", "甩出", "丢下", "throw", "slam"],
    "kneel": ["跪", "跪下", "跪倒", "kneel"],
    # --- Head / face ---
    "nod": ["点头", "点了点头", "微微点头", "nod", "nodding"],
    "shake_head": ["摇头", "摇了摇头", "shake head", "shaking head"],
    "smile": ["微笑", "笑了", "笑着", "露出笑容", "嘴角上扬", "smile", "grin"],
    "cry": ["哭", "流泪", "掉眼泪", "泣不成声", "抹泪", "cry", "weep", "tear"],
    "frown": ["皱眉", "蹙眉", "眉头紧锁", "frown"],
    "laugh": ["大笑", "哈哈笑", "笑出声", "狂笑", "laugh", "burst out laughing"],
    # --- Hand / arm ---
    "wave": ["挥手", "招手", "摆手", "手势", "wave", "waving"],
    "point": ["指", "指向", "指着", "伸手指", "point", "pointing"],
    "clap": ["鼓掌", "拍手", "掌声", "clap", "applause"],
    "reach_out": ["伸手", "伸出手", "递出", "递过去", "reach out", "hand over"],
    "salute": ["敬礼", "行礼", "致敬", "salute"],
    "thumbs_up": ["竖起大拇指", "点赞", "比赞", "thumbs up"],
    "pick_up": ["拿起", "拾起", "捡起", "提起", "pick up", "grab"],
    "put_down": ["放下", "放在", "搁下", "put down", "set down"],
    # --- Whole body ---
    "run": ["跑", "奔跑", "狂奔", "冲过去", "飞奔", "run", "sprint", "dash"],
    "jump": ["跳", "跳起", "蹦", "跃起", "jump", "leap"],
    "dance": ["跳舞", "舞蹈", "热舞", "扭动", "舞步", "dance", "dancing"],
    "spin": ["旋转", "转圈", "打转", "转动", "spin", "twirl"],
    "lean": ["靠", "倚靠", "依偎", "lean", "lean against"],
    "stretch": ["伸展", "伸懒腰", "舒展", "stretch"],
    "crouch": ["蹲下", "蹲", "蹲着", "半蹲", "crouch", "squat"],
    "crawl": ["爬", "爬行", "匍匐", "crawl"],
    "walk": ["走路", "行走", "散步", "踱步", "walk", "walking", "stroll"],
    # --- Social ---
    "handshake": ["握手", "handshake", "shake hands"],
    "bow": ["鞠躬", "弯腰行礼", "bow", "bowing"],
    "cheer": ["欢呼", "庆祝", "振臂", "cheer", "celebrate"],
    "toast": ["碰杯", "举杯", "干杯", "toast", "cheers"],
    "high_five": ["击掌", "high five"],
    # --- Daily ---
    "drink": ["喝水", "喝", "饮", "端杯", "drink", "sip"],
    "eat": ["吃", "进食", "咀嚼", "夹菜", "eat", "eating"],
    "phone_call": ["打电话", "接电话", "挂电话", "通话", "phone call", "calling"],
    "use_phone": ["玩手机", "看手机", "刷手机", "滑动手机", "use phone", "scroll phone"],
    "type_keyboard": ["打字", "敲键盘", "type", "typing"],
    "write": ["写字", "写", "书写", "签字", "write", "writing"],
    "drive": ["开车", "驾驶", "drive", "driving"],
    "photograph": ["拍照", "摄影", "自拍", "photograph", "take photo", "selfie"],
    "makeup": ["化妆", "涂口红", "补妆", "makeup"],
    # --- Combat / sport ---
    "kick": ["踢", "踢球", "飞踢", "kick"],
    "punch": ["打拳", "挥拳", "出拳", "一拳", "punch", "fist"],
    "dodge": ["躲闪", "闪避", "闪开", "dodge"],
    "block": ["挡", "阻挡", "拦住", "格挡", "block"],
    "push": ["推", "推开", "推搡", "push", "shove"],
    "pull": ["拉", "拽", "拉住", "拉过来", "pull", "drag"],
    "grab": ["抓", "抓住", "攥住", "握住", "grab", "grip", "seize"],
    # --- Expression / emotion ---
    "sigh": ["叹气", "叹了口气", "长叹", "sigh"],
    "scream": ["尖叫", "大叫", "呐喊", "吼", "scream", "shout", "yell"],
    "whisper": ["低语", "耳语", "轻声说", "whisper", "murmur"],
    "shrug": ["耸肩", "摊手", "shrug"],
    "cover_face": ["捂脸", "遮脸", "掩面", "cover face"],
    "wipe_tears": ["擦泪", "擦眼泪", "抹眼泪", "wipe tears"],
    # --- Industrial / product showcase ---
    "team_greeting": [
        "欢迎来访", "欢迎参观", "欢迎来到工厂", "团队欢迎", "门口欢迎", "工厂欢迎",
        "factory welcome", "welcome to our factory", "team greeting",
    ],
    "operate_machine": [
        "操作设备", "操作机器", "操作控制面板", "控制面板", "监控仪表", "调试机器", "设备操作",
        "operate machine", "machine operation", "control panel", "monitor panel",
    ],
    "carry_goods": [
        "搬运", "搬货", "搬袋", "装卸", "抬运", "运货", "搬包装袋",
        "carry goods", "carry bags", "load goods", "move bags",
    ],
    "display_product": [
        "展示产品", "展示细节", "产品展示", "产品特写", "特写展示", "样品展示", "颗粒特写",
        "展示塑料颗粒", "showcase product", "product showcase", "display product", "product detail",
    ],
    "inspect_product": [
        "检查产品", "查看产品", "检验产品", "检视颗粒", "查看颗粒", "产品检测",
        "inspect product", "check product", "quality inspection",
    ],
    "material_flow": [
        "传送带", "物料流动", "颗粒流动", "下料", "出料", "流水线流动",
        "material flow", "pellets flowing", "conveyor belt", "production flow",
    ],
    "pour_material": [
        "倒料", "倾倒", "倒入", "投料", "灌装", "下料口倒入",
        "pour material", "pour pellets", "feed material",
    ],
    "package_product": [
        "包装产品", "封装", "打包", "装袋", "封袋", "包装塑料颗粒",
        "package product", "bagging", "packaging",
    ],
}

MOTION_REGEX_PATTERNS = {
    "walk_in": (
        r"(迈步|快步|缓步|径直)?(走|步|迈).{0,4}(进|入)",
        r"(进|入).{0,3}(门|屋|房|办公室|房间)",
    ),
    "push_door": (
        r"(推开|拉开|打开).{0,3}门",
        r"开.{0,2}门.{0,4}(进|入|进来)",
    ),
    "turn_back": (
        r"(停|顿|驻足).{0,4}(后)?(回头|扭头|转头|回眸|转身)",
        r"(回头|扭头|转头|回眸|转过头|转过身)",
    ),
    "approach": (
        r"(缓步|快步|一步步|径直|慢慢)?(走到|走向|走近|来到|上前到).{0,6}(面前|身边)",
        r"(向|朝).{0,6}(走去|靠近|逼近)",
        r"(缓缓|慢慢|一步步)?靠近",
    ),
    "stare": (
        r"(抬眼|抬眸|看向|望向|盯着?|凝视|对视)",
        r"(目光|眼神).{0,4}(落在|看向|扫向)",
    ),
    "sit_down": (r"(坐下|坐回|落座|跌坐|瘫坐)",),
    "stand_up": (r"(站起|起身|猛地站起|站定)",),
    "slap": (r"(扇了?.{0,3}一?巴掌|打了?.{0,3}一?巴掌|打耳光)",),
    "embrace": (
        r"(扑进|冲进).{0,4}(怀里|怀中)",
        r"(拥抱|抱住|抱紧|搂住)",
    ),
    "collapse": (r"(倒下|瘫倒|跌倒|崩溃跪倒|瘫坐在地)",),
    "throw": (r"(扔出|摔下|砸向|甩出)",),
    "kneel": (r"(跪下|跪倒|双膝跪地)",),
    # --- New categories ---
    "nod": (r"(点了?点头|微微点头|频频点头)",),
    "shake_head": (r"(摇了?摇头|直摇头|不住地摇头)",),
    "smile": (r"(微微一笑|嘴角.{0,2}(上扬|上翘)|露出.{0,3}笑容)",),
    "cry": (r"(流下.{0,3}(泪|眼泪)|泪流满面|哭.{0,2}(出|了|起))",),
    "laugh": (r"(哈哈|大笑|笑出声|放声大笑)",),
    "wave": (r"(挥了?.{0,2}手|摆了?.{0,2}手|朝.{0,4}招手)",),
    "clap": (r"(鼓起?.{0,2}掌|拍了?.{0,2}手)",),
    "reach_out": (r"(伸出?.{0,2}手|递.{0,3}(过去|过来|出))",),
    "run": (r"(飞奔|狂奔|冲.{0,3}(过去|过来|出去|出来)|跑.{0,3}(过去|过来|起来))",),
    "jump": (r"(跳.{0,2}(起|了|上)|蹦.{0,2}(起|了)|一跃而起)",),
    "dance": (r"(跳起?.{0,2}舞|翩翩起舞|随.{0,3}(音乐|节奏).{0,3}(跳|舞|扭))",),
    "crouch": (r"(蹲.{0,2}(下|了|着)|半蹲.{0,2}(着|下))",),
    "push": (r"(推.{0,2}(开|倒|走|了)|推搡)",),
    "pull": (r"(拉.{0,2}(住|过|着)|拽.{0,2}(住|过|着))",),
    "grab": (r"(抓.{0,2}(住|着|起)|攥.{0,2}(住|着)|一把抓)",),
    "drink": (r"(喝了?.{0,2}(水|酒|茶|咖啡)|端起?.{0,2}(杯|酒))",),
    "phone_call": (r"(打.{0,2}电话|接.{0,2}电话|挂.{0,2}电话|拿起?.{0,2}(手机|电话))",),
    "scream": (r"(尖叫|大叫|吼.{0,2}(道|了|出)|一声(吼|叫))",),
    "kick": (r"(踢.{0,2}(了|出|向|到)|飞踢|一脚)",),
    "punch": (r"(挥.{0,2}拳|出.{0,2}拳|一拳.{0,2}(打|击|砸))",),
    "team_greeting": (
        r"(欢迎.{0,6}(来访|参观|来到)|工厂团队.{0,6}(欢迎|挥手))",
        r"(smil\w*|微笑).{0,4}(wave|挥手).{0,6}(factory|工厂|团队)",
    ),
    "operate_machine": (
        r"(操作|调试|监控).{0,6}(设备|机器|机床|控制面板|仪表)",
        r"(machine|panel).{0,8}(operation|operate|control)",
    ),
    "carry_goods": (
        r"(搬运|装卸|抬运).{0,6}(货物|包装袋|袋子|原料|产品)",
        r"(carry|load|move).{0,8}(bags|goods|materials)",
    ),
    "display_product": (
        r"(展示|特写展示|产品展示).{0,6}(产品|颗粒|样品|细节)",
        r"(showcase|display).{0,8}(product|detail|pellets)",
    ),
    "inspect_product": (
        r"(检查|检验|查看|检视).{0,6}(产品|颗粒|样品|质量)",
        r"(inspect|check).{0,8}(product|quality|pellets)",
    ),
    "material_flow": (
        r"(传送带|流水线).{0,6}(流动|输送|运行)",
        r"(pellets|materials).{0,8}(flow|moving)",
    ),
    "pour_material": (
        r"(倒料|倾倒|倒入|投料).{0,6}(颗粒|原料|物料)",
        r"(pour|feed).{0,8}(material|pellets)",
    ),
    "package_product": (
        r"(打包|装袋|封袋|包装).{0,6}(产品|颗粒|原料)",
        r"(packing|bagging|package).{0,8}(product|pellets|materials)",
    ),
}

GENERIC_CANDIDATE_PHRASES = (
    "主体展示",
    "动作推进",
    "卖点信息",
    "节奏保持连续",
    "延续叙事",
    "卖点表达",
    "收束式镜头",
    "信息闭环",
    "行动召唤",
    "主体与细节补充",
    "开场引入镜头",
    "结尾收束镜头",
    "卖点强化镜头",
    "展示镜头",
)

FILTER_REASON_LABELS = {
    "duration_too_short": "时长过短",
    "duration_too_long": "时长过长",
    "no_motion_signal": "未识别到动作信号",
    "signal_below_threshold": "信号分不足",
}

MIN_MOTION_DURATION_MS = 800
MAX_MOTION_DURATION_MS = 15000

ACTION_LABEL_MAPPING = {
    "walk_in": "walk_in",
    "push_door": "push_door_enter",
    "turn_back": "pause_and_turn",
    "approach": "slow_approach",
    "stare": "stand_and_stare",
    "sit_down": "sit_down_strongly",
    "stand_up": "look_down_then_up",
    "slap": "slap",
    "embrace": "embrace",
    "collapse": "collapse",
    "throw": "throw_object",
    "kneel": "kneel_down",
    # New
    "nod": "nod",
    "shake_head": "shake_head",
    "smile": "smile",
    "cry": "cry",
    "frown": "frown",
    "laugh": "laugh",
    "wave": "wave",
    "point": "point",
    "clap": "clap",
    "reach_out": "reach_out",
    "salute": "salute",
    "thumbs_up": "thumbs_up",
    "pick_up": "pick_up",
    "put_down": "put_down",
    "run": "run",
    "jump": "jump",
    "dance": "dance",
    "spin": "spin",
    "lean": "lean",
    "stretch": "stretch",
    "crouch": "crouch",
    "crawl": "crawl",
    "walk": "walk",
    "handshake": "handshake",
    "bow": "bow",
    "cheer": "cheer",
    "toast": "toast",
    "high_five": "high_five",
    "drink": "drink",
    "eat": "eat",
    "phone_call": "phone_call",
    "use_phone": "use_phone",
    "type_keyboard": "type_keyboard",
    "write": "write",
    "drive": "drive",
    "photograph": "photograph",
    "makeup": "makeup",
    "kick": "kick",
    "punch": "punch",
    "dodge": "dodge",
    "block": "block",
    "push": "push",
    "pull": "pull",
    "grab": "grab",
    "sigh": "sigh",
    "scream": "scream",
    "whisper": "whisper",
    "shrug": "shrug",
    "cover_face": "cover_face",
    "wipe_tears": "wipe_tears",
    "team_greeting": "team_greeting",
    "operate_machine": "operate_machine",
    "carry_goods": "carry_goods",
    "display_product": "display_product",
    "inspect_product": "inspect_product",
    "material_flow": "material_flow",
    "pour_material": "pour_material",
    "package_product": "package_product",
}

ENTRANCE_STYLE_VALUES = {
    "door_entry",
    "corridor_entry",
    "elevator_entry",
    "back_view_entry",
    "camera_follow_entry",
    "sudden_closeup_entry",
    "stair_descent_entry",
    "car_exit_entry",
    "silhouette_entry",
    "crowd_part_entry",
    "welcome_entrance",
    "workshop_intro",
    "product_closeup_entry",
}

ENTRANCE_STYLE_ALIASES = {
    "welcome_entrance": "welcome_entrance",
    "welcomeentrance": "welcome_entrance",
    "welcome_entry": "welcome_entrance",
    "workshop_intro": "workshop_intro",
    "factory_intro": "workshop_intro",
    "product_closeup_entry": "product_closeup_entry",
    "product_closeup": "product_closeup_entry",
}

CAMERA_MOTION_VALUES = {
    "static",
    "pan",
    "tilt",
    "tracking",
    "push_in",
    "pull_out",
    "zoom_in",
    "zoom_out",
    "handheld",
    "mixed",
}

CAMERA_MOTION_ALIASES = {
    "wide_shot": "wide",
    "medium_shot": "medium",
    "full_shot": "full",
    "close_shot": "close_up",
    "close_up_shot": "close_up",
    "extreme_close_up_shot": "extreme_close_up",
    "tracking_shot": "tracking",
    "push_in_shot": "push_in",
    "pull_out_shot": "pull_out",
}

CAMERA_SHOT_VALUES = {
    "wide",
    "full",
    "medium",
    "medium_close",
    "close_up",
    "extreme_close_up",
    "mixed",
}

SCENE_VALUE_ALIASES = {
    "factory_entrance": "factory_entrance",
    "factory_entry": "factory_entrance",
    "factory_gate": "factory_entrance",
    "factory_workshop": "factory_workshop",
    "workshop": "factory_workshop",
    "production_line": "production_line",
    "warehouse": "warehouse",
    "machine_station": "machine_station",
    "product_closeup": "product_closeup",
    "product_detail": "product_closeup",
    "factory_exterior": "factory_exterior",
    "loading_area": "loading_area",
}

EMOTION_VALUE_ALIASES = {
    "friendly": "friendly_welcome",
    "welcome": "friendly_welcome",
    "warm_welcome": "friendly_welcome",
    "professional": "professional_focus",
    "focused": "professional_focus",
    "focus": "professional_focus",
    "confident": "product_confidence",
    "confidence": "product_confidence",
    "proud": "team_pride",
}

TEMPERAMENT_VALUE_ALIASES = {
    "warm": "warm_hospitable",
    "friendly": "warm_hospitable",
    "hospitable": "warm_hospitable",
    "professional": "skilled_professional",
    "skilled": "skilled_professional",
    "reliable": "industrial_reliable",
    "industrial": "industrial_reliable",
    "united": "team_unified",
    "team_united": "team_unified",
}

SCENE_HINTS = {
    "office": ["办公室", "office", "工位", "会议室"],
    "corridor": ["走廊", "corridor", "过道"],
    "meeting_room": ["会议室", "meeting room"],
    "villa": ["别墅", "villa"],
    "hospital": ["医院", "hospital"],
    "street_night": ["街头", "street", "夜", "night"],
    "elevator": ["电梯", "elevator"],
    "rooftop": ["楼顶", "roof", "rooftop"],
    "bar_club": ["酒吧", "bar", "club"],
    "parking_lot": ["停车场", "parking"],
    "court_room": ["法庭", "court"],
    "banquet_hall": ["宴会厅", "banquet"],
    "bedroom": ["卧室", "bedroom"],
    "car_interior": ["车内", "车里", "car"],
    "rain_outdoor": ["雨", "rain"],
    "factory_entrance": ["工厂门口", "厂门口", "入口处", "factory entrance", "厂区入口"],
    "factory_workshop": ["工厂车间", "车间", "workshop", "厂房内部"],
    "production_line": ["生产线", "流水线", "传送带", "production line", "conveyor"],
    "warehouse": ["仓库", "warehouse", "货架区", "储存区"],
    "machine_station": ["设备前", "机台前", "控制面板", "machine station", "机床旁"],
    "product_closeup": ["产品特写", "颗粒特写", "样品特写", "product closeup", "detail shot"],
    "factory_exterior": ["工厂外景", "厂区外景", "factory exterior", "厂房外部"],
    "loading_area": ["装卸区", "装货区", "loading area", "卸货区"],
}

EMOTION_HINTS = {
    "anger": ["生气", "愤怒", "怒", "aggressive", "angry"],
    "pressure": ["压迫", "紧张", "逼迫", "pressure"],
    "indifference": ["冷淡", "冷漠", "indifference"],
    "sadness": ["难过", "悲伤", "sad", "哭"],
    "restraint": ["克制", "隐忍", "restraint"],
    "desperation": ["绝望", "崩溃", "desperate"],
    "contempt": ["轻蔑", "不屑", "contempt"],
    "shock": ["震惊", "惊讶", "shock"],
    "relief": ["松了口气", "释然", "relief"],
    "jealousy": ["嫉妒", "jealous"],
    "determination": ["坚定", "果断", "determination"],
    "friendly_welcome": ["欢迎", "热情接待", "微笑欢迎", "friendly", "welcome"],
    "professional_focus": ["专注", "熟练", "认真操作", "professional", "focused"],
    "product_confidence": ["品质自信", "质量可靠", "信心展示", "confident product"],
    "team_pride": ["团队形象", "团队自豪", "整齐形象", "team pride"],
}

TEMPERAMENT_HINTS = {
    "cold_dominant": ["冷", "强势", "压迫"],
    "gentle_but_strong": ["温柔", "克制", "坚定"],
    "broken_fragile": ["脆弱", "崩溃", "难过"],
    "scheming": ["算计", "心机"],
    "noble_calm": ["高贵", "冷静", "从容"],
    "aggressive": ["攻击", "愤怒", "冲上前"],
    "playful_confident": ["自信", "俏皮"],
    "silent_power": ["沉默", "压迫感", "无声"],
    "desperate_dignity": ["绝望", "体面"],
    "warm_hospitable": ["热情接待", "欢迎", "亲和", "hospitality"],
    "skilled_professional": ["专业", "熟练", "规范操作", "professional"],
    "industrial_reliable": ["可靠", "稳定生产", "工厂实力", "reliable"],
    "team_unified": ["团队整齐", "团队协作", "统一形象", "unified team"],
}


class MotionService:
    def __init__(self) -> None:
        self._project_service = ProjectService()
        self._asset_service = AssetService()
        self._job_service = JobService()
        self._analysis_ai_service = AnalysisAIService()
        self._settings_service = SystemSettingsService()

    def _load_motion_settings(self) -> dict[str, Any]:
        """Load motion_extraction settings from system settings with safe defaults."""
        try:
            settings = self._settings_service.get_settings()
            normalized = self._settings_service._normalize_motion_extraction_settings(
                settings.get("motion_extraction") or {},
            )
        except Exception:
            logger.warning("Failed to load motion_extraction settings, using hardcoded defaults.", exc_info=True)
            normalized = self._settings_service._normalize_motion_extraction_settings({})

        if normalized["max_duration_ms"] < normalized["min_duration_ms"]:
            normalized["max_duration_ms"] = normalized["min_duration_ms"]
        return normalized

    async def run_job(
        self,
        *,
        job_id: str,
        project_id: int,
        owner_user_id: str | None = None,
        extraction_hint: str | None = None,
    ) -> dict[str, Any]:
        project = self._project_service._get_project_for_execution(project_id=project_id)
        if project is None:
            raise ValueError("目标项目不存在，无法执行动作提取。")

        normalized_hint = str(extraction_hint or "").strip()
        result = {
            "project_id": project_id,
            "source_video_asset_id": project.get("source_asset_id"),
            "candidate_count": 0,
            "tagged_count": 0,
            "saved_count": 0,
            "asset_ids": [],
            "items": [],
            "filtered_items": [],
            "filtered_summary": {},
            "coarse_filter_mode": None,
            "extraction_hint": normalized_hint,
            "steps": [
                {
                    "step_key": definition.step_key,
                    "title": definition.title,
                    "detail": definition.description,
                    "status": "pending",
                    "error_detail": None,
                }
                for definition in MOTION_EXTRACTION_STEPS
            ],
        }
        started_at = utcnow_ms()
        self._job_service.update_job_status(
            job_id=job_id,
            status="running",
            progress=1,
            result=result,
            started_at=started_at,
        )

        motion_settings = self._load_motion_settings()
        context: dict[str, Any] = {
            "_motion_settings": deepcopy(motion_settings),
            "_extraction_hint": normalized_hint,
            "_hint_labels": self._extract_hint_labels(normalized_hint),
        }
        step_handlers = {
            "validate_analysis_data": self.step_validate_analysis,
            "coarse_filter_shots": self.step_coarse_filter,
            "tag_candidates": self.step_tag_candidates,
            "generate_thumbnails": self.step_generate_thumbnails,
            "save_motion_assets": self.step_save_assets,
            "finish": self.step_finish,
        }

        try:
            for index, definition in enumerate(MOTION_EXTRACTION_STEPS, start=1):
                self._set_step_state(
                    result=result,
                    step_key=definition.step_key,
                    status="running",
                    detail=definition.description,
                )
                self._job_service.update_job_status(
                    job_id=job_id,
                    status="running",
                    progress=max(1, int((index - 1) * 100 / len(MOTION_EXTRACTION_STEPS))),
                    result=result,
                )

                step_result = await step_handlers[definition.step_key](
                    project=project,
                    context=context,
                    job_id=job_id,
                    owner_user_id=owner_user_id,
                )
                context[definition.step_key] = step_result
                for field_key in (
                    "source_video_asset_id",
                    "candidate_count",
                    "tagged_count",
                    "saved_count",
                    "asset_ids",
                    "items",
                    "filtered_items",
                    "filtered_summary",
                    "coarse_filter_mode",
                ):
                    if field_key in step_result:
                        result[field_key] = step_result[field_key]
                self._set_step_state(
                    result=result,
                    step_key=definition.step_key,
                    status="completed",
                    detail=step_result.get("detail") or definition.title,
                )
                self._job_service.update_job_status(
                    job_id=job_id,
                    status="running",
                    progress=int(index * 100 / len(MOTION_EXTRACTION_STEPS)),
                    result=result,
                )
        except Exception as exc:
            error_detail = str(exc).strip() or "动作提取失败。"
            logger.exception("Motion extraction failed: project_id=%s job_id=%s", project_id, job_id)
            self._set_step_state(
                result=result,
                step_key=next(
                    (
                        item["step_key"]
                        for item in result["steps"]
                        if item["status"] == "running"
                    ),
                    "finish",
                ),
                status="failed",
                detail=error_detail,
                error_detail=error_detail,
            )
            result["error_detail"] = error_detail
            self._job_service.update_job_status(
                job_id=job_id,
                status="failed",
                progress=max(1, max((idx for idx, _ in enumerate(result["steps"], start=1)), default=1)),
                result=result,
                error_message=error_detail,
                finished_at=utcnow_ms(),
            )
            self._append_project_message(
                project_id=project_id,
                message_type="workflow_error",
                content=error_detail,
                content_json={"job_id": job_id, "workflow_type": "motion_extraction"},
            )
            raise

        self._job_service.update_job_status(
            job_id=job_id,
            status="succeeded",
            progress=100,
            result=result,
            finished_at=utcnow_ms(),
        )
        self._append_project_message(
            project_id=project_id,
            message_type="motion_extraction_result",
            content=result.get("steps", [])[-1].get("detail") or "动作提取完成。",
            content_json={
                "job_id": job_id,
                "workflow_type": "motion_extraction",
                "saved_count": result.get("saved_count", 0),
                "asset_ids": result.get("asset_ids", []),
            },
        )
        return result

    async def step_validate_analysis(
        self,
        *,
        project: dict[str, Any],
        context: dict[str, Any],
        job_id: str,
        owner_user_id: str | None,
    ) -> dict[str, Any]:
        shot_segments = self._project_service._load_shot_segments_for_project(
            project_id=project["id"],
        )
        if not shot_segments:
            raise ValueError("该项目尚未完成视频分析，请先生成 shot_segments 后再执行动作提取。")

        from app.db.session import get_db_session
        from sqlalchemy import select
        from app.models.project import Storyboard
        _session = next(get_db_session())
        try:
            storyboard = self._project_service._load_latest_storyboard(
                session=_session,
                project_id=project["id"],
            )
        finally:
            _session.close()

        source_video_asset_id = (
            project.get("source_asset_id")
            or next(
                (
                    item.get("source_video_asset_id")
                    for item in shot_segments
                    if item.get("source_video_asset_id")
                ),
                None,
            )
        )
        source_asset = (
            self._asset_service.get_asset(asset_id=source_video_asset_id)
            if source_video_asset_id
            else None
        )
        storyboard_count = len((storyboard or {}).get("items") or [])
        detail = f"数据就绪：{len(shot_segments)} 个镜头片段，{storyboard_count} 条分镜描述。"
        if not storyboard_count:
            detail += " 当前未检测到结构化分镜，后续将回退为镜头文本组合。"
        return {
            "detail": detail,
            "shot_segments": shot_segments,
            "storyboard": storyboard or {"summary": "", "items": []},
            "shot_count": len(shot_segments),
            "storyboard_count": storyboard_count,
            "source_video_asset_id": source_video_asset_id,
            "source_asset": source_asset,
        }

    async def step_coarse_filter(
        self,
        *,
        project: dict[str, Any],
        context: dict[str, Any],
        job_id: str,
        owner_user_id: str | None,
    ) -> dict[str, Any]:
        validated = context["validate_analysis_data"]
        shot_segments = validated.get("shot_segments") or []
        storyboard_items = (validated.get("storyboard") or {}).get("items") or []
        storyboard_index = self._build_storyboard_index(storyboard_items)

        motion_settings = context.get("_motion_settings") or {}
        extraction_hint = str(context.get("_extraction_hint") or "").strip()
        hint_labels = context.get("_hint_labels") or []
        coarse_filter_mode = str(motion_settings.get("coarse_filter_mode") or "keyword").strip().lower()
        min_duration = int(motion_settings.get("min_duration_ms") or MIN_MOTION_DURATION_MS)
        max_duration = int(motion_settings.get("max_duration_ms") or MAX_MOTION_DURATION_MS)
        signal_threshold = int(motion_settings.get("signal_score_threshold") or 3)
        is_permissive = coarse_filter_mode == "permissive"

        candidates: list[dict[str, Any]] = []
        filtered_items: list[dict[str, Any]] = []
        for segment in shot_segments:
            segment_index = int(segment.get("segment_index") or 0)
            related_items = storyboard_index.get(segment_index, [])
            storyboard_text = self._build_storyboard_text(storyboard_items=related_items)
            combined_text = self._build_candidate_text(segment=segment, storyboard_items=related_items)

            if is_permissive:
                evaluation = self._evaluate_coarse_filter_candidate(
                    start_ms=int(segment.get("start_ms") or 0),
                    end_ms=int(segment.get("end_ms") or 0),
                    title_text=str(segment.get("title") or "").strip(),
                    transcript_text=str(segment.get("transcript_text") or "").strip(),
                    visual_summary=str(segment.get("visual_summary") or "").strip(),
                    storyboard_text=storyboard_text,
                    ocr_text=str(segment.get("ocr_text") or "").strip(),
                    min_duration_ms=min_duration,
                    max_duration_ms=max_duration,
                    signal_score_threshold=signal_threshold,
                    permissive=True,
                    hint_labels=hint_labels,
                )
            else:
                evaluation = self._evaluate_coarse_filter_candidate(
                    start_ms=int(segment.get("start_ms") or 0),
                    end_ms=int(segment.get("end_ms") or 0),
                    title_text=str(segment.get("title") or "").strip(),
                    transcript_text=str(segment.get("transcript_text") or "").strip(),
                    visual_summary=str(segment.get("visual_summary") or "").strip(),
                    storyboard_text=storyboard_text,
                    ocr_text=str(segment.get("ocr_text") or "").strip(),
                    min_duration_ms=min_duration,
                    max_duration_ms=max_duration,
                    signal_score_threshold=signal_threshold,
                    hint_labels=hint_labels,
                )
            if not evaluation["is_candidate"]:
                filtered_items.append(
                    self._build_filtered_segment_record(
                        segment=segment,
                        storyboard_text=storyboard_text,
                        combined_text=combined_text,
                        evaluation=evaluation,
                    ),
                )
                continue

            candidates.append(
                {
                    "source_shot_segment_id": segment.get("id"),
                    "segment_index": segment_index,
                    "start_ms": int(segment.get("start_ms") or 0),
                    "end_ms": int(segment.get("end_ms") or 0),
                    "duration_ms": int(segment.get("duration_ms") or 0),
                    "transcript_text": str(segment.get("transcript_text") or "").strip(),
                    "ocr_text": str(segment.get("ocr_text") or "").strip(),
                    "visual_summary": str(segment.get("visual_summary") or "").strip(),
                    "title": str(segment.get("title") or "").strip(),
                    "scene_label": str(segment.get("scene_label") or "").strip(),
                    "shot_type_code": str(segment.get("shot_type_code") or "").strip(),
                    "camera_motion_code": str(segment.get("camera_motion_code") or "").strip(),
                    "camera_angle_code": str(segment.get("camera_angle_code") or "").strip(),
                    "storyboard_text": storyboard_text,
                    "combined_text": combined_text,
                    "matched_labels": evaluation["matched_labels"],
                    "matched_sources": evaluation["matched_sources"],
                    "signal_score": evaluation["signal_score"],
                }
            )

        mode_label = "全通过" if is_permissive else "关键词"
        filtered_summary = self._summarize_filtered_items(filtered_items)
        detail = f"粗筛完成（{mode_label}模式）：从 {len(shot_segments)} 个镜头中筛出 {len(candidates)} 个候选。"
        if extraction_hint:
            detail += " 已应用辅助提示，对已有动作信号进行优先级加权。"
        if filtered_items:
            detail += f" 已过滤 {len(filtered_items)} 个镜头（{self._format_filtered_summary(filtered_summary)}）。"
        if not candidates and not is_permissive:
            detail += f" 当前关键词模式阈值为 {signal_threshold}。"
            if filtered_summary.get("no_motion_signal") == len(filtered_items):
                detail += " 当前镜头文本缺少可识别动作信号，可切换为宽松模式或优化分镜描述。"
            elif filtered_summary.get("duration_too_short") or filtered_summary.get("duration_too_long"):
                detail += " 当前可尝试放宽镜头时长范围。"
        return {
            "detail": detail,
            "total_shots": len(shot_segments),
            "candidate_count": len(candidates),
            "candidates": candidates,
            "filtered_items": filtered_items,
            "filtered_summary": filtered_summary,
            "coarse_filter_mode": coarse_filter_mode,
            "source_video_asset_id": validated.get("source_video_asset_id"),
        }

    async def step_tag_candidates(
        self,
        *,
        project: dict[str, Any],
        context: dict[str, Any],
        job_id: str,
        owner_user_id: str | None,
    ) -> dict[str, Any]:
        candidates = context["coarse_filter_shots"].get("candidates") or []
        motion_settings = context.get("_motion_settings") or {}
        confidence_threshold = self._safe_float(
            motion_settings.get("confidence_threshold"), default=0.6,
        )
        # Build provider_group from motion_extraction settings so AI uses the configured model
        provider_group: dict[str, Any] | None = None
        if motion_settings.get("providers"):
            provider_group = {
                "default_provider": motion_settings.get("default_provider") or "",
                "providers": motion_settings.get("providers") or [],
            }

        tagged_results: list[dict[str, Any]] = []

        for candidate in candidates:
            fallback_tags = self._build_fallback_tags(candidate=candidate)
            ai_result = await self._analysis_ai_service.generate_motion_tags_reply(
                source_name=project.get("source_name") or project.get("title") or "视频片段",
                candidate=candidate,
                fallback_payload=fallback_tags,
                extraction_hint=str(context.get("_extraction_hint") or "").strip() or None,
                provider_group=provider_group,
            )
            raw_tags = ai_result.get("payload") or fallback_tags
            tags = self._normalize_ai_tags(
                candidate=candidate,
                tags=raw_tags,
                fallback_tags=fallback_tags,
            )
            confidence = self._safe_float(tags.get("confidence"), default=0.0)
            is_high_value = bool(tags.get("is_high_value", False))
            if not is_high_value or confidence < confidence_threshold:
                continue

            tagged_results.append(
                {
                    **candidate,
                    "tags": tags,
                    "provider": ai_result.get("provider"),
                    "model": ai_result.get("model"),
                    "used_remote": bool(ai_result.get("used_remote")),
                    "raw_tags": raw_tags,
                }
            )

        return {
            "detail": f"精标完成：{len(tagged_results)} 个高价值动作片段。",
            "tagged_count": len(tagged_results),
            "tagged_results": tagged_results,
            "source_video_asset_id": context["coarse_filter_shots"].get("source_video_asset_id"),
        }

    async def step_generate_thumbnails(
        self,
        *,
        project: dict[str, Any],
        context: dict[str, Any],
        job_id: str,
        owner_user_id: str | None,
    ) -> dict[str, Any]:
        tagged_results = context["tag_candidates"].get("tagged_results") or []
        source_asset = context["validate_analysis_data"].get("source_asset") or {}
        file_path = str(source_asset.get("file_path") or "").strip()
        ffmpeg_bin = shutil.which("ffmpeg")
        if not tagged_results:
            return {
                "detail": "没有高价值候选片段，跳过预览素材生成。",
                "thumbnails": {},
                "clips": {},
            }
        if not ffmpeg_bin or not file_path or not Path(file_path).exists():
            return {
                "detail": "当前环境缺少可用的 ffmpeg 或源视频文件，已跳过截图和片段生成。",
                "thumbnails": {},
                "clips": {},
            }

        thumbnails: dict[str, str] = {}
        clips: dict[str, str] = {}
        for item in tagged_results:
            segment_id = str(item.get("source_shot_segment_id") or item.get("segment_index") or "")
            thumbnail_path = await self._extract_thumbnail(
                ffmpeg_bin=ffmpeg_bin,
                source_file=file_path,
                project_id=project["id"],
                segment_id=segment_id,
                timestamp_ms=(int(item.get("start_ms") or 0) + int(item.get("end_ms") or 0)) // 2,
            )
            if thumbnail_path:
                thumbnails[str(item.get("source_shot_segment_id") or "")] = thumbnail_path
            clip_path = await self._extract_clip(
                ffmpeg_bin=ffmpeg_bin,
                source_file=file_path,
                project_id=project["id"],
                segment_id=segment_id,
                start_ms=int(item.get("start_ms") or 0),
                end_ms=int(item.get("end_ms") or 0),
            )
            if clip_path:
                clips[str(item.get("source_shot_segment_id") or "")] = clip_path

        return {
            "detail": f"已生成 {len(thumbnails)} 张缩略图和 {len(clips)} 个动作片段。",
            "thumbnails": thumbnails,
            "clips": clips,
        }

    async def step_save_assets(
        self,
        *,
        project: dict[str, Any],
        context: dict[str, Any],
        job_id: str,
        owner_user_id: str | None,
    ) -> dict[str, Any]:
        tagged_results = context["tag_candidates"].get("tagged_results") or []
        thumbnails = context["generate_thumbnails"].get("thumbnails") or {}
        preview_clips = context["generate_thumbnails"].get("clips") or {}
        source_video_asset_id = context["validate_analysis_data"].get("source_video_asset_id")
        if not tagged_results:
            return {
                "detail": "没有符合条件的动作片段，未写入动作资产。",
                "saved_count": 0,
                "asset_ids": [],
                "items": [],
                "source_video_asset_id": source_video_asset_id,
            }

        clips: list[dict[str, Any]] = []
        asset_owner_user_id = owner_user_id or project.get("user_id")
        for item in tagged_results:
            tags = item.get("tags") or {}
            source_shot_segment_id = str(item.get("source_shot_segment_id") or "")
            thumbnail_path = thumbnails.get(source_shot_segment_id)
            thumbnail_asset = self._create_preview_asset(
                owner_user_id=asset_owner_user_id,
                file_path=thumbnail_path,
                asset_type="image",
                mime_type="image/jpeg",
                source_type="derived",
                duration_ms=None,
                thumbnail_path=thumbnail_path,
                metadata={
                    "project_id": project["id"],
                    "job_id": job_id,
                    "source_video_asset_id": source_video_asset_id,
                    "source_shot_segment_id": source_shot_segment_id,
                    "preview_kind": "motion_thumbnail",
                },
            )
            clip_path = preview_clips.get(source_shot_segment_id)
            clip_asset = self._create_preview_asset(
                owner_user_id=asset_owner_user_id,
                file_path=clip_path,
                asset_type="video",
                mime_type="video/mp4",
                source_type="derived",
                duration_ms=max(int(item.get("end_ms") or 0) - int(item.get("start_ms") or 0), 0),
                thumbnail_path=thumbnail_path,
                metadata={
                    "project_id": project["id"],
                    "job_id": job_id,
                    "source_video_asset_id": source_video_asset_id,
                    "source_shot_segment_id": source_shot_segment_id,
                    "preview_kind": "motion_clip",
                    "thumbnail_asset_id": thumbnail_asset["id"] if thumbnail_asset else None,
                    "thumbnail_path": thumbnail_path,
                },
            )
            clips.append(
                {
                    "start_ms": int(item.get("start_ms") or 0),
                    "end_ms": int(item.get("end_ms") or 0),
                    "action_summary": str(tags.get("action_summary") or "").strip() or self._build_fallback_summary(item),
                    "action_label": str(tags.get("action_label") or "").strip() or None,
                    "entrance_style": str(tags.get("entrance_style") or "").strip() or None,
                    "emotion_label": str(tags.get("emotion_label") or "").strip() or None,
                    "temperament_label": str(tags.get("temperament_label") or "").strip() or None,
                    "scene_label": str(tags.get("scene_label") or "").strip() or None,
                    "camera_motion": str(tags.get("camera_motion") or item.get("camera_motion_code") or "").strip() or None,
                    "camera_shot": str(tags.get("camera_shot") or item.get("shot_type_code") or "").strip() or None,
                    "confidence": self._safe_float(tags.get("confidence"), default=0.75),
                    "asset_candidate": True,
                    "clip_asset_id": clip_asset["id"] if clip_asset else None,
                    "review_status": "approved",
                    "copyright_risk_level": "unknown",
                    "metadata_json": {
                        "matched_labels": item.get("matched_labels") or [],
                        "matched_sources": item.get("matched_sources") or [],
                        "signal_score": int(item.get("signal_score") or 0),
                        "project_id": project["id"],
                        "source_shot_segment_id": source_shot_segment_id,
                        "thumbnail_path": thumbnail_path,
                        "thumbnail_asset_id": thumbnail_asset["id"] if thumbnail_asset else None,
                        "analysis_source": "motion_extraction",
                        "used_remote": bool(item.get("used_remote")),
                        "provider": item.get("provider"),
                        "model": item.get("model"),
                        "raw_tags": item.get("raw_tags") or {},
                        "auto_approved": True,
                        "extraction_hint": str(context.get("_extraction_hint") or "").strip(),
                    },
                }
            )

        saved_assets = self._asset_service.create_motion_assets_from_analysis(
            source_video_asset_id=source_video_asset_id,
            project_id=project["id"],
            job_id=job_id,
            owner_user_id=owner_user_id or project.get("user_id"),
            clips=clips,
            origin="ai_generated",
        )
        return {
            "detail": f"已保存 {len(saved_assets)} 个动作资产到资产库。",
            "saved_count": len(saved_assets),
            "asset_ids": [item["id"] for item in saved_assets],
            "items": saved_assets,
            "source_video_asset_id": source_video_asset_id,
        }

    async def step_finish(
        self,
        *,
        project: dict[str, Any],
        context: dict[str, Any],
        job_id: str,
        owner_user_id: str | None,
    ) -> dict[str, Any]:
        saved_count = int(context.get("save_motion_assets", {}).get("saved_count") or 0)
        return {
            "detail": f"动作资产提取完成，共沉淀 {saved_count} 条动作资产。",
            "saved_count": saved_count,
            "asset_ids": context.get("save_motion_assets", {}).get("asset_ids") or [],
            "items": context.get("save_motion_assets", {}).get("items") or [],
            "source_video_asset_id": context.get("save_motion_assets", {}).get("source_video_asset_id"),
        }

    def _set_step_state(
        self,
        *,
        result: dict[str, Any],
        step_key: str,
        status: str,
        detail: str,
        error_detail: str | None = None,
    ) -> None:
        for item in result.get("steps", []):
            if item["step_key"] != step_key:
                continue
            item["status"] = status
            item["detail"] = detail
            item["error_detail"] = error_detail
            break

    def _append_project_message(
        self,
        *,
        project_id: int,
        message_type: str,
        content: str,
        content_json: dict[str, Any] | None = None,
    ) -> None:
        self._project_service._append_project_message(
            project_id=project_id,
            role="assistant",
            message_type=message_type,
            content=content,
            content_json=content_json,
        )

    def _build_storyboard_index(self, storyboard_items: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
        indexed: dict[int, list[dict[str, Any]]] = {}
        for item in storyboard_items:
            for raw_index in item.get("source_segment_indexes") or []:
                try:
                    segment_index = int(raw_index)
                except (TypeError, ValueError):
                    continue
                indexed.setdefault(segment_index, []).append(item)
        return indexed

    def _build_candidate_text(
        self,
        *,
        segment: dict[str, Any],
        storyboard_items: list[dict[str, Any]],
    ) -> str:
        parts: list[str] = []
        for key in ("title", "visual_summary", "transcript_text", "ocr_text", "scene_label"):
            value = str(segment.get(key) or "").strip()
            if value:
                parts.append(value)
        for item in storyboard_items:
            for key in ("title", "visual_description", "transcript_excerpt", "ocr_excerpt"):
                value = str(item.get(key) or "").strip()
                if value:
                    parts.append(value)
        normalized_parts: list[str] = []
        seen: set[str] = set()
        for part in parts:
            lowered = part.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            normalized_parts.append(part)
        return " ".join(normalized_parts).strip()

    def _build_storyboard_text(self, *, storyboard_items: list[dict[str, Any]]) -> str:
        parts: list[str] = []
        for item in storyboard_items:
            for key in ("title", "visual_description", "transcript_excerpt", "ocr_excerpt"):
                value = str(item.get(key) or "").strip()
                if value:
                    parts.append(value)
        return " ".join(parts).strip()

    def _evaluate_coarse_filter_candidate(
        self,
        *,
        start_ms: int,
        end_ms: int,
        title_text: str,
        transcript_text: str,
        visual_summary: str,
        storyboard_text: str,
        ocr_text: str,
        min_duration_ms: int = MIN_MOTION_DURATION_MS,
        max_duration_ms: int = MAX_MOTION_DURATION_MS,
        signal_score_threshold: int = 3,
        permissive: bool = False,
        hint_labels: list[str] | None = None,
    ) -> dict[str, Any]:
        duration = max(0, end_ms - start_ms)
        if duration < min_duration_ms:
            return {
                "is_candidate": False,
                "matched_labels": [],
                "signal_score": 0,
                "matched_sources": [],
                "filter_reason": "duration_too_short",
                "duration_ms": duration,
                "matched_details": [],
            }
        if duration > max_duration_ms:
            return {
                "is_candidate": False,
                "matched_labels": [],
                "signal_score": 0,
                "matched_sources": [],
                "filter_reason": "duration_too_long",
                "duration_ms": duration,
                "matched_details": [],
            }

        if permissive:
            return {
                "is_candidate": True,
                "matched_labels": [],
                "signal_score": 0,
                "matched_sources": ["permissive"],
                "filter_reason": None,
                "duration_ms": duration,
                "matched_details": [],
            }

        source_payloads = (
            ("transcript_text", transcript_text, 4),
            ("storyboard_text", storyboard_text, 4),
            ("visual_summary", visual_summary, 3),
            ("title", title_text, 2),
            ("ocr_text", ocr_text, 1),
        )
        label_scores: dict[str, int] = {}
        matched_sources: list[str] = []
        matched_details: list[dict[str, Any]] = []
        signal_score = 0

        for source_name, raw_text, weight in source_payloads:
            text = str(raw_text or "").strip()
            if not text:
                continue
            if source_name in {"visual_summary", "title"} and self._is_generic_candidate_text(text):
                continue

            matched_labels = self._match_motion_labels(text=text)
            if not matched_labels:
                continue

            matched_sources.append(source_name)
            signal_score += weight
            matched_details.append(
                {
                    "source": source_name,
                    "weight": weight,
                    "labels": matched_labels,
                    "preview": self._trim_debug_text(text),
                },
            )
            for label in matched_labels:
                label_scores[label] = label_scores.get(label, 0) + weight

        if len(matched_sources) >= 2:
            signal_score += 1
        if len(label_scores) >= 2:
            signal_score += min(2, len(label_scores) - 1)

        ordered_labels = [
            label
            for label, _ in sorted(
                label_scores.items(),
                key=lambda item: (
                    -item[1],
                    list(MOTION_KEYWORDS.keys()).index(item[0]),
                ),
            )
        ]

        normalized_hint_labels = [
            label
            for label in (hint_labels or [])
            if label in MOTION_KEYWORDS
        ]
        matched_hint_labels = [
            label
            for label in ordered_labels
            if label in normalized_hint_labels
        ]
        if matched_hint_labels:
            hint_bonus = min(2, len(matched_hint_labels))
            signal_score += hint_bonus
            matched_sources.append("extraction_hint")
            matched_details.append(
                {
                    "source": "extraction_hint",
                    "weight": hint_bonus,
                    "labels": matched_hint_labels,
                    "preview": "本次提取辅助提示命中已有动作信号，已提升优先级。",
                },
            )

        filter_reason = None
        if signal_score < signal_score_threshold:
            filter_reason = "signal_below_threshold" if ordered_labels else "no_motion_signal"
        return {
            "is_candidate": signal_score >= signal_score_threshold,
            "matched_labels": ordered_labels,
            "signal_score": signal_score,
            "matched_sources": matched_sources,
            "filter_reason": filter_reason,
            "duration_ms": duration,
            "matched_details": matched_details,
        }

    def _coarse_filter_candidate(
        self,
        *,
        start_ms: int,
        end_ms: int,
        title_text: str,
        transcript_text: str,
        visual_summary: str,
        storyboard_text: str,
        ocr_text: str,
        min_duration_ms: int = MIN_MOTION_DURATION_MS,
        max_duration_ms: int = MAX_MOTION_DURATION_MS,
        signal_score_threshold: int = 3,
        hint_labels: list[str] | None = None,
    ) -> tuple[bool, list[str], int, list[str]]:
        evaluation = self._evaluate_coarse_filter_candidate(
            start_ms=start_ms,
            end_ms=end_ms,
            title_text=title_text,
            transcript_text=transcript_text,
            visual_summary=visual_summary,
            storyboard_text=storyboard_text,
            ocr_text=ocr_text,
            min_duration_ms=min_duration_ms,
            max_duration_ms=max_duration_ms,
            signal_score_threshold=signal_score_threshold,
            hint_labels=hint_labels,
        )
        return (
            evaluation["is_candidate"],
            evaluation["matched_labels"],
            evaluation["signal_score"],
            evaluation["matched_sources"],
        )

    def _build_filtered_segment_record(
        self,
        *,
        segment: dict[str, Any],
        storyboard_text: str,
        combined_text: str,
        evaluation: dict[str, Any],
    ) -> dict[str, Any]:
        reason = str(evaluation.get("filter_reason") or "no_motion_signal")
        return {
            "source_shot_segment_id": segment.get("id"),
            "segment_index": int(segment.get("segment_index") or 0),
            "start_ms": int(segment.get("start_ms") or 0),
            "end_ms": int(segment.get("end_ms") or 0),
            "duration_ms": int(evaluation.get("duration_ms") or segment.get("duration_ms") or 0),
            "title": str(segment.get("title") or "").strip(),
            "transcript_text": str(segment.get("transcript_text") or "").strip(),
            "visual_summary": str(segment.get("visual_summary") or "").strip(),
            "storyboard_text": storyboard_text,
            "combined_text": combined_text,
            "matched_labels": evaluation.get("matched_labels") or [],
            "matched_sources": evaluation.get("matched_sources") or [],
            "matched_details": evaluation.get("matched_details") or [],
            "signal_score": int(evaluation.get("signal_score") or 0),
            "filter_reason": reason,
            "filter_reason_label": FILTER_REASON_LABELS.get(reason, reason),
        }

    def _summarize_filtered_items(self, filtered_items: list[dict[str, Any]]) -> dict[str, int]:
        summary: dict[str, int] = {}
        for item in filtered_items:
            reason = str(item.get("filter_reason") or "unknown")
            summary[reason] = summary.get(reason, 0) + 1
        return summary

    def _format_filtered_summary(self, filtered_summary: dict[str, int]) -> str:
        ordered = sorted(
            filtered_summary.items(),
            key=lambda item: (-item[1], item[0]),
        )
        return "，".join(
            f"{FILTER_REASON_LABELS.get(reason, reason)} {count} 个"
            for reason, count in ordered
        )

    @staticmethod
    def _trim_debug_text(text: str, limit: int = 120) -> str:
        normalized = str(text or "").strip()
        if len(normalized) <= limit:
            return normalized
        return normalized[: limit - 1].rstrip() + "…"

    def _extract_hint_labels(self, hint_text: str) -> list[str]:
        normalized = str(hint_text or "").strip()
        if not normalized:
            return []

        labels = self._match_motion_labels(text=normalized)
        inferred_industrial_label = self._infer_industrial_action_label(text=normalized)
        if inferred_industrial_label and inferred_industrial_label not in labels:
            labels.append(inferred_industrial_label)
        return labels

    def _match_motion_labels(self, *, text: str) -> list[str]:
        lowered = str(text or "").strip().lower()
        compact = self._compact_text(lowered)
        matched: list[str] = []
        for label, keywords in MOTION_KEYWORDS.items():
            keyword_hit = any(
                self._keyword_in_text(keyword=keyword, lowered_text=lowered, compact_text=compact)
                for keyword in keywords
            )
            regex_hit = any(
                re.search(pattern, lowered)
                for pattern in MOTION_REGEX_PATTERNS.get(label, ())
            )
            if keyword_hit or regex_hit:
                matched.append(label)
        return matched

    def _is_generic_candidate_text(self, text: str) -> bool:
        normalized = str(text or "").strip()
        if not normalized:
            return True
        if any(phrase in normalized for phrase in GENERIC_CANDIDATE_PHRASES):
            return True
        compact = self._compact_text(normalized)
        return compact in {
            self._compact_text("该分镜以主体展示和节奏推进为主"),
            self._compact_text("镜头以主体与细节补充为主"),
            self._compact_text("中段通过主体展示与动作推进承接卖点信息"),
        }

    @staticmethod
    def _compact_text(text: str) -> str:
        return re.sub(r"[\s\.,;:!?，。！？、：；\"'“”‘’（）()\[\]{}<>《》【】—_\-]+", "", text.lower())

    def _keyword_in_text(self, *, keyword: str, lowered_text: str, compact_text: str) -> bool:
        normalized_keyword = str(keyword or "").strip().lower()
        if not normalized_keyword:
            return False
        if normalized_keyword in lowered_text:
            return True
        compact_keyword = self._compact_text(normalized_keyword)
        return bool(compact_keyword) and compact_keyword in compact_text

    def _build_fallback_tags(self, *, candidate: dict[str, Any]) -> dict[str, Any]:
        matched_labels = candidate.get("matched_labels") or []
        primary_label = matched_labels[0] if matched_labels else "stare"
        text = str(candidate.get("combined_text") or "").strip()
        inferred_industrial_action = self._infer_industrial_action_label(text=text)
        action_label = inferred_industrial_action or ACTION_LABEL_MAPPING.get(primary_label, "stand_and_stare")
        scene_label = self._normalize_enum_value(
            value=self._infer_label(text=text, mapping=SCENE_HINTS, default=candidate.get("scene_label") or "office"),
            allowed_values=set(SCENE_HINTS.keys()),
            fallback_value="office",
        )
        emotion_label = self._normalize_enum_value(
            value=self._infer_label(text=text, mapping=EMOTION_HINTS, default="determination"),
            allowed_values=set(EMOTION_HINTS.keys()),
            fallback_value="determination",
        )
        temperament_label = self._normalize_enum_value(
            value=self._infer_label(text=text, mapping=TEMPERAMENT_HINTS, default="silent_power"),
            allowed_values=set(TEMPERAMENT_HINTS.keys()),
            fallback_value="silent_power",
        )
        camera_motion = self._normalize_enum_value(
            value=str(candidate.get("camera_motion_code") or "static").strip() or "static",
            allowed_values=CAMERA_MOTION_VALUES,
            fallback_value="static",
            aliases=CAMERA_MOTION_ALIASES,
        )
        camera_shot = self._normalize_enum_value(
            value=str(candidate.get("shot_type_code") or "medium").strip() or "medium",
            allowed_values=CAMERA_SHOT_VALUES,
            fallback_value="medium",
            aliases=CAMERA_MOTION_ALIASES,
        )
        return {
            "action_label": action_label,
            "entrance_style": self._infer_fallback_entrance_style(
                primary_label=primary_label,
                action_label=action_label,
            ),
            "emotion_label": emotion_label,
            "temperament_label": temperament_label,
            "scene_label": scene_label,
            "camera_motion": camera_motion,
            "camera_shot": camera_shot,
            "action_summary": self._build_fallback_summary(candidate),
            "confidence": 0.76 if len(matched_labels) == 1 else 0.88,
            "is_high_value": True,
        }

    def _normalize_ai_tags(
        self,
        *,
        candidate: dict[str, Any],
        tags: dict[str, Any],
        fallback_tags: dict[str, Any],
    ) -> dict[str, Any]:
        normalized = dict(fallback_tags)
        raw_tags = tags or {}
        normalized["action_label"] = self._normalize_action_label(
            value=raw_tags.get("action_label"),
            candidate=candidate,
            fallback_value=str(fallback_tags.get("action_label") or "stand_and_stare"),
        )
        normalized["entrance_style"] = self._normalize_optional_enum_value(
            value=raw_tags.get("entrance_style"),
            allowed_values=ENTRANCE_STYLE_VALUES,
            fallback_value=fallback_tags.get("entrance_style"),
            aliases=ENTRANCE_STYLE_ALIASES,
        )
        normalized["emotion_label"] = self._normalize_enum_value(
            value=raw_tags.get("emotion_label"),
            allowed_values=set(EMOTION_HINTS.keys()),
            fallback_value=str(fallback_tags.get("emotion_label") or "determination"),
            aliases=EMOTION_VALUE_ALIASES,
        )
        normalized["temperament_label"] = self._normalize_enum_value(
            value=raw_tags.get("temperament_label"),
            allowed_values=set(TEMPERAMENT_HINTS.keys()),
            fallback_value=str(fallback_tags.get("temperament_label") or "silent_power"),
            aliases=TEMPERAMENT_VALUE_ALIASES,
        )
        normalized["scene_label"] = self._normalize_enum_value(
            value=raw_tags.get("scene_label"),
            allowed_values=set(SCENE_HINTS.keys()),
            fallback_value=str(fallback_tags.get("scene_label") or "office"),
            aliases=SCENE_VALUE_ALIASES,
        )
        normalized["camera_motion"] = self._normalize_enum_value(
            value=raw_tags.get("camera_motion"),
            allowed_values=CAMERA_MOTION_VALUES,
            fallback_value=str(fallback_tags.get("camera_motion") or "static"),
            aliases=CAMERA_MOTION_ALIASES,
        )
        normalized["camera_shot"] = self._normalize_enum_value(
            value=raw_tags.get("camera_shot"),
            allowed_values=CAMERA_SHOT_VALUES,
            fallback_value=str(fallback_tags.get("camera_shot") or "medium"),
            aliases=CAMERA_MOTION_ALIASES,
        )
        action_summary = str(raw_tags.get("action_summary") or "").strip()
        if action_summary:
            normalized["action_summary"] = action_summary
        normalized["confidence"] = self._safe_float(
            raw_tags.get("confidence"),
            default=self._safe_float(fallback_tags.get("confidence"), default=0.75),
        )
        normalized["is_high_value"] = bool(raw_tags.get("is_high_value", fallback_tags.get("is_high_value", True)))
        return normalized

    def _normalize_action_label(
        self,
        *,
        value: Any,
        candidate: dict[str, Any],
        fallback_value: str,
    ) -> str:
        normalized = str(value or "").strip().lower()
        if normalized in ACTION_LABEL_MAPPING.values():
            return normalized

        inferred_industrial_action = self._infer_industrial_action_label(text=normalized)
        if inferred_industrial_action:
            return inferred_industrial_action

        inferred_from_candidate = self._infer_industrial_action_label(
            text=str(candidate.get("combined_text") or ""),
        )
        matched_from_value = self._match_motion_labels(text=normalized)
        if matched_from_value:
            if inferred_from_candidate and matched_from_value[0] in {
                "wave",
                "smile",
                "point",
                "reach_out",
                "write",
                "push",
                "pull",
                "walk",
            }:
                return inferred_from_candidate
            return ACTION_LABEL_MAPPING.get(matched_from_value[0], fallback_value)

        if inferred_from_candidate:
            return inferred_from_candidate

        candidate_labels = candidate.get("matched_labels") or []
        if candidate_labels:
            return ACTION_LABEL_MAPPING.get(candidate_labels[0], fallback_value)
        return fallback_value

    def _infer_industrial_action_label(self, *, text: str) -> str | None:
        lowered = str(text or "").strip().lower()
        if not lowered:
            return None

        rules = (
            ("team_greeting", ("欢迎", "welcome", "挥手", "wave", "team", "团队", "factory", "工厂")),
            ("operate_machine", ("操作设备", "operate machine", "控制面板", "control panel", "监控仪表", "machine operation")),
            ("carry_goods", ("搬运", "carry goods", "carry bags", "装卸", "搬袋", "load goods")),
            ("display_product", ("展示产品", "showcase product", "product detail", "产品展示", "颗粒特写", "display product")),
            ("inspect_product", ("检查产品", "inspect product", "quality inspection", "检验", "查看颗粒")),
            ("material_flow", ("传送带", "conveyor", "pellets flowing", "物料流动", "production flow")),
            ("pour_material", ("倒料", "pour material", "投料", "feed material", "倾倒")),
            ("package_product", ("打包", "bagging", "packaging", "装袋", "封袋")),
        )
        compact_text = self._compact_text(lowered)
        for action_label, keywords in rules:
            if any(self._compact_text(keyword) in compact_text for keyword in keywords):
                return action_label
        return None

    def _infer_fallback_entrance_style(
        self,
        *,
        primary_label: str,
        action_label: str,
    ) -> str | None:
        if action_label == "team_greeting":
            return "welcome_entrance"
        if action_label in {"operate_machine", "carry_goods", "package_product"}:
            return "workshop_intro"
        if action_label in {"display_product", "inspect_product", "material_flow", "pour_material"}:
            return "product_closeup_entry"
        if primary_label in {"walk_in", "approach"}:
            return "camera_follow_entry"
        if primary_label == "push_door":
            return "door_entry"
        return None

    def _normalize_enum_value(
        self,
        *,
        value: Any,
        allowed_values: set[str],
        fallback_value: str,
        aliases: dict[str, str] | None = None,
    ) -> str:
        normalized = str(value or "").strip().lower()
        if not normalized:
            return fallback_value
        candidate = normalized.replace("-", "_").replace(" ", "_")
        if aliases:
            candidate = aliases.get(candidate, candidate)
        if candidate in allowed_values:
            return candidate
        compact_candidate = self._compact_text(candidate)
        for allowed in allowed_values:
            if compact_candidate == self._compact_text(allowed):
                return allowed
        return fallback_value

    def _normalize_optional_enum_value(
        self,
        *,
        value: Any,
        allowed_values: set[str],
        fallback_value: Any,
        aliases: dict[str, str] | None = None,
    ) -> str | None:
        fallback = str(fallback_value).strip() if fallback_value else ""
        normalized = str(value or "").strip().lower()
        if not normalized:
            return fallback or None
        candidate = normalized.replace("-", "_").replace(" ", "_")
        if aliases:
            candidate = aliases.get(candidate, candidate)
        if candidate in allowed_values:
            return candidate
        compact_candidate = self._compact_text(candidate)
        for allowed in allowed_values:
            if compact_candidate == self._compact_text(allowed):
                return allowed
        return fallback or None

    def _build_fallback_summary(self, candidate: dict[str, Any]) -> str:
        shot_title = str(candidate.get("title") or candidate.get("visual_summary") or "").strip()
        text = str(candidate.get("combined_text") or "").strip()
        if shot_title:
            return f"角色在该片段中围绕“{shot_title}”完成关键动作，镜头以{candidate.get('camera_motion_code') or 'static'}方式推进。"
        if text:
            trimmed = text[:60]
            return f"角色在该片段中完成关键动作推进，核心信息为：{trimmed}。"
        return "角色在该片段中完成关键动作推进，镜头强调动作节奏与情绪变化。"

    def _infer_label(
        self,
        *,
        text: str,
        mapping: dict[str, list[str]],
        default: str,
    ) -> str:
        lowered = (text or "").lower()
        for label, keywords in mapping.items():
            if any(keyword in lowered for keyword in keywords):
                return label
        return default

    async def _extract_thumbnail(
        self,
        *,
        ffmpeg_bin: str,
        source_file: str,
        project_id: int,
        segment_id: str,
        timestamp_ms: int,
    ) -> str | None:
        output_dir = Path.cwd() / "uploads" / "motion-thumbnails"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{project_id}-{segment_id}.jpg"
        command = [
            ffmpeg_bin,
            "-loglevel",
            "error",
            "-y",
            "-ss",
            f"{max(timestamp_ms, 0) / 1000:.3f}",
            "-i",
            source_file,
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(output_path),
        ]
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await process.communicate()
        except Exception:
            logger.debug("Thumbnail extraction skipped for %s", source_file, exc_info=True)
            return None

        if process.returncode != 0 or not output_path.exists():
            logger.debug(
                "ffmpeg thumbnail extraction failed for %s: %s",
                source_file,
                stderr.decode("utf-8", errors="ignore").strip(),
            )
            return None
        return str(output_path)

    async def _extract_clip(
        self,
        *,
        ffmpeg_bin: str,
        source_file: str,
        project_id: int,
        segment_id: str,
        start_ms: int,
        end_ms: int,
    ) -> str | None:
        duration_ms = max(end_ms - start_ms, 0)
        if duration_ms <= 0:
            return None

        output_dir = Path.cwd() / "uploads" / "motion-clips"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{project_id}-{segment_id}.mp4"
        command = [
            ffmpeg_bin,
            "-loglevel",
            "error",
            "-y",
            "-ss",
            f"{max(start_ms, 0) / 1000:.3f}",
            "-i",
            source_file,
            "-t",
            f"{duration_ms / 1000:.3f}",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await process.communicate()
        except Exception:
            logger.debug("Clip extraction skipped for %s", source_file, exc_info=True)
            return None

        if process.returncode != 0 or not output_path.exists():
            logger.debug(
                "ffmpeg clip extraction failed for %s: %s",
                source_file,
                stderr.decode("utf-8", errors="ignore").strip(),
            )
            return None
        return str(output_path)

    def _create_preview_asset(
        self,
        *,
        owner_user_id: str | None,
        file_path: str | None,
        asset_type: str,
        mime_type: str,
        source_type: str,
        duration_ms: int | None,
        thumbnail_path: str | None,
        metadata: dict[str, Any],
    ) -> dict[str, Any] | None:
        normalized_path = str(file_path or "").strip()
        if not normalized_path:
            return None
        asset_path = Path(normalized_path)
        if not asset_path.exists():
            return None

        return self._asset_service.create_asset(
            owner_user_id=owner_user_id,
            asset_type=asset_type,
            source_type=source_type,
            file_name=asset_path.name,
            file_path=str(asset_path),
            mime_type=mime_type,
            size_bytes=asset_path.stat().st_size,
            duration_ms=duration_ms,
            thumbnail_path=thumbnail_path,
            metadata=metadata,
        )

    @staticmethod
    def _safe_float(value: Any, *, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
