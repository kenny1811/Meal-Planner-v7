"""Report_Normal（報平安更）同 OnOff_Duty（報開工/收工）共用嘅政策 + 靜態資料。

改 grace/retry 政策淨係改呢度，兩邊自動一致；30 小時制/時間解析喺 timeparse.py，
更表讀法喺 roster.py，更時表解讀喺 shift_time.py。
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Callable

# 到期後嘅寬限期：期內未發＝due（可以自動發），過咗＝missed。
GRACE_MINUTES = 15
GRACE_DETAIL = f"passed grace window ({GRACE_MINUTES} min)"

# 上次發送失敗後，最少等幾多秒先重試（唔好每 tick 狂試）。
RETRY_SECONDS = 60


def load_kv_config(lock, connect: Callable[[], Any], table: str) -> dict[str, Any]:
    """key/value JSON 設定表 → dict（壞 JSON 嘅 row 跳過）。

    Report_Normal 同 OnOff_Duty 兩張 config 表結構一樣，讀法收埋喺呢度。
    `table` 係模組常數，唔會來自用戶輸入。
    """
    with lock:
        conn = connect()
        try:
            rows = conn.execute(f"SELECT config_key, value_json FROM {table}").fetchall()
        finally:
            conn.close()
    stored: dict[str, Any] = {}
    for key, value_json in rows:
        try:
            stored[key] = json.loads(value_json)
        except ValueError:
            continue
    return stored


def retry_backoff_active(last_recorded_iso: str | None, now: datetime | None = None) -> bool:
    """上次失敗記錄仲喺 backoff 期內？（記錄無效當唔喺 backoff，即刻可以再試。）"""
    try:
        last = datetime.fromisoformat(str(last_recorded_iso or ""))
        ref = now or datetime.now(last.tzinfo)
        return (ref - last).total_seconds() < RETRY_SECONDS
    except (ValueError, TypeError):
        return False

# 更碼 → Google Form 個「Post」崗位嘅**初始內容**（用戶 15/07/2026 確認）。
# 呢個係唯一推唔出嘅嘢：PenB/PenBB/PenBM 共用一個 Post、EleC1/EleC2 又共用另一個，冇規律。
# 第一次開 DB 會 seed 落 roster_post_mapping 表，之後以表為準（Config → 系統參數 改得到），
# 呢度就唔會再讀。行邊條 form 唔使記——由更碼推（roster_codes.form_key_for_code）。
POST_MAPPING_SEED: dict[str, str] = {
    "Lecole": "L'ECOLE 珠寶學院",
    "Lecole Event": "L'ECOLE-event 珠寶學院",
    "VCRA": "V-CR/A 廣東道",
    "VCRB": "V-CR/B 廣東道",
    "VLG": "V-LG 利園",
    "VOC": "V-OC 海港",
    "VPP": "V-PP 金鐘太古廣場",
    "EleA": "ELEA - Chanel  圓方",
    "EleB": "ELEB - Chanel 圓方",
    "EleC1": "ELEC - Chanel  圓方",
    "EleC2": "ELEC - Chanel  圓方",
    "EleD": "ELED - Chanel  圓方",
    "EleM": "ELEM - Chanel  圓方",
    "IFCA1": "A1 - IFC 時裝",
    "IFCA2": "A2 - IFC 時裝",
    "IFCB1": "B1 - IFC 時裝",
    "IFCB2": "B2 - IFC 時裝",
    "IFCFJ1": "FJ-1 - IFC 珠寶",
    "IFCFJ2": "FJ-2 - IFC 珠寶",
    "IFCM1": "M1 - IFC 飯更",
    "IFCM2": "M2 - IFC ＆ OES 飯更",
    "IFCS1": "S1 - IFC 鞋店",
    "IFCS2": "S2 - IFC 鞋店",
    "OES1": "OES-1- 交易廣場",
    "OES2": "OES-2 - 交易廣場",
    "PenA": "PENA - 半島時裝",
    "PenB": "PENB - 半島時裝",
    "PenBB": "PENB - 半島時裝",
    "PenBM": "PENB - 半島時裝",
    "PenC": "PENC - 半島時裝",
    "PenC頂位": "PENC - 半島時裝",
    "PenFJ": "PEN-FJ - 半島珠寶",
    "PenM": "PENM -  半島時裝",
    "TSA": "TSA - Chanel 時代",
    "TSB": "TSB - Chanel 時代",
    "TSM": "TSM - Chanel 時代",
}
