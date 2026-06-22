package com.example.oneshotalarm;

import android.app.AlarmManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.util.Log;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.Calendar;

public final class AlarmAutoSyncReceiver extends BroadcastReceiver {
    private static final String TAG = "OneShotAutoSync";
    private static final String ACTION_AUTO_SYNC_POLL = "com.example.oneshotalarm.ACTION_AUTO_SYNC_POLL";
    private static final String ACTION_DAILY_IMPORT = "com.example.oneshotalarm.ACTION_DAILY_IMPORT";
    private static final String EXTRA_DAILY_IMPORT_SLOT = "daily_import_slot";
    private static final int REQUEST_CODE_AUTO_SYNC_POLL = 8102;
    private static final int REQUEST_CODE_DAILY_IMPORT_0500 = 8500;
    private static final int REQUEST_CODE_DAILY_IMPORT_0530 = 8530;
    private static final long POLL_INTERVAL_MS = 2 * 60 * 1000L;
    private static final int HTTP_CONNECT_TIMEOUT_MS = 4000;
    private static final int HTTP_READ_TIMEOUT_MS = 12000;

    interface PollCallback {
        void onResult(PollResult result);
    }

    static final class PollResult {
        final boolean ok;
        final boolean updated;
        final long syncId;
        final int alarmCount;
        final String message;

        PollResult(boolean ok, boolean updated, long syncId, int alarmCount, String message) {
            this.ok = ok;
            this.updated = updated;
            this.syncId = syncId;
            this.alarmCount = alarmCount;
            this.message = message == null ? "" : message;
        }
    }

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
        if (!ACTION_AUTO_SYNC_POLL.equals(action)) {
            return;
        }
        new Thread(new Runnable() {
            @Override
            public void run() {
                pollAndImport(context, true);
            }
        }).start();
    }

    static void schedulePolling(Context context) {
        cancelLegacyPolling(context);
        scheduleDailyImports(context);
    }

    private static void cancelLegacyPolling(Context context) {
        AlarmManager alarmManager = (AlarmManager) context.getSystemService(Context.ALARM_SERVICE);
        if (alarmManager == null) {
            return;
        }
        Intent intent = new Intent(context, AlarmAutoSyncReceiver.class);
        intent.setAction(ACTION_AUTO_SYNC_POLL);
        int flags = PendingIntent.FLAG_NO_CREATE | (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M ? PendingIntent.FLAG_IMMUTABLE : 0);
        PendingIntent pendingIntent = PendingIntent.getBroadcast(
                context,
                REQUEST_CODE_AUTO_SYNC_POLL,
                intent,
                flags
        );
        if (pendingIntent != null) {
            alarmManager.cancel(pendingIntent);
            pendingIntent.cancel();
        }
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

    static void scheduleLegacyPollingForManualSync(Context context) {
        String serverUrl = AlarmStore.getAutoSyncServerUrl(context);
        String deviceId = AlarmStore.getAutoSyncDeviceId(context);
        if (serverUrl == null || serverUrl.trim().isEmpty() || deviceId == null || deviceId.trim().isEmpty()) {
            return;
        }
        AlarmManager alarmManager = (AlarmManager) context.getSystemService(Context.ALARM_SERVICE);
        Intent intent = new Intent(context, AlarmAutoSyncReceiver.class);
        intent.setAction(ACTION_AUTO_SYNC_POLL);
        int flags = PendingIntent.FLAG_UPDATE_CURRENT | (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M ? PendingIntent.FLAG_IMMUTABLE : 0);
        PendingIntent pendingIntent = PendingIntent.getBroadcast(
                context,
                REQUEST_CODE_AUTO_SYNC_POLL,
                intent,
                flags
        );
        long triggerAt = System.currentTimeMillis() + POLL_INTERVAL_MS;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            alarmManager.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, triggerAt, pendingIntent);
        } else if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.KITKAT) {
            alarmManager.setExact(AlarmManager.RTC_WAKEUP, triggerAt, pendingIntent);
        } else {
            alarmManager.set(AlarmManager.RTC_WAKEUP, triggerAt, pendingIntent);
        }
    }

    static void pollNow(Context context, PollCallback callback) {
        Context appContext = context.getApplicationContext();
        new Thread(new Runnable() {
            @Override
            public void run() {
                PollResult result = pollAndImport(appContext, false);
                if (callback != null) {
                    callback.onResult(result);
                }
            }
        }).start();
    }

    private static PollResult pollAndImport(Context context, boolean scheduleNext) {
        String serverUrl = AlarmStore.getAutoSyncServerUrl(context);
        String deviceId = AlarmStore.getAutoSyncDeviceId(context);
        if (serverUrl == null || serverUrl.trim().isEmpty() || deviceId == null || deviceId.trim().isEmpty()) {
            if (scheduleNext) {
                schedulePolling(context);
            }
            return new PollResult(false, false, 0L, 0, "未設定同步 Server");
        }

        long lastSyncId = AlarmStore.getAutoSyncLastSyncId(context);
        String[] candidates = AlarmStore.getAutoSyncServerCandidates(context);
        Exception lastError = null;
        for (String serverUrlCandidate : candidates) {
            String server = serverUrlCandidate == null ? "" : serverUrlCandidate.trim();
            if (server.isEmpty() || !(server.startsWith("http://") || server.startsWith("https://"))) {
                continue;
            }
            if (server.endsWith("/")) {
                server = server.substring(0, server.length() - 1);
            }
            String endpoint = server
                    + "/api/alarm-plan/poll?device="
                    + Uri.encode(deviceId)
                    + "&last_sync_id="
                    + lastSyncId;
            HttpURLConnection conn = null;
            try {
                URL url = new URL(endpoint);
                conn = (HttpURLConnection) url.openConnection();
                conn.setRequestMethod("GET");
                conn.setConnectTimeout(HTTP_CONNECT_TIMEOUT_MS);
                conn.setReadTimeout(HTTP_READ_TIMEOUT_MS);
                conn.connect();
                int code = conn.getResponseCode();
                if (code != HttpURLConnection.HTTP_OK) {
                    Log.w(TAG, "Auto sync poll HTTP " + code + " at " + endpoint);
                    lastError = new Exception("同步失敗：HTTP " + code);
                    continue;
                }
                String body = readResponse(conn.getInputStream());
                if (body == null || body.isEmpty()) {
                    return new PollResult(false, false, 0L, 0, "同步失敗：回應空白");
                }
                JSONObject response = new JSONObject(body);
                if (!response.optBoolean("ok", false)) {
                    return new PollResult(false, false, 0L, 0, "同步失敗：Server 回應錯誤");
                }
                if (!response.optBoolean("updated", false)) {
                    return new PollResult(true, false, lastSyncId, AlarmStore.getAlarms(context).length(), "未有新資料");
                }
                long syncId = response.optLong("sync_id", 0L);
                if (syncId <= lastSyncId) {
                    return new PollResult(true, false, syncId, AlarmStore.getAlarms(context).length(), "未有新資料");
                }
                JSONObject payload = response.optJSONObject("payload");
                if (payload == null) {
                    return new PollResult(false, false, syncId, 0, "同步失敗：payload 空白");
                }
                AlarmImportCoordinator.importPlanData(context, payload, false);
                AlarmStore.setAutoSyncLastSyncId(context, syncId);
                int count = AlarmStore.getAlarms(context).length();
                return new PollResult(true, true, syncId, count, "已同步 " + count + " 個鬧鐘");
            } catch (Exception e) {
                Log.w(TAG, "Auto sync poll failed at " + server, e);
                lastError = e;
            } finally {
                if (conn != null) {
                    conn.disconnect();
                }
            }
        }
        if (scheduleNext) {
            schedulePolling(context);
        }
        String message = lastError == null
                ? "同步失敗：未能連線任何可用的 server"
                : "同步失敗：" + lastError.getMessage();
        return new PollResult(false, false, 0L, 0, message);
    }

    private static String readResponse(InputStream inputStream) throws Exception {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        byte[] buffer = new byte[1024];
        int n;
        while ((n = inputStream.read(buffer)) > -1) {
            out.write(buffer, 0, n);
        }
        return new String(out.toByteArray(), "UTF-8");
    }
}
