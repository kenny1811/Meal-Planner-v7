package com.example.oneshotalarm.watch;

import android.content.ComponentName;
import android.content.Context;
import android.content.SharedPreferences;
import android.util.Log;

import androidx.wear.watchface.complications.datasource.ComplicationDataSourceUpdateRequester;

import org.json.JSONArray;
import org.json.JSONObject;

import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

final class WatchScheduleDisplayState {
    private static final String TAG = "ShiftAlarmWatch";

    private WatchScheduleDisplayState() {
    }

    static void refreshFromCacheAndRequest(Context context) {
        refreshFromCache(context);
        requestAlarmComplicationUpdates(context);
    }

    static void refreshFromCache(Context context) {
        SharedPreferences prefs = context.getSharedPreferences(
                AlarmScheduleState.PREFS,
                Context.MODE_PRIVATE
        );
        JSONArray rows = parseRows(prefs.getString(AlarmScheduleState.KEY_SCHEDULE_ITEMS_JSON, "[]"));
        long now = System.currentTimeMillis();
        JSONObject prev = null;
        JSONObject next = null;
        long prevAt = 0L;
        long nextAt = Long.MAX_VALUE;

        for (int i = 0; i < rows.length(); i++) {
            JSONObject row = rows.optJSONObject(i);
            if (row == null) {
                continue;
            }
            long at = row.optLong("at", 0L);
            if (at <= 0L) {
                continue;
            }
            if (at <= now && at >= prevAt) {
                prev = row;
                prevAt = at;
            }
            if (at > now && at < nextAt) {
                next = row;
                nextAt = at;
            }
        }

        SharedPreferences.Editor editor = prefs.edit()
                .putLong(AlarmScheduleState.KEY_UPDATED_AT, now);
        putRow(editor, true, prev, prevAt);
        putRow(editor, false, next, nextAt == Long.MAX_VALUE ? 0L : nextAt);
        editor.apply();
        Log.d(TAG, "Refreshed watch prev/next from cached schedule");
    }

    static void requestAlarmComplicationUpdates(Context context) {
        requestAlarmComplicationUpdate(context, PrevAlarmComplicationDataSourceService.class);
        requestAlarmComplicationUpdate(context, NextAlarmComplicationDataSourceService.class);
        requestAlarmComplicationUpdate(context, PrevAlarmLabelLine1ComplicationDataSourceService.class);
        requestAlarmComplicationUpdate(context, PrevAlarmLabelLine2ComplicationDataSourceService.class);
        requestAlarmComplicationUpdate(context, NextAlarmLabelLine1ComplicationDataSourceService.class);
        requestAlarmComplicationUpdate(context, NextAlarmLabelLine2ComplicationDataSourceService.class);
    }

    private static void putRow(SharedPreferences.Editor editor, boolean prev, JSONObject row, long at) {
        if (row == null || at <= 0L) {
            editor.putString(prev ? AlarmScheduleState.KEY_PREV_TIME : AlarmScheduleState.KEY_NEXT_TIME, "--:--")
                    .putString(prev ? AlarmScheduleState.KEY_PREV_DATE : AlarmScheduleState.KEY_NEXT_DATE, "")
                    .putString(prev ? AlarmScheduleState.KEY_PREV_LABEL : AlarmScheduleState.KEY_NEXT_LABEL, "沒有資料")
                    .putLong(prev ? AlarmScheduleState.KEY_PREV_AT : AlarmScheduleState.KEY_NEXT_AT, 0L);
            return;
        }
        String label = row.optString("content", "").trim();
        if (label.isEmpty()) {
            label = "鬧鐘";
        }
        editor.putString(prev ? AlarmScheduleState.KEY_PREV_TIME : AlarmScheduleState.KEY_NEXT_TIME, format("HH:mm", at))
                .putString(prev ? AlarmScheduleState.KEY_PREV_DATE : AlarmScheduleState.KEY_NEXT_DATE, format("dd/MM EEE", at))
                .putString(prev ? AlarmScheduleState.KEY_PREV_LABEL : AlarmScheduleState.KEY_NEXT_LABEL, label)
                .putLong(prev ? AlarmScheduleState.KEY_PREV_AT : AlarmScheduleState.KEY_NEXT_AT, at);
    }

    private static String format(String pattern, long at) {
        return new SimpleDateFormat(pattern, Locale.getDefault()).format(new Date(at));
    }

    private static JSONArray parseRows(String raw) {
        try {
            return new JSONArray(raw == null ? "[]" : raw);
        } catch (Exception ignored) {
            return new JSONArray();
        }
    }

    private static void requestAlarmComplicationUpdate(Context context, Class<?> serviceClass) {
        try {
            ComplicationDataSourceUpdateRequester.create(
                    context,
                    new ComponentName(context, serviceClass)
            ).requestUpdateAll();
        } catch (Exception e) {
            Log.e(TAG, "Request alarm complication update failed", e);
        }
    }
}
