package com.example.oneshotalarm;

import android.content.Context;
import android.net.Uri;
import android.util.Log;

import org.json.JSONArray;
import org.json.JSONObject;

import java.text.SimpleDateFormat;
import java.util.Calendar;
import java.util.Locale;

final class ScheduleGridAutoImporter {
    private static final String TAG = "ScheduleGridAutoImport";
    private static final int HTTP_READ_TIMEOUT_MS = 12000;

    private ScheduleGridAutoImporter() {
    }

    static ImportResult importFromPc(Context context) throws Exception {
        if (!AlarmScheduler.canScheduleExactAlarm(context)) {
            return new ImportResult(false, 0, "", "", "no exact alarm permission");
        }
        try {
            return importAllVariants(context);
        } catch (Exception e) {
            Log.w(TAG, "Auto import failed", e);
            String message = e.getMessage() == null || e.getMessage().trim().isEmpty()
                    ? "no usable server" : e.getMessage();
            return new ImportResult(false, 0, "", "", message);
        }
    }

    private static ImportResult importAllVariants(Context context) throws Exception {
        String body = ApiClient.request(
                context, "GET", "/api/maint/sheets/schedule_grid/export-all", null, HTTP_READ_TIMEOUT_MS);
        JSONObject response = new JSONObject(body);
        if (!response.optBoolean("ok", false)) {
            return new ImportResult(false, 0, "", "", "all variants response not ok");
        }
        JSONArray variants = response.optJSONArray("variants");
        if (variants == null || variants.length() == 0) {
            return new ImportResult(false, 0, "", "", "no schedule variants");
        }
        String currentRoster = response.optString("current_roster_code", "");
        JSONArray storedVariants = new JSONArray();
        ParsedScheduleGrid selected = null;
        String selectedRoster = "";
        int totalAlarmCount = 0;
        for (int i = 0; i < variants.length(); i++) {
            JSONObject item = variants.optJSONObject(i);
            if (item == null) {
                continue;
            }
            String rosterCode = item.optString("roster_code", "");
            ParsedScheduleGrid parsed = parse(item);
            if (parsed.alarms.length() == 0) {
                continue;
            }
            JSONObject stored = new JSONObject();
            stored.put("plan_date", parsed.planDate);
            stored.put("roster_code", rosterCode);
            stored.put("alarm_count", parsed.alarms.length());
            stored.put("alarms", parsed.alarms);
            storedVariants.put(stored);
            totalAlarmCount += parsed.alarms.length();
            if (item.optBoolean("is_current", false)
                    || (!currentRoster.trim().isEmpty() && rosterCode.equals(currentRoster.trim()))) {
                selected = parsed;
                selectedRoster = rosterCode;
            }
        }
        if (storedVariants.length() == 0) {
            return new ImportResult(false, 0, "", "", "no usable schedule variants");
        }
        if (selected == null) {
            String missingRoster = currentRoster == null ? "" : currentRoster.trim();
            String message = missingRoster.isEmpty()
                    ? "搵唔到當日更碼行位表"
                    : "搵唔到 " + missingRoster + " 行位表";
            return new ImportResult(false, 0, "", missingRoster, message);
        }
        AlarmStore.saveScheduleGridVariants(context, storedVariants);
        AlarmScheduler.schedulePlan(context, selected.alarms, 0L, selected.planDate, selectedRoster);
        AlarmStore.markLastImportNow(context);
        Log.d(TAG, "Imported " + storedVariants.length() + " variants; active " + selectedRoster);
        return new ImportResult(
                true,
                selected.alarms.length(),
                selected.planDate,
                selectedRoster,
                "ok variants=" + storedVariants.length(),
                storedVariants.length(),
                totalAlarmCount
        );
    }

    /** 一個 variant（電腦讀 sqlite 出嘅 alarms）→ 電話嘅鬧鐘 plan。 */
    private static ParsedScheduleGrid parse(JSONObject variant) throws Exception {
        String rosterCode = variant.optString("roster_code", "");
        String planDate = normalizeDate(variant.optString("target_date", ""));
        if (planDate.isEmpty()) {
            planDate = normalizeDate(variant.optString("effective_date", ""));
        }
        if (planDate.isEmpty()) {
            planDate = todayIso();
        }

        JSONArray alarms = new JSONArray();
        JSONArray items = variant.optJSONArray("alarms");
        int count = items == null ? 0 : items.length();
        for (int i = 0; i < count; i++) {
            JSONObject item = items.optJSONObject(i);
            if (item == null) {
                continue;
            }
            String time = item.optString("time", "").trim();
            String label = item.optString("label", "").trim();
            if (time.isEmpty() || label.isEmpty()) {
                continue;
            }
            long triggerAt = triggerAt(planDate, time);
            JSONObject alarm = new JSONObject();
            alarm.put("id", "auto-grid-" + planDate + "-" + Uri.encode(time) + "-" + i);
            alarm.put("label", label);
            alarm.put("trigger_at_epoch_ms", triggerAt);
            alarm.put("trigger_at", formatIso(triggerAt));
            // 停用嘅行位照樣落電話（要見到先撳得返啟用），但唔會排鬧鐘。
            alarm.put("disabled", item.optBoolean("disabled", false));
            alarms.put(alarm);
        }
        return new ParsedScheduleGrid(alarms, planDate, rosterCode);
    }

    private static String normalizeDate(String raw) {
        String value = raw == null ? "" : raw.trim();
        if (value.isEmpty()) {
            return "";
        }
        String[] patterns = new String[]{"yyyy-MM-dd", "dd/MM/yyyy", "d/M/yyyy", "dd-MM-yyyy", "d-M-yyyy"};
        for (String pattern : patterns) {
            try {
                SimpleDateFormat input = new SimpleDateFormat(pattern, Locale.US);
                input.setLenient(false);
                return new SimpleDateFormat("yyyy-MM-dd", Locale.US).format(input.parse(value));
            } catch (java.text.ParseException ignored) {
            }
        }
        return "";
    }

    private static long triggerAt(String planDate, String time) {
        String[] dateParts = planDate.split("-");
        String[] timeParts = time.trim().split(":");
        // 30 小時制：24:00–29:59 即係翌日凌晨（27:56 = 第二日 03:56）。
        int hour = Integer.parseInt(timeParts[0]);
        int dayOffset = hour >= 24 ? 1 : 0;
        if (hour >= 24) {
            hour -= 24;
        }
        Calendar calendar = Calendar.getInstance();
        calendar.set(Calendar.YEAR, Integer.parseInt(dateParts[0]));
        calendar.set(Calendar.MONTH, Integer.parseInt(dateParts[1]) - 1);
        calendar.set(Calendar.DAY_OF_MONTH, Integer.parseInt(dateParts[2]) + dayOffset);
        calendar.set(Calendar.HOUR_OF_DAY, hour);
        calendar.set(Calendar.MINUTE, Integer.parseInt(timeParts[1]));
        calendar.set(Calendar.SECOND, 0);
        calendar.set(Calendar.MILLISECOND, 0);
        return calendar.getTimeInMillis();
    }

    private static String todayIso() {
        return new SimpleDateFormat("yyyy-MM-dd", Locale.US).format(System.currentTimeMillis());
    }

    private static String formatIso(long millis) {
        return new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ssZ", Locale.US).format(millis);
    }

    static final class ImportResult {
        final boolean ok;
        final int alarmCount;
        final String planDate;
        final String rosterCode;
        final String message;
        final int variantCount;
        final int totalAlarmCount;

        ImportResult(boolean ok, int alarmCount, String planDate, String rosterCode, String message) {
            this(ok, alarmCount, planDate, rosterCode, message, 0, alarmCount);
        }

        ImportResult(
                boolean ok,
                int alarmCount,
                String planDate,
                String rosterCode,
                String message,
                int variantCount,
                int totalAlarmCount
        ) {
            this.ok = ok;
            this.alarmCount = alarmCount;
            this.planDate = planDate == null ? "" : planDate;
            this.rosterCode = rosterCode == null ? "" : rosterCode;
            this.message = message == null ? "" : message;
            this.variantCount = variantCount;
            this.totalAlarmCount = totalAlarmCount;
        }
    }

    private static final class ParsedScheduleGrid {
        final JSONArray alarms;
        final String planDate;
        final String rosterCode;

        ParsedScheduleGrid(JSONArray alarms, String planDate, String rosterCode) {
            this.alarms = alarms == null ? new JSONArray() : alarms;
            this.planDate = planDate == null ? "" : planDate;
            this.rosterCode = rosterCode == null ? "" : rosterCode;
        }
    }
}
