package com.example.oneshotalarm;

import android.content.Intent;
import android.util.Log;

import com.google.android.gms.wearable.DataMap;
import com.google.android.gms.wearable.DataEvent;
import com.google.android.gms.wearable.DataEventBuffer;
import com.google.android.gms.wearable.MessageEvent;
import com.google.android.gms.wearable.PutDataMapRequest;
import com.google.android.gms.wearable.Wearable;
import com.google.android.gms.wearable.WearableListenerService;

import org.json.JSONArray;
import org.json.JSONObject;

import java.text.SimpleDateFormat;
import java.util.Locale;

public class PhoneWearListenerService extends WearableListenerService {
    private static final String TAG = "OneShotWearListener";
    private static final String DISMISS_PATH = "/oneshotalarm/dismiss";
    private static final String DISMISS_DATA_PATH = "/oneshotalarm/dismiss-data";
    private static final String TILE_STATE_REQUEST_PATH = "/oneshotalarm/tile-state-request";
    private static final String TILE_STATE_PATH = "/oneshotalarm/tile-state";

    @Override
    public void onDataChanged(DataEventBuffer dataEvents) {
        for (DataEvent event : dataEvents) {
            if (event != null
                    && event.getDataItem() != null
                    && event.getDataItem().getUri() != null
                    && DISMISS_DATA_PATH.equals(event.getDataItem().getUri().getPath())) {
                Log.d(TAG, "Received watch dismiss data");
                dispatchWatchDismiss();
                return;
            }
        }
    }

    @Override
    public void onMessageReceived(MessageEvent messageEvent) {
        if (messageEvent == null) {
            return;
        }
        if (TILE_STATE_REQUEST_PATH.equals(messageEvent.getPath())) {
            Log.d(TAG, "Received watch tile state request");
            WatchBridge.sendTileState(this);
            return;
        }
        if (!DISMISS_PATH.equals(messageEvent.getPath())) {
            return;
        }
        Log.d(TAG, "Received watch dismiss message");
        dispatchWatchDismiss();
    }

    private void dispatchWatchDismiss() {
        AlarmActivity.markWatchDismiss(this);
        WatchBridge.sendTileState(this);
        Intent intent = new Intent(AlarmActivity.ACTION_WATCH_DISMISS);
        intent.setPackage(getPackageName());
        sendBroadcast(intent);
    }

    private void sendTileState() {
        long now = System.currentTimeMillis();
        AlarmPair pair = findPrevNext(now);
        PutDataMapRequest request = PutDataMapRequest.create(TILE_STATE_PATH);
        DataMap map = request.getDataMap();
        map.putLong("updated_at", now);
        putAlarm(map, "prev", pair.prev, pair.prevAt);
        putAlarm(map, "next", pair.next, pair.nextAt);
        Wearable.getDataClient(this)
                .putDataItem(request.asPutDataRequest().setUrgent())
                .addOnSuccessListener(item -> Log.d(TAG, "Sent tile state to watch"))
                .addOnFailureListener(e -> Log.e(TAG, "Send tile state to watch failed", e));
    }

    private AlarmPair findPrevNext(long now) {
        JSONArray alarms = AlarmStore.getAlarms(this);
        JSONObject prev = null;
        JSONObject next = null;
        long prevAt = 0L;
        long nextAt = Long.MAX_VALUE;
        for (int i = 0; i < alarms.length(); i++) {
            JSONObject alarm = alarms.optJSONObject(i);
            if (alarm == null) {
                continue;
            }
            long triggerAt = alarm.optLong("trigger_at_epoch_ms", 0L);
            if (triggerAt <= 0L) {
                continue;
            }
            if (triggerAt <= now && triggerAt >= prevAt) {
                prev = alarm;
                prevAt = triggerAt;
            }
            if (triggerAt > now && triggerAt < nextAt) {
                next = alarm;
                nextAt = triggerAt;
            }
        }
        return new AlarmPair(prev, prevAt, next, nextAt == Long.MAX_VALUE ? 0L : nextAt);
    }

    private void putAlarm(DataMap map, String prefix, JSONObject alarm, long triggerAt) {
        if (alarm == null || triggerAt <= 0L) {
            map.putString(prefix + "_time", "--:--");
            map.putString(prefix + "_date", "");
            map.putString(prefix + "_label", "沒有資料");
            map.putLong(prefix + "_at", 0L);
            return;
        }
        map.putString(prefix + "_time", new SimpleDateFormat("HH:mm", Locale.getDefault()).format(triggerAt));
        map.putString(prefix + "_date", new SimpleDateFormat("dd/MM EEE", Locale.getDefault()).format(triggerAt));
        map.putLong(prefix + "_at", triggerAt);
        String label = alarm.optString("label", "").trim();
        map.putString(prefix + "_label", label.isEmpty() ? "鬧鐘" : label);
    }

    private static final class AlarmPair {
        final JSONObject prev;
        final long prevAt;
        final JSONObject next;
        final long nextAt;

        AlarmPair(JSONObject prev, long prevAt, JSONObject next, long nextAt) {
            this.prev = prev;
            this.prevAt = prevAt;
            this.next = next;
            this.nextAt = nextAt;
        }
    }
}
