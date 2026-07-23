package com.example.oneshotalarm.watch;

import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.util.Log;

import com.google.android.gms.wearable.DataMap;
import com.google.android.gms.wearable.DataMapItem;
import com.google.android.gms.wearable.MessageEvent;
import com.google.android.gms.wearable.DataEvent;
import com.google.android.gms.wearable.DataEventBuffer;
import com.google.android.gms.wearable.WearableListenerService;

import org.json.JSONObject;
import org.json.JSONArray;

import java.nio.charset.StandardCharsets;

public class WearAlarmListenerService extends WearableListenerService {
    private static final String TAG = "ShiftAlarmWatch";
    private static final String WATCH_DISMISS_PATH = "/oneshotalarm/watch-dismiss";
    private static final String WATCH_DISMISS_DATA_PATH = "/oneshotalarm/watch-dismiss-data";
    private static final String TILE_STATE_PATH = "/oneshotalarm/tile-state";
    private static final String WEAR_APK_CHANNEL_PATH = "/oneshotalarm/wear-apk";
    private static final String CAPTURE_REQUEST_PATH = "/oneshotalarm/capture-request";
    private static final String CAPTURE_RESULT_PATH = "/oneshotalarm/capture-result";
    private static final String VERSION_REQUEST_PATH = "/oneshotalarm/version-request";
    private static final String VERSION_RESULT_PATH = "/oneshotalarm/version-result";
    private static final String PREFS = "watch_alarm_listener";
    private static final String KEY_LAST_TILE_STATE_AT = "last_tile_state_at";
    private static final long DISMISS_FRESH_MS = 30 * 1000L;

    @Override
    public void onDataChanged(DataEventBuffer dataEvents) {
        for (DataEvent event : dataEvents) {
            if (event == null
                    || event.getType() != DataEvent.TYPE_CHANGED
                    || event.getDataItem() == null
                    || event.getDataItem().getUri() == null) {
                continue;
            }
            if (WATCH_DISMISS_DATA_PATH.equals(event.getDataItem().getUri().getPath())) {
                DataMap map = DataMapItem.fromDataItem(event.getDataItem()).getDataMap();
                Log.d(TAG, "Received phone dismiss data: " + map.getString("alarm_id", ""));
                dismissWatchAlarm(map.getString("alarm_id", ""), map.getLong("ts", 0L));
                return;
            }
            if (TILE_STATE_PATH.equals(event.getDataItem().getUri().getPath())) {
                saveTileState(DataMapItem.fromDataItem(event.getDataItem()).getDataMap());
            }
        }
    }

    @Override
    public void onMessageReceived(MessageEvent messageEvent) {
        if (messageEvent == null) {
            return;
        }
        if (WATCH_DISMISS_PATH.equals(messageEvent.getPath())) {
            JSONObject payload = dismissPayload(messageEvent.getData());
            String alarmId = payload.optString("alarm_id", "");
            Log.d(TAG, "Received phone dismiss message: " + alarmId);
            dismissWatchAlarm(alarmId, payload.optLong("ts", payload.optLong("dismiss_id", 0L)));
            return;
        }
        if (TILE_STATE_PATH.equals(messageEvent.getPath())) {
            saveTileState(new String(messageEvent.getData(), StandardCharsets.UTF_8));
            return;
        }
        if (CAPTURE_REQUEST_PATH.equals(messageEvent.getPath())) {
            String sourceNodeId = messageEvent.getSourceNodeId();
            new Thread(() -> sendCaptureResult(sourceNodeId), "watch-capture").start();
            return;
        }
        if (VERSION_REQUEST_PATH.equals(messageEvent.getPath())) {
            // 電話 update 前問一聲：我而家裝緊邊個 version（同版就唔使傳 APK 過嚟）。
            String sourceNodeId = messageEvent.getSourceNodeId();
            long version = 0;
            try {
                version = versionCodeOf(getPackageManager().getPackageInfo(getPackageName(), 0));
            } catch (Exception e) {
                Log.w(TAG, "Read own version failed", e);
            }
            byte[] payload = String.valueOf(version).getBytes(StandardCharsets.UTF_8);
            com.google.android.gms.wearable.Wearable.getMessageClient(this)
                    .sendMessage(sourceNodeId, VERSION_RESULT_PATH, payload)
                    .addOnFailureListener(e -> Log.e(TAG, "Send version result failed", e));
            return;
        }
    }

    /** 影一張全螢幕 PNG，經 ChannelClient 回傳俾電話（空 byte＝失敗）。 */
    private void sendCaptureResult(String nodeId) {
        byte[] png = WatchCaptureAccessibilityService.captureNow();
        byte[] payload = png != null ? png : new byte[0];
        try {
            com.google.android.gms.wearable.ChannelClient channelClient =
                    com.google.android.gms.wearable.Wearable.getChannelClient(this);
            com.google.android.gms.wearable.ChannelClient.Channel channel =
                    com.google.android.gms.tasks.Tasks.await(
                            channelClient.openChannel(nodeId, CAPTURE_RESULT_PATH),
                            10, java.util.concurrent.TimeUnit.SECONDS);
            try (java.io.OutputStream out = com.google.android.gms.tasks.Tasks.await(
                    channelClient.getOutputStream(channel),
                    10, java.util.concurrent.TimeUnit.SECONDS)) {
                out.write(payload);
            }
            Log.d(TAG, "Sent capture result (" + payload.length + " bytes)");
        } catch (Exception e) {
            Log.e(TAG, "Send capture result failed", e);
        }
    }

    private void dismissWatchAlarm(String alarmId, long sentAtMillis) {
        // Data-layer dismiss items can arrive long after they were sent (Doze /
        // disconnect deferral), right when the NEXT alarm wakes the watch — so a
        // dismiss may only stop ringing if it names the ringing alarm, or is fresh.
        String id = alarmId == null ? "" : alarmId.trim();
        long now = System.currentTimeMillis();
        boolean fresh = sentAtMillis > 0L && Math.abs(now - sentAtMillis) < DISMISS_FRESH_MS;
        String ringingId = WatchAlarmService.activeAlarmId(this);
        boolean matchesRinging = ringingId != null && !id.isEmpty() && id.equals(ringingId);
        if (!fresh && !matchesRinging) {
            Log.d(TAG, "Ignored stale phone dismiss: " + id);
            return;
        }
        Log.d(TAG, "Dismiss watch alarm from phone: " + id);
        if (!id.isEmpty()) {
            WatchLocalAlarmScheduler.cancelAlarm(this, id);
        }
        if (matchesRinging || id.isEmpty()) {
            WatchAlarmService.stop(this);
            Intent intent = new Intent(WatchAlarmActivity.ACTION_DISMISS_LOCAL);
            intent.setPackage(getPackageName());
            sendBroadcast(intent);
        }
        WatchScheduleDisplayState.refreshFromCacheAndRequest(this);
    }

    /**
     * Tile state 行雙通道（message 快 + data item 捱得過 Doze），兩邊帶同一個
     * updated_at。兩個通道都到齊時，第二份唔好再 cancel+reschedule 晒全部
     * alarm 同 refresh complication 多次——慳電。
     */
    private boolean isDuplicateTileState(long updatedAt) {
        if (updatedAt <= 0L) {
            return false; // 冇 updated_at 嘅舊 payload 照處理
        }
        SharedPreferences preferences = getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        if (updatedAt == preferences.getLong(KEY_LAST_TILE_STATE_AT, 0L)) {
            return true;
        }
        preferences.edit().putLong(KEY_LAST_TILE_STATE_AT, updatedAt).apply();
        return false;
    }

    private void saveTileState(DataMap map) {
        if (map == null) {
            return;
        }
        if (isDuplicateTileState(map.getLong("updated_at", 0L))) {
            Log.d(TAG, "Duplicate tile state (data channel) ignored");
            return;
        }
        getSharedPreferences(AlarmScheduleState.PREFS, Context.MODE_PRIVATE).edit()
                .putString(AlarmScheduleState.KEY_PLAN_DATE, map.getString("plan_date", ""))
                .putString(AlarmScheduleState.KEY_ROSTER_CODE, map.getString("roster_code", ""))
                .putString(AlarmScheduleState.KEY_SCHEDULE_ITEMS_JSON, map.getString("schedule_items_json", "[]"))
                .remove("schedule_count")
                .putString(AlarmScheduleState.KEY_PREV_TIME, map.getString("prev_time", "--:--"))
                .putString(AlarmScheduleState.KEY_PREV_DATE, map.getString("prev_date", ""))
                .putString(AlarmScheduleState.KEY_PREV_LABEL, map.getString("prev_label", "沒有資料"))
                .putLong(AlarmScheduleState.KEY_PREV_AT, map.getLong("prev_at", 0L))
                .putString(AlarmScheduleState.KEY_NEXT_TIME, map.getString("next_time", "--:--"))
                .putString(AlarmScheduleState.KEY_NEXT_DATE, map.getString("next_date", ""))
                .putString(AlarmScheduleState.KEY_NEXT_LABEL, map.getString("next_label", "沒有資料"))
                .putLong(AlarmScheduleState.KEY_NEXT_AT, map.getLong("next_at", 0L))
                .putLong(AlarmScheduleState.KEY_UPDATED_AT, map.getLong("updated_at", System.currentTimeMillis()))
                .apply();
        WatchLocalAlarmScheduler.scheduleFromCachedState(this);
        WatchScheduleDisplayState.refreshFromCacheAndRequest(this);
    }

    private void saveTileState(String rawJson) {
        try {
            JSONObject json = new JSONObject(rawJson == null ? "{}" : rawJson);
            if (isDuplicateTileState(json.optLong("updated_at", 0L))) {
                Log.d(TAG, "Duplicate tile state (message channel) ignored");
                return;
            }
            JSONArray items = json.optJSONArray("schedule_items");
            getSharedPreferences(AlarmScheduleState.PREFS, Context.MODE_PRIVATE).edit()
                    .putString(AlarmScheduleState.KEY_PLAN_DATE, json.optString("plan_date", ""))
                    .putString(AlarmScheduleState.KEY_ROSTER_CODE, json.optString("roster_code", ""))
                    .putString(AlarmScheduleState.KEY_SCHEDULE_ITEMS_JSON, items == null ? "[]" : items.toString())
                    .remove("schedule_count")
                    .putString(AlarmScheduleState.KEY_PREV_TIME, json.optString("prev_time", "--:--"))
                    .putString(AlarmScheduleState.KEY_PREV_DATE, json.optString("prev_date", ""))
                    .putString(AlarmScheduleState.KEY_PREV_LABEL, json.optString("prev_label", "沒有資料"))
                    .putLong(AlarmScheduleState.KEY_PREV_AT, json.optLong("prev_at", 0L))
                    .putString(AlarmScheduleState.KEY_NEXT_TIME, json.optString("next_time", "--:--"))
                    .putString(AlarmScheduleState.KEY_NEXT_DATE, json.optString("next_date", ""))
                    .putString(AlarmScheduleState.KEY_NEXT_LABEL, json.optString("next_label", "沒有資料"))
                    .putLong(AlarmScheduleState.KEY_NEXT_AT, json.optLong("next_at", 0L))
                    .putLong(AlarmScheduleState.KEY_UPDATED_AT, json.optLong("updated_at", System.currentTimeMillis()))
                    .apply();
            WatchLocalAlarmScheduler.scheduleFromCachedState(this);
            WatchScheduleDisplayState.refreshFromCacheAndRequest(this);
        } catch (Exception e) {
            Log.e(TAG, "Save tile state message failed", e);
        }
    }

    private JSONObject dismissPayload(byte[] data) {
        String raw = new String(data == null ? new byte[0] : data, StandardCharsets.UTF_8);
        try {
            return new JSONObject(raw);
        } catch (Exception ignored) {
            return new JSONObject();
        }
    }

    // ---------------- in-app update：電話推 APK 過嚟（ChannelClient），收齊即裝 ----------------

    @Override
    public void onChannelOpened(com.google.android.gms.wearable.ChannelClient.Channel channel) {
        if (channel == null || !WEAR_APK_CHANNEL_PATH.equals(channel.getPath())) {
            return;
        }
        java.io.File dest = updateApkFile();
        if (dest.exists() && !dest.delete()) {
            Log.w(TAG, "Cannot delete old update apk");
        }
        Log.d(TAG, "Receiving wear APK from phone...");
        com.google.android.gms.wearable.Wearable.getChannelClient(this)
                .receiveFile(channel, android.net.Uri.fromFile(dest), false)
                .addOnFailureListener(e -> Log.e(TAG, "Receive wear APK failed", e));
    }

    @Override
    public void onInputClosed(com.google.android.gms.wearable.ChannelClient.Channel channel,
            int closeReason, int appSpecificErrorCode) {
        if (channel == null || !WEAR_APK_CHANNEL_PATH.equals(channel.getPath())) {
            return;
        }
        java.io.File apk = updateApkFile();
        if (closeReason != com.google.android.gms.wearable.ChannelClient.ChannelCallback.CLOSE_REASON_NORMAL
                || !apk.isFile() || apk.length() == 0) {
            Log.e(TAG, "Wear APK transfer incomplete, reason=" + closeReason);
            return;
        }
        // 同 version 唔使裝：解 APK 版本對返自己，一樣就 skip。
        try {
            android.content.pm.PackageInfo incoming = getPackageManager()
                    .getPackageArchiveInfo(apk.getPath(), 0);
            android.content.pm.PackageInfo own = getPackageManager()
                    .getPackageInfo(getPackageName(), 0);
            long incomingCode = incoming != null ? versionCodeOf(incoming) : 0;
            long ownCode = versionCodeOf(own);
            if (incomingCode > 0 && incomingCode <= ownCode) {
                Log.d(TAG, "Wear APK v" + incomingCode + " <= installed v" + ownCode + ", skip install");
                deleteQuietly(apk);
                return;
            }
        } catch (Exception e) {
            Log.w(TAG, "Version check failed, installing anyway", e);
        }
        Log.d(TAG, "Wear APK received (" + apk.length() + " bytes), installing...");
        try {
            installApk(apk);
        } catch (Exception e) {
            Log.e(TAG, "Install wear APK failed", e);
        } finally {
            // session 已抄走份 APK，cache 嗰份即刻清。
            deleteQuietly(apk);
        }
    }

    private static void deleteQuietly(java.io.File file) {
        if (file != null && file.exists() && !file.delete()) {
            Log.w(TAG, "Cannot delete " + file);
        }
    }

    private static long versionCodeOf(android.content.pm.PackageInfo info) {
        return android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.P
                ? info.getLongVersionCode() : info.versionCode;
    }

    private java.io.File updateApkFile() {
        return new java.io.File(getCacheDir(), "update-wear.apk");
    }

    /** PackageInstaller session；確認框喺手錶螢幕撳。 */
    private void installApk(java.io.File apk) throws Exception {
        android.content.pm.PackageInstaller installer = getPackageManager().getPackageInstaller();
        android.content.pm.PackageInstaller.SessionParams params =
                new android.content.pm.PackageInstaller.SessionParams(
                        android.content.pm.PackageInstaller.SessionParams.MODE_FULL_INSTALL);
        params.setSize(apk.length());
        int sessionId = installer.createSession(params);
        try (android.content.pm.PackageInstaller.Session session = installer.openSession(sessionId)) {
            try (java.io.OutputStream out = session.openWrite("wear.apk", 0, apk.length());
                    java.io.InputStream in = new java.io.FileInputStream(apk)) {
                byte[] buffer = new byte[65536];
                int read;
                while ((read = in.read(buffer)) >= 0) {
                    out.write(buffer, 0, read);
                }
                session.fsync(out);
            }
            Intent intent = new Intent(this, WatchInstallResultReceiver.class)
                    .setAction(WatchInstallResultReceiver.ACTION_INSTALL_RESULT);
            int flags = android.app.PendingIntent.FLAG_UPDATE_CURRENT;
            if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.S) {
                flags |= android.app.PendingIntent.FLAG_MUTABLE;
            }
            android.app.PendingIntent pending =
                    android.app.PendingIntent.getBroadcast(this, sessionId, intent, flags);
            session.commit(pending.getIntentSender());
        }
    }

}
