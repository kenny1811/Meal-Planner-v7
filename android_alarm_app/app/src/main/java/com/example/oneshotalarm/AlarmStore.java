package com.example.oneshotalarm;

import android.content.Context;
import android.content.SharedPreferences;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.LinkedHashSet;

final class AlarmStore {
    private static final String PREFS = "alarm_store";
    static final String DEFAULT_AUTO_SYNC_SERVER = "http://192.168.15.125:8765";
    // NordVPN Meshnet：出街（mobile data）時 LAN 到唔到，經 meshnet IP 直達 PC。
    static final String MESHNET_AUTO_SYNC_SERVER = "http://100.119.164.40:8765";
    private static final String KEY_ALARMS = "alarms_json";
    private static final String KEY_PLAN_DATE = "plan_date";
    private static final String KEY_ROSTER_CODE = "roster_code";
    private static final String KEY_AUTO_SYNC_SERVER = "auto_sync_server_url";
    private static final String KEY_MEAL_PLAN_TEXT = "meal_plan_text";
    private static final String KEY_MEAL_PLAN_JSON = "meal_plan_json";
    private static final String KEY_MEAL_PLAN_JSON_DATE = "meal_plan_json_date";
    private static final String KEY_MEAL_PLAN_JSON_VERSION = "meal_plan_json_version";
    private static final String KEY_MEAL_PLAN_JSON_BY_DATE_PREFIX = "meal_plan_json_";
    private static final String KEY_MEAL_PLAN_JSON_VERSION_BY_DATE_PREFIX = "meal_plan_json_version_";
    private static final String KEY_LAST_IMPORT_AT = "last_import_at_epoch_ms";
    private static final String KEY_WATCH_ALARM_ENABLED = "watch_alarm_enabled";
    private static final String KEY_SCHEDULE_GRID_VARIANTS = "schedule_grid_variants_json";
    // 「上一個響咗」長存版。唔靠 alarms list 反推：排新 plan 會成個 list
    // 換走，啱啱響完嗰個（收工之後成日都係咁）就跟 plan 陪葬埋 ——
    // 對面個 launcher 嘅 Prev 會突然倒退去第二個 app 嘅舊鬧鐘。
    // clear() 都特登唔剷呢兩條：清 plan 唔等於改寫歷史。
    private static final String KEY_LAST_FIRED_AT = "last_fired_at_epoch_ms";
    private static final String KEY_LAST_FIRED_LABEL = "last_fired_label";

    private AlarmStore() {
    }

    static void savePlan(Context context, JSONArray alarms, long cleanupAtMillis) {
        savePlan(context, alarms, cleanupAtMillis, getPlanDate(context), getRosterCode(context));
    }

    static void savePlan(
            Context context,
            JSONArray alarms,
            long cleanupAtMillis,
            String planDate,
            String rosterCode
    ) {
        prefs(context).edit()
                .putString(KEY_ALARMS, alarms == null ? "[]" : alarms.toString())
                .putString(KEY_PLAN_DATE, planDate == null ? "" : planDate)
                .putString(KEY_ROSTER_CODE, rosterCode == null ? "" : rosterCode)
                .apply();
        NextAlarmProvider.notifyChanged(context);
    }

    static JSONArray getAlarms(Context context) {
        String raw = prefs(context).getString(KEY_ALARMS, "[]");
        try {
            return new JSONArray(raw);
        } catch (JSONException e) {
            return new JSONArray();
        }
    }

    static void saveScheduleGridVariants(Context context, JSONArray variants) {
        prefs(context).edit()
                .putString(KEY_SCHEDULE_GRID_VARIANTS, variants == null ? "[]" : variants.toString())
                .apply();
    }

    static JSONArray getScheduleGridVariants(Context context) {
        String raw = prefs(context).getString(KEY_SCHEDULE_GRID_VARIANTS, "[]");
        try {
            return new JSONArray(raw);
        } catch (JSONException e) {
            return new JSONArray();
        }
    }

    static String getPlanDate(Context context) {
        return prefs(context).getString(KEY_PLAN_DATE, "");
    }

    static String getRosterCode(Context context) {
        return prefs(context).getString(KEY_ROSTER_CODE, "");
    }

    static void markLastImportNow(Context context) {
        prefs(context).edit().putLong(KEY_LAST_IMPORT_AT, System.currentTimeMillis()).apply();
    }

    static long getLastImportAt(Context context) {
        return prefs(context).getLong(KEY_LAST_IMPORT_AT, 0L);
    }

    static boolean isWatchAlarmEnabled(Context context) {
        return prefs(context).getBoolean(KEY_WATCH_ALARM_ENABLED, false);
    }

    static void setWatchAlarmEnabled(Context context, boolean enabled) {
        prefs(context).edit().putBoolean(KEY_WATCH_ALARM_ENABLED, enabled).apply();
    }

    static String getMealPlanText(Context context) {
        return prefs(context).getString(KEY_MEAL_PLAN_TEXT, "");
    }

    static void saveMealPlanJson(Context context, String dateIso, String json, String version) {
        String normalizedDate = normalizeDateKey(dateIso);
        SharedPreferences.Editor editor = prefs(context).edit()
                .putString(KEY_MEAL_PLAN_JSON_DATE, dateIso == null ? "" : dateIso)
                .putString(KEY_MEAL_PLAN_JSON, json == null ? "" : json)
                .putString(KEY_MEAL_PLAN_JSON_VERSION, version == null ? "" : version);
        if (!normalizedDate.isEmpty()) {
            editor.putString(KEY_MEAL_PLAN_JSON_BY_DATE_PREFIX + normalizedDate, json == null ? "" : json);
            editor.putString(KEY_MEAL_PLAN_JSON_VERSION_BY_DATE_PREFIX + normalizedDate, version == null ? "" : version);
        }
        editor.apply();
        NextAlarmProvider.notifyChanged(context);     // 更碼跟餐單 JSON 走
    }

    static String getMealPlanJson(Context context) {
        return prefs(context).getString(KEY_MEAL_PLAN_JSON, "");
    }

    static String getMealPlanJsonDate(Context context) {
        return prefs(context).getString(KEY_MEAL_PLAN_JSON_DATE, "");
    }

    static String getMealPlanJsonVersion(Context context) {
        return prefs(context).getString(KEY_MEAL_PLAN_JSON_VERSION, "");
    }

    static String getMealPlanJsonForDate(Context context, String dateIso) {
        String normalizedDate = normalizeDateKey(dateIso);
        if (normalizedDate.isEmpty()) {
            return "";
        }
        return prefs(context).getString(KEY_MEAL_PLAN_JSON_BY_DATE_PREFIX + normalizedDate, "");
    }

    static String getMealPlanJsonVersionForDate(Context context, String dateIso) {
        String normalizedDate = normalizeDateKey(dateIso);
        if (normalizedDate.isEmpty()) {
            return "";
        }
        return prefs(context).getString(KEY_MEAL_PLAN_JSON_VERSION_BY_DATE_PREFIX + normalizedDate, "");
    }

    static String getAutoSyncServerUrl(Context context) {
        return DEFAULT_AUTO_SYNC_SERVER;
    }

    // 屋企 LAN 網段：淨係喺自己屋企個 router 先會派呢啲 IP（唔靠 Wi-Fi 名，唔使 location 權限）。
    private static final String HOME_LAN_PREFIX = "192.168.15.";

    static String[] getAutoSyncServerCandidates(Context context) {
        // 部機有 192.168.15.x 呢個 IP＝真係喺屋企個網 → LAN 行先，meshnet 做後備。
        // 唔喺屋企（mobile data／街外 Wi-Fi）：嗰個 LAN IP 數學上唔可能通，所以
        // 索性唔放入候選——以前照放後尾，meshnet 一失敗就硬食佢 2.5 秒 connect
        // timeout 白等，得個「試咗」嘅假象。
        return isOnHomeLan(context)
                ? new String[]{DEFAULT_AUTO_SYNC_SERVER, MESHNET_AUTO_SYNC_SERVER}
                : new String[]{MESHNET_AUTO_SYNC_SERVER};
    }

    private static boolean isOnHomeLan(Context context) {
        try {
            android.net.ConnectivityManager cm =
                    (android.net.ConnectivityManager) context.getSystemService(Context.CONNECTIVITY_SERVICE);
            if (cm == null) {
                return false;
            }
            for (android.net.Network network : cm.getAllNetworks()) {
                android.net.LinkProperties lp = cm.getLinkProperties(network);
                if (lp == null) {
                    continue;
                }
                for (android.net.LinkAddress la : lp.getLinkAddresses()) {
                    java.net.InetAddress address = la.getAddress();
                    if (address instanceof java.net.Inet4Address
                            && address.getHostAddress() != null
                            && address.getHostAddress().startsWith(HOME_LAN_PREFIX)) {
                        return true;
                    }
                }
            }
        } catch (Exception ignored) {
        }
        return false;
    }

    /** 儲存 alarms 入面搵「最近已過」(prev) 同「最快將到」(next) 一個。
     *  WatchBridge tile-state 同 NextAlarmWidgetProvider 共用（以前各抄一份 scan）。 */
    static PrevNext findPrevNext(Context context, long now) {
        JSONArray alarms = getAlarms(context);
        JSONObject prev = null;
        JSONObject next = null;
        long prevAt = 0L;
        long nextAt = Long.MAX_VALUE;
        for (int i = 0; i < alarms.length(); i++) {
            JSONObject alarm = alarms.optJSONObject(i);
            if (alarm == null) {
                continue;
            }
            if (alarm.optBoolean("disabled", false)) {
                continue;  // 停用嘅行位唔算 prev/next
            }
            long triggerAt = alarm.optLong("trigger_at_epoch_ms", 0L);
            if (triggerAt <= 0L) {
                continue;
            }
            if (triggerAt <= now && triggerAt >= prevAt) {
                prev = alarm;
                prevAt = triggerAt;
            }
            if (triggerAt > now && triggerAt < nextAt) {
                next = alarm;
                nextAt = triggerAt;
            }
        }
        // 長存嗰份都要問埋：plan 換咗之後 list 入面已經冇已響嗰個。
        // 齋要 label 一個欄位就夠 —— 三個出口（provider、widget、手錶 tile）
        // 都係淨讀 label。
        long storedAt = prefs(context).getLong(KEY_LAST_FIRED_AT, 0L);
        if (storedAt > prevAt && storedAt <= now) {
            try {
                JSONObject stored = new JSONObject();
                stored.put("label", prefs(context).getString(KEY_LAST_FIRED_LABEL, ""));
                stored.put("trigger_at_epoch_ms", storedAt);
                prev = stored;
                prevAt = storedAt;
            } catch (JSONException ignored) {
                // 砌唔成就用返 scan 嗰個，唔好連 next 都陪葬
            }
        }
        return new PrevNext(prev, prevAt, next, nextAt == Long.MAX_VALUE ? 0L : nextAt);
    }

    static final class PrevNext {
        final JSONObject prev;
        final long prevAt;
        final JSONObject next;
        final long nextAt;

        PrevNext(JSONObject prev, long prevAt, JSONObject next, long nextAt) {
            this.prev = prev;
            this.prevAt = prevAt;
            this.next = next;
            this.nextAt = nextAt;
        }
    }

    static void markAlarmFired(Context context, String id) {
        String targetId = id == null ? "" : id;
        if (targetId.isEmpty()) {
            return;
        }
        JSONArray current = getAlarms(context);
        JSONArray next = new JSONArray();
        long firedAt = System.currentTimeMillis();
        for (int i = 0; i < current.length(); i++) {
            JSONObject alarm = current.optJSONObject(i);
            if (alarm == null) {
                continue;
            }
            if (targetId.equals(alarm.optString("id"))) {
                try {
                    alarm.put("fired_at_epoch_ms", firedAt);
                } catch (JSONException ignored) {
                }
                // 響嗰刻另外長存一份 —— 呢度係唯一有齊時間同標籤嘅位
                // （AlarmReceiver 同手錶 dismiss 兩條路都經呢度入嚟）。
                // 時間用排程嗰個 trigger_at，同 findPrevNext 嘅口徑一致。
                long at = alarm.optLong("trigger_at_epoch_ms", firedAt);
                prefs(context).edit()
                        .putLong(KEY_LAST_FIRED_AT, at)
                        .putString(KEY_LAST_FIRED_LABEL, alarm.optString("label", ""))
                        .apply();
            }
            next.put(alarm);
        }
        prefs(context).edit().putString(KEY_ALARMS, next.toString()).apply();
        NextAlarmProvider.notifyChanged(context);     // 響咗＝Prev／Next 都變
    }

    static void clear(Context context) {
        SharedPreferences preferences = prefs(context);
        SharedPreferences.Editor editor = preferences.edit()
                .remove(KEY_ALARMS)
                .remove(KEY_PLAN_DATE)
                .remove(KEY_ROSTER_CODE)
                .remove(KEY_MEAL_PLAN_TEXT)
                .remove(KEY_MEAL_PLAN_JSON)
                .remove(KEY_MEAL_PLAN_JSON_DATE)
                .remove(KEY_MEAL_PLAN_JSON_VERSION)
                .remove(KEY_SCHEDULE_GRID_VARIANTS)
                .remove(KEY_LAST_IMPORT_AT);
        for (String key : preferences.getAll().keySet()) {
            if (key.startsWith(KEY_MEAL_PLAN_JSON_BY_DATE_PREFIX)
                    || key.startsWith(KEY_MEAL_PLAN_JSON_VERSION_BY_DATE_PREFIX)) {
                editor.remove(key);
            }
        }
        editor.apply();
        NextAlarmProvider.notifyChanged(context);
    }

    private static SharedPreferences prefs(Context context) {
        return context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    private static String normalizeDateKey(String dateIso) {
        String value = dateIso == null ? "" : dateIso.trim();
        if (!value.matches("\\d{4}-\\d{2}-\\d{2}")) {
            return "";
        }
        return value;
    }
}
