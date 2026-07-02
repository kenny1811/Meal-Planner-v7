package com.example.oneshotalarm.watch;

import android.app.AlarmManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Build;
import android.util.Log;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;

final class WatchLocalAlarmScheduler {
    static final String ACTION_FIRE = "com.example.oneshotalarm.watch.ACTION_LOCAL_ALARM";
    static final String EXTRA_ALARM_ID = "alarm_id";
    static final String EXTRA_TIME = "time";
    static final String EXTRA_LABEL = "label";
    static final String EXTRA_AT = "at";

    private static final String TAG = "ShiftAlarmWatch";
    private static final String KEY_SCHEDULED_IDS = "local_alarm_ids";

    private WatchLocalAlarmScheduler() {
    }

    static void scheduleFromCachedState(Context context) {
        SharedPreferences prefs = context.getSharedPreferences(AlarmScheduleState.PREFS, Context.MODE_PRIVATE);
        scheduleRows(context, prefs.getString(AlarmScheduleState.KEY_SCHEDULE_ITEMS_JSON, "[]"));
    }

    static void scheduleRows(Context context, String rowsJson) {
        cancelScheduledAlarms(context);
        long now = System.currentTimeMillis();
        JSONArray rows = parseRows(rowsJson);
        ArrayList<String> scheduledIds = new ArrayList<>();
        for (int i = 0; i < rows.length(); i++) {
            JSONObject row = rows.optJSONObject(i);
            if (row == null) {
                continue;
            }
            long at = row.optLong("at", 0L);
            if (at <= now) {
                continue;
            }
            String label = row.optString("content", "鬧鐘").trim();
            if (label.isEmpty()) {
                label = "鬧鐘";
            }
            String id = row.optString("id", "").trim();
            if (id.isEmpty()) {
                id = "watch-" + at + "-" + label.hashCode();
            }
            String time = row.optString("time", "--:--");
            scheduleOne(context, id, time, label, at);
            scheduledIds.add(id);
        }
        context.getSharedPreferences(AlarmScheduleState.PREFS, Context.MODE_PRIVATE)
                .edit()
                .putString(KEY_SCHEDULED_IDS, new JSONArray(scheduledIds).toString())
                .apply();
        Log.d(TAG, "Scheduled local watch alarms: " + scheduledIds.size());
    }

    static void cancelScheduledAlarms(Context context) {
        SharedPreferences prefs = context.getSharedPreferences(AlarmScheduleState.PREFS, Context.MODE_PRIVATE);
        JSONArray ids = parseRows(prefs.getString(KEY_SCHEDULED_IDS, "[]"));
        for (int i = 0; i < ids.length(); i++) {
            String id = ids.optString(i, "");
            if (!id.isEmpty()) {
                cancelAlarm(context, id);
            }
        }
        prefs.edit().remove(KEY_SCHEDULED_IDS).apply();
    }

    static void cancelAlarm(Context context, String id) {
        PendingIntent pendingIntent = alarmPendingIntent(context, id, "--:--", "鬧鐘", 0L, PendingIntent.FLAG_NO_CREATE);
        if (pendingIntent != null) {
            alarmManager(context).cancel(pendingIntent);
            pendingIntent.cancel();
        }
    }

    private static void scheduleOne(Context context, String id, String time, String label, long at) {
        PendingIntent pendingIntent = alarmPendingIntent(context, id, time, label, at, PendingIntent.FLAG_UPDATE_CURRENT);
        AlarmManager manager = alarmManager(context);
        PendingIntent showIntent = alarmActivityPendingIntent(
                context,
                id,
                time,
                label,
                PendingIntent.FLAG_UPDATE_CURRENT
        );
        try {
            manager.setAlarmClock(new AlarmManager.AlarmClockInfo(at, showIntent), pendingIntent);
            Log.d(TAG, "Scheduled watch alarm clock: " + time + " " + label);
            return;
        } catch (SecurityException e) {
            Log.w(TAG, "Watch alarm clock unavailable; using exact fallback", e);
        }
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S && manager.canScheduleExactAlarms()) {
                manager.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, pendingIntent);
                return;
            }
            if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S) {
                manager.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, pendingIntent);
                return;
            }
        } catch (SecurityException e) {
            Log.w(TAG, "Exact watch alarm unavailable; using inexact fallback", e);
        }
        manager.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, pendingIntent);
    }

    static void scheduleImmediate(Context context, String id, String time, String label) {
        String alarmId = id == null || id.trim().isEmpty()
                ? "watch-immediate-" + System.currentTimeMillis()
                : id.trim();
        String alarmTime = time == null || time.trim().isEmpty() ? "--:--" : time;
        String alarmLabel = label == null || label.trim().isEmpty() ? "鬧鐘" : label;
        scheduleOne(context, alarmId, alarmTime, alarmLabel, System.currentTimeMillis() + 1000L);
    }

    private static PendingIntent alarmPendingIntent(
            Context context,
            String id,
            String time,
            String label,
            long at,
            int extraFlags
    ) {
        Intent intent = new Intent(context, WatchLocalAlarmReceiver.class);
        intent.setAction(ACTION_FIRE);
        intent.putExtra(EXTRA_ALARM_ID, id == null ? "" : id);
        intent.putExtra(EXTRA_TIME, time == null ? "--:--" : time);
        intent.putExtra(EXTRA_LABEL, label == null ? "鬧鐘" : label);
        intent.putExtra(EXTRA_AT, at);
        return PendingIntent.getBroadcast(
                context,
                requestCodeFor(id),
                intent,
                immutableFlags(extraFlags)
        );
    }

    private static PendingIntent alarmActivityPendingIntent(
            Context context,
            String id,
            String time,
            String label,
            int extraFlags
    ) {
        Intent intent = new Intent(context, WatchAlarmActivity.class);
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        intent.putExtra(WatchAlarmActivity.EXTRA_ALARM_ID, id == null ? "" : id);
        intent.putExtra(WatchAlarmActivity.EXTRA_TIME, time == null ? "--:--" : time);
        intent.putExtra(WatchAlarmActivity.EXTRA_LABEL, label == null ? "鬧鐘" : label);
        return PendingIntent.getActivity(
                context,
                requestCodeFor(id),
                intent,
                immutableFlags(extraFlags)
        );
    }

    private static JSONArray parseRows(String raw) {
        try {
            return new JSONArray(raw == null ? "[]" : raw);
        } catch (Exception ignored) {
            return new JSONArray();
        }
    }

    private static AlarmManager alarmManager(Context context) {
        return (AlarmManager) context.getSystemService(Context.ALARM_SERVICE);
    }

    private static int requestCodeFor(String id) {
        return 9100 + ((String.valueOf(id).hashCode() & 0x7fffffff) % 100000);
    }

    private static int immutableFlags(int flags) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            return flags | PendingIntent.FLAG_IMMUTABLE;
        }
        return flags;
    }
}
