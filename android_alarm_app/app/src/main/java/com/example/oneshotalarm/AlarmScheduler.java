package com.example.oneshotalarm;

import android.app.AlarmManager;
import android.app.ActivityOptions;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;

import org.json.JSONArray;
import org.json.JSONObject;

final class AlarmScheduler {
    static final String ACTION_ALARM = "com.example.oneshotalarm.ACTION_ALARM";
    static final String EXTRA_ALARM_ID = "alarm_id";
    static final String EXTRA_ALARM_LABEL = "alarm_label";
    static final String EXTRA_ALARM_TRIGGER_AT = "alarm_trigger_at";

    private AlarmScheduler() {
    }

    static boolean canScheduleExactAlarm(Context context) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S) {
            return true;
        }
        AlarmManager alarmManager = getAlarmManager(context);
        return alarmManager.canScheduleExactAlarms();
    }

    static void requestExactAlarmPermission(Context context) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            Intent intent = new Intent(Settings.ACTION_REQUEST_SCHEDULE_EXACT_ALARM);
            intent.setData(Uri.parse("package:" + context.getPackageName()));
            context.startActivity(intent);
        }
    }

    static void requestFullScreenIntentPermission(Context context) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            Intent intent = new Intent(Settings.ACTION_MANAGE_APP_USE_FULL_SCREEN_INTENT);
            intent.setData(Uri.parse("package:" + context.getPackageName()));
            context.startActivity(intent);
        }
    }

    static void scheduleManual(Context context, long triggerAtMillis) {
        JSONArray alarms = new JSONArray();
        try {
            JSONObject alarm = new JSONObject();
            alarm.put("id", "manual-" + triggerAtMillis);
            alarm.put("label", "手動鬧鐘");
            alarm.put("trigger_at_epoch_ms", triggerAtMillis);
            alarms.put(alarm);
        } catch (Exception ignored) {
        }
        schedulePlan(context, alarms, 0L);
    }

    static void schedulePlan(Context context, JSONArray alarms, long cleanupAtMillis) {
        schedulePlan(
                context,
                alarms,
                cleanupAtMillis,
                AlarmStore.getPlanDate(context),
                AlarmStore.getRosterCode(context)
        );
    }

    static void schedulePlan(
            Context context,
            JSONArray alarms,
            long cleanupAtMillis,
            String planDate,
            String rosterCode
    ) {
        cancelScheduledAlarms(context);
        long now = System.currentTimeMillis();
        for (int i = 0; i < alarms.length(); i++) {
            JSONObject alarm = alarms.optJSONObject(i);
            if (alarm == null) {
                continue;
            }
            String id = alarm.optString("id", "alarm-" + i);
            String label = alarm.optString("label", "鬧鐘");
            long triggerAtMillis = alarm.optLong("trigger_at_epoch_ms", 0L);
            if (triggerAtMillis <= now) {
                continue;
            }
            scheduleAlarm(context, id, label, triggerAtMillis);
        }
        AlarmStore.savePlan(context, alarms, 0L, planDate, rosterCode);
        NextAlarmWidgetProvider.updateAll(context);
        WatchBridge.sendTileState(context);
    }

    static void rescheduleStoredPlan(Context context) {
        JSONArray alarms = AlarmStore.getAlarms(context);
        cancelScheduledAlarms(context);
        long now = System.currentTimeMillis();
        for (int i = 0; i < alarms.length(); i++) {
            JSONObject alarm = alarms.optJSONObject(i);
            if (alarm == null) {
                continue;
            }
            String id = alarm.optString("id", "alarm-" + i);
            String label = alarm.optString("label", "鬧鐘");
            long triggerAtMillis = alarm.optLong("trigger_at_epoch_ms", 0L);
            if (triggerAtMillis <= now) {
                continue;
            }
            scheduleAlarm(context, id, label, triggerAtMillis);
        }
    }

    private static void scheduleAlarm(Context context, String id, String label, long triggerAtMillis) {
        AlarmManager alarmManager = getAlarmManager(context);
        PendingIntent alarmIntent = alarmPendingIntent(context, id, label, triggerAtMillis, PendingIntent.FLAG_UPDATE_CURRENT);
        PendingIntent showIntent = activityPendingIntent(context, id, label, triggerAtMillis, PendingIntent.FLAG_UPDATE_CURRENT);

        AlarmManager.AlarmClockInfo alarmClockInfo =
                new AlarmManager.AlarmClockInfo(triggerAtMillis, showIntent);
        alarmManager.setAlarmClock(alarmClockInfo, alarmIntent);
    }

    static void cancelAll(Context context) {
        cancelScheduledAlarms(context);
        AlarmStore.clear(context);
        NextAlarmWidgetProvider.updateAll(context);
        WatchBridge.sendTileState(context);
    }

    static void cancelScheduledAlarms(Context context) {
        JSONArray alarms = AlarmStore.getAlarms(context);
        for (int i = 0; i < alarms.length(); i++) {
            JSONObject alarm = alarms.optJSONObject(i);
            if (alarm == null) {
                continue;
            }
            cancelAlarm(context, alarm.optString("id"), alarm.optString("label"));
        }
    }

    static void cancelAlarm(Context context, String id, String label) {
        PendingIntent existing = alarmPendingIntent(context, id, label, 0L, PendingIntent.FLAG_NO_CREATE);
        if (existing != null) {
            getAlarmManager(context).cancel(existing);
            existing.cancel();
        }
    }

    private static AlarmManager getAlarmManager(Context context) {
        return (AlarmManager) context.getSystemService(Context.ALARM_SERVICE);
    }

    static PendingIntent alarmPendingIntent(Context context, String id, String label, long triggerAtMillis, int extraFlags) {
        Intent intent = new Intent(context, AlarmReceiver.class);
        intent.setAction(ACTION_ALARM);
        intent.putExtra(EXTRA_ALARM_ID, id);
        intent.putExtra(EXTRA_ALARM_LABEL, label);
        intent.putExtra(EXTRA_ALARM_TRIGGER_AT, triggerAtMillis);
        return PendingIntent.getBroadcast(
                context,
                requestCodeFor(id),
                intent,
                immutableFlags(extraFlags)
        );
    }

    static PendingIntent activityPendingIntent(Context context, String id, String label, long triggerAtMillis, int extraFlags) {
        Intent intent = new Intent(context, AlarmActivity.class);
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        intent.putExtra(EXTRA_ALARM_ID, id);
        intent.putExtra(EXTRA_ALARM_LABEL, label);
        intent.putExtra(EXTRA_ALARM_TRIGGER_AT, triggerAtMillis);
        return PendingIntent.getActivity(
                context,
                requestCodeFor(id),
                intent,
                immutableFlags(extraFlags)
        );
    }

    static void sendAlarmActivity(Context context, String id, String label, long triggerAtMillis) {
        PendingIntent pendingIntent =
                activityPendingIntent(context, id, label, triggerAtMillis, PendingIntent.FLAG_UPDATE_CURRENT);
        try {
            pendingIntent.send();
        } catch (PendingIntent.CanceledException ignored) {
        }
    }

    private static int requestCodeFor(String id) {
        return 7100 + ((String.valueOf(id).hashCode() & 0x7fffffff) % 100000);
    }

    private static int immutableFlags(int flags) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            return flags | PendingIntent.FLAG_IMMUTABLE;
        }
        return flags;
    }

}
