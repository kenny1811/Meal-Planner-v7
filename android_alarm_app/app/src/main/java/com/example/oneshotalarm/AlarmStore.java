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
    private static final String KEY_ALARMS = "alarms_json";
    private static final String KEY_PLAN_DATE = "plan_date";
    private static final String KEY_ROSTER_CODE = "roster_code";
    private static final String KEY_AUTO_SYNC_SERVER = "auto_sync_server_url";
    private static final String KEY_AUTO_SYNC_DEVICE = "auto_sync_device_id";
    private static final String KEY_AUTO_SYNC_LAST_ID = "auto_sync_last_id";
    private static final String KEY_MEAL_PLAN_TEXT = "meal_plan_text";
    private static final String KEY_MEAL_PLAN_JSON = "meal_plan_json";
    private static final String KEY_MEAL_PLAN_JSON_DATE = "meal_plan_json_date";
    private static final String KEY_MEAL_PLAN_JSON_VERSION = "meal_plan_json_version";
    private static final String KEY_MEAL_PLAN_JSON_BY_DATE_PREFIX = "meal_plan_json_";
    private static final String KEY_MEAL_PLAN_JSON_VERSION_BY_DATE_PREFIX = "meal_plan_json_version_";
    private static final String KEY_LAST_IMPORT_AT = "last_import_at_epoch_ms";
    private static final String KEY_WATCH_ALARM_ENABLED = "watch_alarm_enabled";
    private static final String KEY_SCHEDULE_GRID_VARIANTS = "schedule_grid_variants_json";

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

    static long getCleanupAt(Context context) {
        return 0L;
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

    static void saveMealPlanText(Context context, String text) {
        prefs(context).edit().putString(KEY_MEAL_PLAN_TEXT, text == null ? "" : text).apply();
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

    static void saveAutoSyncConfig(Context context, String serverUrl, String deviceId) {
        String normalizedDevice = (deviceId == null || deviceId.trim().isEmpty())
                ? "default"
                : deviceId.trim();
        prefs(context).edit()
                .putString(KEY_AUTO_SYNC_SERVER, DEFAULT_AUTO_SYNC_SERVER)
                .putString(KEY_AUTO_SYNC_DEVICE, normalizedDevice)
                .apply();
    }

    static String getAutoSyncServerUrl(Context context) {
        return DEFAULT_AUTO_SYNC_SERVER;
    }

    static String getConfiguredAutoSyncServerUrl(Context context) {
        return DEFAULT_AUTO_SYNC_SERVER;
    }

    static String[] getAutoSyncServerCandidates(Context context) {
        return new String[]{DEFAULT_AUTO_SYNC_SERVER};
    }

    static String getAutoSyncServerUrl(Context context, boolean fallbackToLoopback) {
        return DEFAULT_AUTO_SYNC_SERVER;
    }

    static String getAutoSyncDeviceId(Context context) {
        return prefs(context).getString(KEY_AUTO_SYNC_DEVICE, "default");
    }

    static long getAutoSyncLastSyncId(Context context) {
        return prefs(context).getLong(KEY_AUTO_SYNC_LAST_ID, 0L);
    }

    static void setAutoSyncLastSyncId(Context context, long syncId) {
        prefs(context).edit().putLong(KEY_AUTO_SYNC_LAST_ID, syncId).apply();
    }

    static void removeAlarm(Context context, String id) {
        String targetId = id == null ? "" : id;
        JSONArray current = getAlarms(context);
        JSONArray next = new JSONArray();
        for (int i = 0; i < current.length(); i++) {
            JSONObject alarm = current.optJSONObject(i);
            if (alarm == null) {
                continue;
            }
            if (!targetId.equals(alarm.optString("id"))) {
                next.put(alarm);
            }
        }
        prefs(context).edit().putString(KEY_ALARMS, next.toString()).apply();
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
            }
            next.put(alarm);
        }
        prefs(context).edit().putString(KEY_ALARMS, next.toString()).apply();
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

    private static String normalizeServerUrl(String serverUrl) {
        return DEFAULT_AUTO_SYNC_SERVER;
    }
}
