package com.example.oneshotalarm;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

public class AlarmReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        String id = intent == null ? "" : intent.getStringExtra(AlarmScheduler.EXTRA_ALARM_ID);
        String label = intent == null ? "鬧鐘" : intent.getStringExtra(AlarmScheduler.EXTRA_ALARM_LABEL);
        long triggerAtMillis = intent == null ? 0L : intent.getLongExtra(AlarmScheduler.EXTRA_ALARM_TRIGGER_AT, 0L);
        if (label == null || label.trim().isEmpty()) {
            label = "鬧鐘";
        }
        AlarmStore.markAlarmFired(context, id);
        AlarmScheduler.cancelAlarm(context, id, label);
        NextAlarmWidgetProvider.updateAll(context);
        AlarmAlertService.start(context, id, label, triggerAtMillis);
        // 響鬧唔好推嘢上錶：手錶自己有同一份行位表、自己排程自己響。
    }
}
