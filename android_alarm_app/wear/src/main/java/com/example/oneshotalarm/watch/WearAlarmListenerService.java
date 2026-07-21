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

}
