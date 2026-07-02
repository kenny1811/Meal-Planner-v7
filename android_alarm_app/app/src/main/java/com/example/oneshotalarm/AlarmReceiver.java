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
        // 手錶已由 tile-state 自行本地排程同一個鬧鐘，唔再喺 fire-time push（避免雙重觸發同慳電）。
        // 只推送最新 tile-state，令手錶 prev/next 顯示同本地排程保持同步（亦作為排程漂移時嘅安全網）。
        WatchBridge.sendTileState(context);
    }
}
