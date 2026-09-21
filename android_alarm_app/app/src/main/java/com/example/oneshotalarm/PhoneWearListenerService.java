package com.example.oneshotalarm;

import android.content.Intent;
import android.content.SharedPreferences;
import android.util.Log;

import com.google.android.gms.wearable.DataEvent;
import com.google.android.gms.wearable.DataEventBuffer;
import com.google.android.gms.wearable.DataMap;
import com.google.android.gms.wearable.DataMapItem;
import com.google.android.gms.wearable.MessageEvent;
import com.google.android.gms.wearable.WearableListenerService;

import org.json.JSONObject;

import java.nio.charset.StandardCharsets;

public class PhoneWearListenerService extends WearableListenerService {
    private static final String TAG = "OneShotWearListener";
    private static final String DISMISS_PATH = "/oneshotalarm/dismiss";
    private static final String DISMISS_DATA_PATH = "/oneshotalarm/dismiss-data";
    private static final String PREFS = "phone_wear_listener";
    private static final String KEY_LAST_DISMISS_ID = "last_dismiss_id";
    private static final String KEY_LAST_DISMISS_SEEN_AT = "last_dismiss_seen_at";
    private static final long DISMISS_FRESH_MS = 30 * 1000L;

    @Override
    public void onDataChanged(DataEventBuffer dataEvents) {
        for (DataEvent event : dataEvents) {
            if (event != null
                    && event.getType() == DataEvent.TYPE_CHANGED
                    && event.getDataItem() != null
                    && event.getDataItem().getUri() != null
                    && DISMISS_DATA_PATH.equals(event.getDataItem().getUri().getPath())) {
                Log.d(TAG, "Received watch dismiss data");
                DataMap map = DataMapItem.fromDataItem(event.getDataItem()).getDataMap();
                long dismissId = map.getLong("dismiss_id", 0L);
                dispatchWatchDismiss(
                        map.getString("alarm_id", ""),
                        map.getLong("ts", dismissId),
                        dismissId
                );
                return;
            }
        }
    }

    @Override
    public void onMessageReceived(MessageEvent messageEvent) {
        if (messageEvent == null) {
            return;
        }
        if (WatchVersionBridge.VERSION_RESULT_PATH.equals(messageEvent.getPath())) {
            try {
                WatchVersionBridge.deliver(Long.parseLong(
                        new String(messageEvent.getData(), StandardCharsets.UTF_8).trim()));
            } catch (Exception e) {
                WatchVersionBridge.deliver(0);
            }
            return;
        }
        if (!DISMISS_PATH.equals(messageEvent.getPath())) {
            return;
        }
        Log.d(TAG, "Received watch dismiss message");
        JSONObject payload = dismissPayload(messageEvent.getData());
        long dismissId = payload.optLong("dismiss_id", 0L);
        dispatchWatchDismiss(
                payload.optString("alarm_id", ""),
                payload.optLong("ts", dismissId),
                dismissId
        );
    }

    /**
     * 手錶一次 dismiss 會經 message + data item 兩條路各送 4 次（保證起碼一份到）。
     * 同一個 dismiss_id 30 秒內只處理一次——否則一次 dismiss 最多 8 次
     * markAlarmFired + notifyChanged + broadcast。照 wear 嗰邊 isDuplicateTileState 嘅做法。
     */
    private boolean isDuplicateDismiss(long dismissId) {
        if (dismissId <= 0L) {
            return false; // 冇 id 嘅舊 payload 照處理
        }
        SharedPreferences preferences = getSharedPreferences(PREFS, MODE_PRIVATE);
        long now = System.currentTimeMillis();
        if (dismissId == preferences.getLong(KEY_LAST_DISMISS_ID, 0L)
                && now - preferences.getLong(KEY_LAST_DISMISS_SEEN_AT, 0L) < DISMISS_FRESH_MS) {
            return true;
        }
        preferences.edit()
                .putLong(KEY_LAST_DISMISS_ID, dismissId)
                .putLong(KEY_LAST_DISMISS_SEEN_AT, now)
                .apply();
        return false;
    }

    private void dispatchWatchDismiss(String alarmId, long sentAtMillis, long dismissId) {
        if (isDuplicateDismiss(dismissId)) {
            Log.d(TAG, "Duplicate watch dismiss ignored id=" + dismissId);
            return;
        }
        // Data-layer dismiss items can be delivered long after the watch sent them
        // (Doze / disconnect deferral) — a stale dismiss must not touch alarm state;
        // it may only close a ringing AlarmActivity whose alarm id matches.
        String id = alarmId == null ? "" : alarmId.trim();
        long now = System.currentTimeMillis();
        boolean fresh = sentAtMillis > 0L && Math.abs(now - sentAtMillis) < DISMISS_FRESH_MS;
        DiagLog.log(this, "watch dismiss received id=" + id + " fresh=" + fresh);
        if (!fresh && id.isEmpty()) {
            Log.d(TAG, "Ignored stale watch dismiss without alarm id");
            return;
        }
        if (fresh) {
            if (!id.isEmpty()) {
                AlarmScheduler.cancelAlarm(this, id, "");
                AlarmStore.markAlarmFired(this, id);
                NextAlarmWidgetProvider.updateAll(this);
            }
            AlarmActivity.markWatchDismiss(this, id);
        }
        Intent intent = new Intent(AlarmActivity.ACTION_WATCH_DISMISS);
        intent.setPackage(getPackageName());
        intent.putExtra(AlarmActivity.EXTRA_DISMISS_ALARM_ID, id);
        intent.putExtra(AlarmActivity.EXTRA_DISMISS_TS, sentAtMillis);
        sendBroadcast(intent);
    }

    private JSONObject dismissPayload(byte[] data) {
        String raw = new String(data == null ? new byte[0] : data, StandardCharsets.UTF_8);
        try {
            return new JSONObject(raw);
        } catch (Exception ignored) {
            return new JSONObject();
        }
    }

    /** 手錶截圖回傳（ChannelClient）：讀晒 PNG 交返俾 WatchCaptureBridge。 */
    @Override
    public void onChannelOpened(com.google.android.gms.wearable.ChannelClient.Channel channel) {
        if (channel == null || !WatchCaptureBridge.CAPTURE_RESULT_PATH.equals(channel.getPath())) {
            return;
        }
        com.google.android.gms.wearable.Wearable.getChannelClient(this)
                .getInputStream(channel)
                .addOnSuccessListener(in -> new Thread(() -> {
                    try (java.io.InputStream stream = in) {
                        java.io.ByteArrayOutputStream out = new java.io.ByteArrayOutputStream();
                        byte[] buffer = new byte[65536];
                        int read;
                        while ((read = stream.read(buffer)) >= 0) {
                            out.write(buffer, 0, read);
                        }
                        WatchCaptureBridge.deliver(out.toByteArray());
                    } catch (Exception e) {
                        Log.e(TAG, "Read watch capture failed", e);
                        WatchCaptureBridge.deliver(null);
                    }
                }, "watch-capture-read").start())
                .addOnFailureListener(e -> {
                    Log.e(TAG, "Open watch capture stream failed", e);
                    WatchCaptureBridge.deliver(null);
                });
    }
}
