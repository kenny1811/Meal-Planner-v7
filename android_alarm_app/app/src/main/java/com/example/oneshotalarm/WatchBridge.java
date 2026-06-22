package com.example.oneshotalarm;

import android.content.Context;
import android.util.Log;

import com.google.android.gms.wearable.DataMap;
import com.google.android.gms.wearable.Node;
import com.google.android.gms.wearable.PutDataMapRequest;
import com.google.android.gms.wearable.Wearable;

import org.json.JSONArray;
import org.json.JSONObject;

import java.text.SimpleDateFormat;
import java.util.List;
import java.util.Locale;

final class WatchBridge {
    private static final String TAG = "OneShotWatchBridge";
    private static final String ALARM_PATH = "/oneshotalarm/alarm";
    private static final String WATCH_DISMISS_PATH = "/oneshotalarm/watch-dismiss";
    private static final String WATCH_DISMISS_DATA_PATH = "/oneshotalarm/watch-dismiss-data";
    private static final String TILE_STATE_PATH = "/oneshotalarm/tile-state";

    private WatchBridge() {
    }

    static void sendAlarm(Context context, String label, long triggerAtMillis) {
        if (!AlarmStore.isWatchAlarmEnabled(context)) {
            Log.d(TAG, "Watch alarm disabled; skip sending alarm");
            return;
        }
        long millis = triggerAtMillis > 0L ? triggerAtMillis : System.currentTimeMillis();
        String time = new SimpleDateFormat("HH:mm", Locale.getDefault()).format(millis);
        String text = label == null ? "" : label.trim();
        if (text.isEmpty()) {
            text = "鬧鐘";
        }
        JSONObject payload = new JSONObject();
        try {
            payload.put("time", time);
            payload.put("label", text);
        } catch (Exception e) {
            Log.e(TAG, "Build watch alarm payload failed", e);
            return;
        }
        byte[] bytes = payload.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8);
        Wearable.getNodeClient(context).getConnectedNodes()
                .addOnSuccessListener(nodes -> sendToNodes(context, nodes, bytes))
                .addOnFailureListener(e -> Log.e(TAG, "Get connected watch nodes failed", e));
    }

    static void sendDismiss(Context context) {
        if (!AlarmStore.isWatchAlarmEnabled(context)) {
            Log.d(TAG, "Watch alarm disabled; skip sending dismiss");
            return;
        }
        Wearable.getNodeClient(context).getConnectedNodes()
                .addOnSuccessListener(nodes -> sendToNodes(context, nodes, WATCH_DISMISS_PATH, new byte[0]))
                .addOnFailureListener(e -> Log.e(TAG, "Get connected watch nodes for dismiss failed", e));
        PutDataMapRequest request = PutDataMapRequest.create(WATCH_DISMISS_DATA_PATH);
        request.getDataMap().putLong("ts", System.currentTimeMillis());
        Wearable.getDataClient(context).putDataItem(request.asPutDataRequest());
    }

    static void sendTileState(Context context) {
        long now = System.currentTimeMillis();
        AlarmPair pair = findPrevNext(context, now);
        PutDataMapRequest request = PutDataMapRequest.create(TILE_STATE_PATH);
        DataMap map = request.getDataMap();
        map.putLong("updated_at", now);
        putAlarm(map, "prev", pair.prev, pair.prevAt);
        putAlarm(map, "next", pair.next, pair.nextAt);
        Wearable.getDataClient(context)
                .putDataItem(request.asPutDataRequest().setUrgent())
                .addOnSuccessListener(item -> Log.d(TAG, "Sent tile state to watch"))
                .addOnFailureListener(e -> Log.e(TAG, "Send tile state to watch failed", e));
        JSONObject payload = new JSONObject();
        try {
            payload.put("updated_at", now);
            putAlarm(payload, "prev", pair.prev, pair.prevAt);
            putAlarm(payload, "next", pair.next, pair.nextAt);
        } catch (Exception e) {
            Log.e(TAG, "Build tile state message failed", e);
            return;
        }
        byte[] bytes = payload.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8);
        Wearable.getNodeClient(context).getConnectedNodes()
                .addOnSuccessListener(nodes -> sendToNodes(context, nodes, TILE_STATE_PATH, bytes))
                .addOnFailureListener(e -> Log.e(TAG, "Get watch nodes for tile state failed", e));
    }

    private static AlarmPair findPrevNext(Context context, long now) {
        JSONArray alarms = AlarmStore.getAlarms(context);
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

    private static void putAlarm(DataMap map, String prefix, JSONObject alarm, long triggerAt) {
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

    private static void putAlarm(JSONObject json, String prefix, JSONObject alarm, long triggerAt) throws Exception {
        if (alarm == null || triggerAt <= 0L) {
            json.put(prefix + "_time", "--:--");
            json.put(prefix + "_date", "");
            json.put(prefix + "_label", "沒有資料");
            json.put(prefix + "_at", 0L);
            return;
        }
        json.put(prefix + "_time", new SimpleDateFormat("HH:mm", Locale.getDefault()).format(triggerAt));
        json.put(prefix + "_date", new SimpleDateFormat("dd/MM EEE", Locale.getDefault()).format(triggerAt));
        json.put(prefix + "_at", triggerAt);
        String label = alarm.optString("label", "").trim();
        json.put(prefix + "_label", label.isEmpty() ? "鬧鐘" : label);
    }

    private static void sendToNodes(Context context, List<Node> nodes, byte[] bytes) {
        if (nodes == null || nodes.isEmpty()) {
            Log.d(TAG, "No connected watch nodes");
            return;
        }
        for (Node node : nodes) {
            Wearable.getMessageClient(context)
                    .sendMessage(node.getId(), ALARM_PATH, bytes)
                    .addOnSuccessListener(id -> Log.d(TAG, "Sent alarm to watch: " + node.getDisplayName()))
                    .addOnFailureListener(e -> Log.e(TAG, "Send alarm to watch failed: " + node.getDisplayName(), e));
        }
    }

    private static void sendToNodes(Context context, List<Node> nodes, String path, byte[] bytes) {
        if (nodes == null || nodes.isEmpty()) {
            Log.d(TAG, "No connected watch nodes");
            return;
        }
        for (Node node : nodes) {
            Wearable.getMessageClient(context)
                    .sendMessage(node.getId(), path, bytes)
                    .addOnSuccessListener(id -> Log.d(TAG, "Sent message to watch: " + path))
                    .addOnFailureListener(e -> Log.e(TAG, "Send message to watch failed: " + path, e));
        }
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
