package com.example.oneshotalarm;

import android.content.Context;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;

import com.google.android.gms.wearable.DataMap;
import com.google.android.gms.wearable.Node;
import com.google.android.gms.wearable.PutDataMapRequest;
import com.google.android.gms.wearable.Wearable;

import org.json.JSONArray;
import org.json.JSONObject;

import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Locale;

final class WatchBridge {
    private static final String TAG = "OneShotWatchBridge";
    private static final String WATCH_DISMISS_PATH = "/oneshotalarm/watch-dismiss";
    private static final String WATCH_DISMISS_DATA_PATH = "/oneshotalarm/watch-dismiss-data";
    private static final String TILE_STATE_PATH = "/oneshotalarm/tile-state";

    private WatchBridge() {
    }

    static void sendDismiss(Context context, String alarmId) {
        Context appContext = context.getApplicationContext();
        if (!AlarmStore.isWatchAlarmEnabled(appContext)) {
            Log.d(TAG, "Watch alarm disabled; skip sending dismiss");
            return;
        }
        sendDismissNow(appContext, alarmId);
        Handler handler = new Handler(Looper.getMainLooper());
        handler.postDelayed(() -> sendDismissNow(appContext, alarmId), 300);
        handler.postDelayed(() -> sendDismissNow(appContext, alarmId), 900);
        handler.postDelayed(() -> sendDismissNow(appContext, alarmId), 1500);
    }

    private static void sendDismissNow(Context context, String alarmId) {
        byte[] payload = dismissPayload(alarmId);
        Wearable.getNodeClient(context).getConnectedNodes()
                .addOnSuccessListener(nodes -> sendToNodes(context, nodes, WATCH_DISMISS_PATH, payload))
                .addOnFailureListener(e -> Log.e(TAG, "Get connected watch nodes for dismiss failed", e));
        PutDataMapRequest request = PutDataMapRequest.create(WATCH_DISMISS_DATA_PATH);
        request.getDataMap().putLong("ts", System.currentTimeMillis());
        request.getDataMap().putString("alarm_id", alarmId == null ? "" : alarmId);
        Wearable.getDataClient(context)
                .putDataItem(request.asPutDataRequest().setUrgent())
                .addOnSuccessListener(item -> Log.d(TAG, "Sent dismiss data to watch"))
                .addOnFailureListener(e -> Log.e(TAG, "Send dismiss data to watch failed", e));
    }

    static void sendTileState(Context context) {
        long now = System.currentTimeMillis();
        AlarmPair pair = findPrevNext(context, now);
        PutDataMapRequest request = PutDataMapRequest.create(TILE_STATE_PATH);
        DataMap map = request.getDataMap();
        map.putLong("updated_at", now);
        map.putString("plan_date", AlarmStore.getPlanDate(context));
        map.putString("roster_code", AlarmStore.getRosterCode(context));
        putAlarm(map, "prev", pair.prev, pair.prevAt);
        putAlarm(map, "next", pair.next, pair.nextAt);
        JSONArray scheduleItems = buildScheduleItems(context);
        map.putString("schedule_items_json", scheduleItems.toString());
        Wearable.getDataClient(context)
                .putDataItem(request.asPutDataRequest().setUrgent())
                .addOnSuccessListener(item -> Log.d(TAG, "Sent tile state to watch"))
                .addOnFailureListener(e -> Log.e(TAG, "Send tile state to watch failed", e));
        JSONObject payload = new JSONObject();
        try {
            payload.put("updated_at", now);
            payload.put("plan_date", AlarmStore.getPlanDate(context));
            payload.put("roster_code", AlarmStore.getRosterCode(context));
            putAlarm(payload, "prev", pair.prev, pair.prevAt);
            putAlarm(payload, "next", pair.next, pair.nextAt);
            payload.put("schedule_items", scheduleItems);
        } catch (Exception e) {
            Log.e(TAG, "Build tile state message failed", e);
            return;
        }
        byte[] bytes = payload.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8);
        Wearable.getNodeClient(context).getConnectedNodes()
                .addOnSuccessListener(nodes -> sendToNodes(context, nodes, TILE_STATE_PATH, bytes))
                .addOnFailureListener(e -> Log.e(TAG, "Get watch nodes for tile state failed", e));
    }

    private static byte[] dismissPayload(String alarmId) {
        JSONObject payload = new JSONObject();
        try {
            payload.put("ts", System.currentTimeMillis());
            payload.put("alarm_id", alarmId == null ? "" : alarmId);
        } catch (Exception ignored) {
        }
        return payload.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8);
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

    private static JSONArray buildScheduleItems(Context context) {
        JSONArray alarms = AlarmStore.getAlarms(context);
        ArrayList<JSONObject> ordered = new ArrayList<>();
        for (int i = 0; i < alarms.length(); i++) {
            JSONObject alarm = alarms.optJSONObject(i);
            if (alarm == null || alarm.optLong("trigger_at_epoch_ms", 0L) <= 0L) {
                continue;
            }
            ordered.add(alarm);
        }
        Collections.sort(ordered, (left, right) -> Long.compare(
                left.optLong("trigger_at_epoch_ms", 0L),
                right.optLong("trigger_at_epoch_ms", 0L)
        ));

        JSONArray rows = new JSONArray();
        SimpleDateFormat timeFormat = new SimpleDateFormat("HH:mm", Locale.getDefault());
        for (int i = 0; i < ordered.size(); i++) {
            JSONObject alarm = ordered.get(i);
            long triggerAt = alarm.optLong("trigger_at_epoch_ms", 0L);
            String label = alarm.optString("label", "").trim();
            if (label.isEmpty()) {
                label = "鬧鐘";
            }
            JSONObject row = new JSONObject();
            try {
                row.put("id", alarm.optString("id", ""));
                row.put("time", timeFormat.format(triggerAt));
                row.put("content", label);
                row.put("at", triggerAt);
                rows.put(row);
            } catch (Exception e) {
                Log.e(TAG, "Build schedule tile row failed", e);
            }
        }
        return rows;
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
