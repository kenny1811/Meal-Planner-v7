package com.example.oneshotalarm;

import android.app.AlarmManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.util.Log;

import java.util.Calendar;

public final class AlarmAutoSyncReceiver extends BroadcastReceiver {
    private static final String TAG = "OneShotAutoSync";
    private static final String ACTION_DAILY_IMPORT = "com.example.oneshotalarm.ACTION_DAILY_IMPORT";
    private static final String EXTRA_DAILY_IMPORT_SLOT = "daily_import_slot";
    private static final int REQUEST_CODE_DAILY_IMPORT_0500 = 8500;
    private static final int REQUEST_CODE_DAILY_IMPORT_0530 = 8530;

    @Override
    public void onReceive(Context context, Intent intent) {
        String action = intent == null ? null : intent.getAction();
        if (ACTION_DAILY_IMPORT.equals(action)) {
            int slot = intent.getIntExtra(EXTRA_DAILY_IMPORT_SLOT, 0);
            new Thread(new Runnable() {
                @Override
                public void run() {
                    try {
                        ScheduleGridAutoImporter.importFromPc(context);
                    } catch (Exception e) {
                        Log.w(TAG, "Daily schedule_grid import failed", e);
                    } finally {
                        scheduleDailyImportSlot(context, slot);
                    }
                }
            }).start();
            return;
        }
    }

    static void schedulePolling(Context context) {
        scheduleDailyImports(context);
    }

    /**
     * 補跑今日錯過咗嘅每日匯入。
     * 例如手機喺 05:00 / 05:30 兩棍都關咗機，開機後今日就唔會再自動匯入，要等聽日。
     * 呢個方法喺開機後檢查：如果已過今日 05:00 但今日 05:00 之後仲未成功匯入過，就即刻補跑一次，
     * 令手機同手錶唔使等到聽日、亦唔使人手插手。
     */
    static void catchUpMissedDailyImport(Context context) {
        Calendar todayFive = Calendar.getInstance();
        todayFive.set(Calendar.HOUR_OF_DAY, 5);
        todayFive.set(Calendar.MINUTE, 0);
        todayFive.set(Calendar.SECOND, 0);
        todayFive.set(Calendar.MILLISECOND, 0);
        long fiveAmToday = todayFive.getTimeInMillis();
        if (System.currentTimeMillis() < fiveAmToday) {
            return; // 未到今日 05:00，等正常排程跑
        }
        if (AlarmStore.getLastImportAt(context) >= fiveAmToday) {
            return; // 今日 05:00 之後已經匯入過，唔使補
        }
        final Context appContext = context.getApplicationContext();
        new Thread(new Runnable() {
            @Override
            public void run() {
                try {
                    ScheduleGridAutoImporter.importFromPc(appContext);
                } catch (Exception e) {
                    Log.w(TAG, "Boot catch-up daily import failed", e);
                }
            }
        }).start();
    }

    static void scheduleDailyImports(Context context) {
        scheduleDailyImportSlot(context, REQUEST_CODE_DAILY_IMPORT_0500);
        scheduleDailyImportSlot(context, REQUEST_CODE_DAILY_IMPORT_0530);
    }

    private static void scheduleDailyImportSlot(Context context, int slot) {
        int hour = 5;
        int minute = slot == REQUEST_CODE_DAILY_IMPORT_0530 ? 30 : 0;
        AlarmManager alarmManager = (AlarmManager) context.getSystemService(Context.ALARM_SERVICE);
        if (alarmManager == null) {
            return;
        }
        Intent intent = new Intent(context, AlarmAutoSyncReceiver.class);
        intent.setAction(ACTION_DAILY_IMPORT);
        intent.putExtra(EXTRA_DAILY_IMPORT_SLOT, slot);
        int flags = PendingIntent.FLAG_UPDATE_CURRENT | (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M ? PendingIntent.FLAG_IMMUTABLE : 0);
        PendingIntent pendingIntent = PendingIntent.getBroadcast(context, slot, intent, flags);
        long triggerAt = nextDailyTriggerAt(hour, minute);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            alarmManager.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, triggerAt, pendingIntent);
        } else if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.KITKAT) {
            alarmManager.setExact(AlarmManager.RTC_WAKEUP, triggerAt, pendingIntent);
        } else {
            alarmManager.set(AlarmManager.RTC_WAKEUP, triggerAt, pendingIntent);
        }
    }

    private static long nextDailyTriggerAt(int hour, int minute) {
        Calendar calendar = Calendar.getInstance();
        calendar.set(Calendar.HOUR_OF_DAY, hour);
        calendar.set(Calendar.MINUTE, minute);
        calendar.set(Calendar.SECOND, 0);
        calendar.set(Calendar.MILLISECOND, 0);
        if (calendar.getTimeInMillis() <= System.currentTimeMillis()) {
            calendar.add(Calendar.DAY_OF_MONTH, 1);
        }
        return calendar.getTimeInMillis();
    }

}
