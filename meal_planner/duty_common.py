"""Report_Normal（報平安更）同 OnOff_Duty（報開工/收工）共用嘅政策 + 靜態資料。

改 grace/retry 政策淨係改呢度，兩邊自動一致；30 小時制/時間解析喺 timeparse.py，
更表讀法喺 roster.py，更時表解讀喺 shift_time.py。
"""

from __future__ import annotations

from datetime import datetime

# 到期後嘅寬限期：期內未發＝due（可以自動發），過咗＝missed。
GRACE_MINUTES = 15
GRACE_DETAIL = f"passed grace window ({GRACE_MINUTES} min)"

# 上次發送失敗後，最少等幾多秒先重試（唔好每 tick 狂試）。
RETRY_SECONDS = 60


def retry_backoff_active(last_recorded_iso: str | None, now: datetime | None = None) -> bool:
    """上次失敗記錄仲喺 backoff 期內？（記錄無效當唔喺 backoff，即刻可以再試。）"""
    try:
        last = datetime.fromisoformat(str(last_recorded_iso or ""))
        ref = now or datetime.now(last.tzinfo)
        return (ref - last).total_seconds() < RETRY_SECONDS
    except (ValueError, TypeError):
        return False


# 更碼 → (form_key, Post 崗位)（用戶 15/07/2026 確認）。OnOff_Duty 交 form 用；
# Report_Normal 亦借佢個 key 集做「全套已知更碼」（電話 Change code pickup list）。
POST_MAPPING: dict[str, tuple[str, str]] = {
    "Lecole": ("vca", "L'ECOLE 珠寶學院"),
    "Lecole Event": ("vca", "L'ECOLE-event 珠寶學院"),
    "VCRA": ("vca", "V-CR/A 廣東道"),
    "VCRB": ("vca", "V-CR/B 廣東道"),
    "VLG": ("vca", "V-LG 利園"),
    "VOC": ("vca", "V-OC 海港"),
    "VPP": ("vca", "V-PP 金鐘太古廣場"),
    "EleA": ("other", "ELEA - Chanel  圓方"),
    "EleB": ("other", "ELEB - Chanel 圓方"),
    "EleC1": ("other", "ELEC - Chanel  圓方"),
    "EleC2": ("other", "ELEC - Chanel  圓方"),
    "EleD": ("other", "ELED - Chanel  圓方"),
    "EleM": ("other", "ELEM - Chanel  圓方"),
    "IFCA1": ("other", "A1 - IFC 時裝"),
    "IFCA2": ("other", "A2 - IFC 時裝"),
    "IFCB1": ("other", "B1 - IFC 時裝"),
    "IFCB2": ("other", "B2 - IFC 時裝"),
    "IFCFJ1": ("other", "FJ-1 - IFC 珠寶"),
    "IFCFJ2": ("other", "FJ-2 - IFC 珠寶"),
    "IFCM1": ("other", "M1 - IFC 飯更"),
    "IFCM2": ("other", "M2 - IFC ＆ OES 飯更"),
    "IFCS1": ("other", "S1 - IFC 鞋店"),
    "IFCS2": ("other", "S2 - IFC 鞋店"),
    "OES1": ("other", "OES-1- 交易廣場"),
    "OES2": ("other", "OES-2 - 交易廣場"),
    "PenA": ("other", "PENA - 半島時裝"),
    "PenB": ("other", "PENB - 半島時裝"),
    "PenBB": ("other", "PENB - 半島時裝"),
    "PenBM": ("other", "PENB - 半島時裝"),
    "PenC": ("other", "PENC - 半島時裝"),
    "PenC頂位": ("other", "PENC - 半島時裝"),
    "PenFJ": ("other", "PEN-FJ - 半島珠寶"),
    "PenM": ("other", "PENM -  半島時裝"),
    "TSA": ("other", "TSA - Chanel 時代"),
    "TSB": ("other", "TSB - Chanel 時代"),
    "TSM": ("other", "TSM - Chanel 時代"),
}
