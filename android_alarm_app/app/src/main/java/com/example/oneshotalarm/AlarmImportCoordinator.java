package com.example.oneshotalarm;

import android.content.Context;
import android.util.Log;
import android.widget.Toast;

import org.json.JSONArray;
import org.json.JSONObject;

final class AlarmImportCoordinator {
    private static final String TAG = "OneShotAlarmImport";

    private AlarmImportCoordinator() {
    }

    static void importPlanData(Context context, JSONObject data, boolean notify) {
        if (data == null) {
            return;
        }
        if (!AlarmScheduler.canScheduleExactAlarm(context)) {
            if (notify) {
                Toast.makeText(
                        context,
                        "請先允許精準鬧鐘權限，再同步一次",
                        Toast.LENGTH_LONG
                ).show();
                AlarmScheduler.requestExactAlarmPermission(context);
            }
            return;
        }
        JSONArray alarms = data.optJSONArray("alarms");
        if (alarms == null) {
            alarms = new JSONArray();
        }
        String date = data.optString("date", "");
        String rosterCode = data.optString("roster_code", "");
        String mealPlanText = extractMealPlanText(data);
        AlarmStore.saveMealPlanText(context, mealPlanText);
        AlarmScheduler.schedulePlan(context, alarms, 0L, date, rosterCode);
        AlarmStore.markLastImportNow(context);
        if (notify) {
            String message = "已同步 " + AlarmStore.getAlarms(context).length() + " 個鬧鐘";
            if (!mealPlanText.isEmpty()) {
                message += "，及餐單內容";
            }
            Toast.makeText(context, message, Toast.LENGTH_LONG).show();
        }
        Log.d(TAG, "Imported alarm plan: " + AlarmStore.getAlarms(context).length());
    }

    private static String extractMealPlanText(JSONObject data) {
        String text = data.optString("meal_plan_text", "").trim();
        if (!text.isEmpty()) {
            return text;
        }

        JSONArray lines = data.optJSONArray("meal_lines");
        if (lines == null) {
            lines = data.optJSONArray("meal_plan_lines");
        }
        if (lines == null) {
            String raw = data.optString("meal_plan_raw", "").trim();
            if (!raw.isEmpty()) {
                return raw;
            }
        }
        if (lines != null) {
            return formatMealLines(lines);
        }

        JSONObject mealObj = data.optJSONObject("meal_plan");
        if (mealObj != null) {
            return formatMealPlanObject(mealObj);
        }
        mealObj = data.optJSONObject("menu");
        if (mealObj != null) {
            return formatMealPlanObject(mealObj);
        }

        return "";
    }

    private static String formatMealPlanObject(JSONObject mealObj) {
        StringBuilder builder = new StringBuilder();
        String title = mealObj.optString("title", "").trim();
        String summary = mealObj.optString("summary", "").trim();
        String note = mealObj.optString("notes", "").trim();
        if (!title.isEmpty()) {
            builder.append(title).append("\n");
        }
        if (!summary.isEmpty()) {
            builder.append(summary).append("\n");
        }
        if (!note.isEmpty()) {
            builder.append(note).append("\n");
        }
        JSONArray items = mealObj.optJSONArray("items");
        if (items == null) {
            items = mealObj.optJSONArray("meal_items");
        }
        if (items != null) {
            if (builder.length() > 0) {
                builder.append("\n");
            }
            builder.append(formatMealLines(items));
        } else {
            String fallback = mealObj.optString("text", "").trim();
            if (!fallback.isEmpty()) {
                if (builder.length() > 0) {
                    builder.append("\n");
                }
                builder.append(fallback);
            }
        }
        return builder.toString().trim();
    }

    private static String formatMealLines(JSONArray lines) {
        StringBuilder builder = new StringBuilder();
        for (int i = 0; i < lines.length(); i++) {
            String itemText = mealLineToText(lines.opt(i));
            if (itemText.isEmpty()) {
                continue;
            }
            if (builder.length() > 0) {
                builder.append("\n");
            }
            builder.append("- ").append(itemText);
        }
        return builder.toString().trim();
    }

    private static String mealLineToText(Object value) {
        if (value == null) {
            return "";
        }
        if (value instanceof String) {
            return ((String) value).trim();
        }
        if (!(value instanceof JSONObject)) {
            return "";
        }
        JSONObject item = (JSONObject) value;
        String[] nameKeys = new String[]{
                "name",
                "item",
                "dish",
                "meal",
                "title"
        };
        String name = "";
        for (String key : nameKeys) {
            name = item.optString(key, "").trim();
            if (!name.isEmpty()) {
                break;
            }
        }
        String amount = item.optString("amount", "").trim();
        String unit = item.optString("unit", "").trim();
        String nutrition = item.optString("nutrition", "").trim();
        String text = item.optString("text", "").trim();
        if (name.isEmpty() && text.isEmpty()) {
            return "";
        }
        if (name.isEmpty()) {
            return text;
        }
        StringBuilder builder = new StringBuilder(name);
        if (!amount.isEmpty()) {
            builder.append(" ").append(amount);
        }
        if (!unit.isEmpty() && !amount.isEmpty()) {
            builder.append(unit);
        } else if (!unit.isEmpty() && amount.isEmpty()) {
            builder.append(" ").append(unit);
        }
        if (!nutrition.isEmpty()) {
            builder.append("（").append(nutrition).append("）");
        }
        return builder.toString().trim();
    }
}
