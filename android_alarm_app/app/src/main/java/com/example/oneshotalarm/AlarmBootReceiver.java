package com.example.oneshotalarm;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.util.Log;

public class AlarmBootReceiver extends BroadcastReceiver {
    private static final String TAG = "OneShotAlarmBoot";

    @Override
    public void onReceive(Context context, Intent intent) {
        String action = intent == null ? "" : intent.getAction();
        if (!Intent.ACTION_BOOT_COMPLETED.equals(action)
                && !Intent.ACTION_LOCKED_BOOT_COMPLETED.equals(action)
                && !Intent.ACTION_MY_PACKAGE_REPLACED.equals(action)) {
            return;
        }
        try {
            AlarmScheduler.rescheduleStoredPlan(context);
            AlarmAutoSyncReceiver.schedulePolling(context);
        } catch (Exception e) {
            Log.w(TAG, "Restore alarms after boot failed", e);
        }
    }
}
