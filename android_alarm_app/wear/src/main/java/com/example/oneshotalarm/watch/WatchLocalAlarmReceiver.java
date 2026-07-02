package com.example.oneshotalarm.watch;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.util.Log;

public class WatchLocalAlarmReceiver extends BroadcastReceiver {
    private static final String TAG = "ShiftAlarmWatch";
    static final String ACTION_STOP_FROM_NOTIFICATION =
            "com.example.oneshotalarm.watch.ACTION_STOP_FROM_NOTIFICATION";

    @Override
    public void onReceive(Context context, Intent intent) {
        String action = intent == null ? "" : intent.getAction();
        if (Intent.ACTION_BOOT_COMPLETED.equals(action)
                || Intent.ACTION_LOCKED_BOOT_COMPLETED.equals(action)
                || Intent.ACTION_MY_PACKAGE_REPLACED.equals(action)) {
            WatchLocalAlarmScheduler.scheduleFromCachedState(context);
            return;
        }
        if (ACTION_STOP_FROM_NOTIFICATION.equals(action)) {
            String alarmId = intent.getStringExtra(WatchAlarmActivity.EXTRA_ALARM_ID);
            Log.d(TAG, "Stopping watch alarm from notification: " + alarmId);
            WatchDismissBridge.sendDismiss(context, alarmId);
            WatchAlarmService.stop(context);
            Intent dismissIntent = new Intent(WatchAlarmActivity.ACTION_DISMISS_LOCAL);
            dismissIntent.setPackage(context.getPackageName());
            context.sendBroadcast(dismissIntent);
            WatchScheduleDisplayState.refreshFromCacheAndRequest(context);
            return;
        }
        if (!WatchLocalAlarmScheduler.ACTION_FIRE.equals(action)) {
            return;
        }
        Log.d(TAG, "Local watch alarm receiver fired");
        String id = intent.getStringExtra(WatchLocalAlarmScheduler.EXTRA_ALARM_ID);
        String time = intent.getStringExtra(WatchLocalAlarmScheduler.EXTRA_TIME);
        String label = intent.getStringExtra(WatchLocalAlarmScheduler.EXTRA_LABEL);
        if (time == null || time.trim().isEmpty()) {
            time = "--:--";
        }
        if (label == null || label.trim().isEmpty()) {
            label = "鬧鐘";
        }
        String alarmKey = (id == null ? "" : id) + "\n" + time + "\n" + label;
        WatchAlarmService.start(context, alarmKey);
        WatchScheduleDisplayState.refreshFromCacheAndRequest(context);
        Log.d(TAG, "Requested watch alarm notification: " + time + " " + label);
    }
}
