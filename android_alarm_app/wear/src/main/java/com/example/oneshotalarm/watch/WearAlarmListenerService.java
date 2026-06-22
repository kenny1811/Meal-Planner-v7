package com.example.oneshotalarm.watch;

import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.ComponentName;
import android.util.Log;

import androidx.wear.tiles.TileService;
import androidx.wear.watchface.complications.datasource.ComplicationDataSourceUpdateRequester;

import com.google.android.gms.wearable.DataMap;
import com.google.android.gms.wearable.DataMapItem;
import com.google.android.gms.wearable.MessageEvent;
import com.google.android.gms.wearable.DataEvent;
import com.google.android.gms.wearable.DataEventBuffer;
import com.google.android.gms.wearable.WearableListenerService;

import org.json.JSONObject;

import java.nio.charset.StandardCharsets;

public class WearAlarmListenerService extends WearableListenerService {
    private static final String TAG = "ShiftAlarmWatch";
    private static final String ALARM_PATH = "/oneshotalarm/alarm";
    private static final String WATCH_DISMISS_PATH = "/oneshotalarm/watch-dismiss";
    private static final String WATCH_DISMISS_DATA_PATH = "/oneshotalarm/watch-dismiss-data";
    private static final String TILE_STATE_PATH = "/oneshotalarm/tile-state";
    private static final String PREFS = "watch_alarm_listener";
    private static final String KEY_LAST_ALARM_KEY = "last_alarm_key";
    private static final String KEY_LAST_ALARM_AT = "last_alarm_at";
    private static final long DUPLICATE_ALARM_MS = 2 * 60 * 1000L;

    @Override
    public void onDataChanged(DataEventBuffer dataEvents) {
        for (DataEvent event : dataEvents) {
            if (event != null
                    && event.getDataItem() != null
                    && event.getDataItem().getUri() != null
                    && WATCH_DISMISS_DATA_PATH.equals(event.getDataItem().getUri().getPath())) {
                dismissWatchAlarm();
                return;
            }
            if (event != null
                    && event.getDataItem() != null
                    && event.getDataItem().getUri() != null
                    && TILE_STATE_PATH.equals(event.getDataItem().getUri().getPath())) {
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
            dismissWatchAlarm();
            return;
        }
        if (TILE_STATE_PATH.equals(messageEvent.getPath())) {
            saveTileState(new String(messageEvent.getData(), StandardCharsets.UTF_8));
            return;
        }
        if (!ALARM_PATH.equals(messageEvent.getPath())) {
            return;
        }
        String time = "--:--";
        String label = "鬧鐘";
        try {
            JSONObject json = new JSONObject(new String(messageEvent.getData(), StandardCharsets.UTF_8));
            time = json.optString("time", time);
            label = json.optString("label", label);
        } catch (Exception e) {
            Log.e(TAG, "Parse alarm message failed", e);
        }
        String alarmKey = time + "\n" + label;
        if (isDuplicateAlarm(alarmKey)) {
            Log.d(TAG, "Duplicate watch alarm ignored");
            return;
        }
        WatchAlarmService.start(this, alarmKey);
        Intent intent = new Intent(this, WatchAlarmActivity.class);
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        intent.putExtra(WatchAlarmActivity.EXTRA_TIME, time);
        intent.putExtra(WatchAlarmActivity.EXTRA_LABEL, label);
        startActivity(intent);
    }

    private void dismissWatchAlarm() {
        WatchAlarmService.stop(this);
        Intent intent = new Intent(WatchAlarmActivity.ACTION_DISMISS_LOCAL);
        intent.setPackage(getPackageName());
        sendBroadcast(intent);
    }

    private boolean isDuplicateAlarm(String alarmKey) {
        String key = alarmKey == null ? "" : alarmKey;
        if (key.isEmpty()) {
            return false;
        }
        SharedPreferences preferences = getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        String previousKey = preferences.getString(KEY_LAST_ALARM_KEY, "");
        long previousAt = preferences.getLong(KEY_LAST_ALARM_AT, 0L);
        long now = System.currentTimeMillis();
        if (key.equals(previousKey) && now - previousAt >= 0L && now - previousAt < DUPLICATE_ALARM_MS) {
            return true;
        }
        preferences.edit()
                .putString(KEY_LAST_ALARM_KEY, key)
                .putLong(KEY_LAST_ALARM_AT, now)
                .apply();
        return false;
    }

    private void clearLastAlarm() {
        getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
                .remove(KEY_LAST_ALARM_KEY)
                .remove(KEY_LAST_ALARM_AT)
                .apply();
    }

    private void saveTileState(DataMap map) {
        if (map == null) {
            return;
        }
        getSharedPreferences(PrevNextAlarmTileService.PREFS, Context.MODE_PRIVATE).edit()
                .putString(PrevNextAlarmTileService.KEY_PREV_TIME, map.getString("prev_time", "--:--"))
                .putString(PrevNextAlarmTileService.KEY_PREV_DATE, map.getString("prev_date", ""))
                .putString(PrevNextAlarmTileService.KEY_PREV_LABEL, map.getString("prev_label", "沒有資料"))
                .putLong(PrevNextAlarmTileService.KEY_PREV_AT, map.getLong("prev_at", 0L))
                .putString(PrevNextAlarmTileService.KEY_NEXT_TIME, map.getString("next_time", "--:--"))
                .putString(PrevNextAlarmTileService.KEY_NEXT_DATE, map.getString("next_date", ""))
                .putString(PrevNextAlarmTileService.KEY_NEXT_LABEL, map.getString("next_label", "沒有資料"))
                .putLong(PrevNextAlarmTileService.KEY_NEXT_AT, map.getLong("next_at", 0L))
                .putLong(PrevNextAlarmTileService.KEY_UPDATED_AT, map.getLong("updated_at", System.currentTimeMillis()))
                .apply();
        try {
            TileService.getUpdater(this).requestUpdate(PrevNextAlarmTileService.class);
            requestAlarmComplicationUpdates();
        } catch (Exception e) {
            Log.e(TAG, "Request tile update failed", e);
        }
    }

    private void saveTileState(String rawJson) {
        try {
            JSONObject json = new JSONObject(rawJson == null ? "{}" : rawJson);
            getSharedPreferences(PrevNextAlarmTileService.PREFS, Context.MODE_PRIVATE).edit()
                    .putString(PrevNextAlarmTileService.KEY_PREV_TIME, json.optString("prev_time", "--:--"))
                    .putString(PrevNextAlarmTileService.KEY_PREV_DATE, json.optString("prev_date", ""))
                    .putString(PrevNextAlarmTileService.KEY_PREV_LABEL, json.optString("prev_label", "沒有資料"))
                    .putLong(PrevNextAlarmTileService.KEY_PREV_AT, json.optLong("prev_at", 0L))
                    .putString(PrevNextAlarmTileService.KEY_NEXT_TIME, json.optString("next_time", "--:--"))
                    .putString(PrevNextAlarmTileService.KEY_NEXT_DATE, json.optString("next_date", ""))
                    .putString(PrevNextAlarmTileService.KEY_NEXT_LABEL, json.optString("next_label", "沒有資料"))
                    .putLong(PrevNextAlarmTileService.KEY_NEXT_AT, json.optLong("next_at", 0L))
                    .putLong(PrevNextAlarmTileService.KEY_UPDATED_AT, json.optLong("updated_at", System.currentTimeMillis()))
                    .apply();
            TileService.getUpdater(this).requestUpdate(PrevNextAlarmTileService.class);
            requestAlarmComplicationUpdates();
        } catch (Exception e) {
            Log.e(TAG, "Save tile state message failed", e);
        }
    }

    private void requestAlarmComplicationUpdates() {
        requestAlarmComplicationUpdate(PrevAlarmComplicationDataSourceService.class);
        requestAlarmComplicationUpdate(NextAlarmComplicationDataSourceService.class);
        requestAlarmComplicationUpdate(PrevAlarmLabelLine1ComplicationDataSourceService.class);
        requestAlarmComplicationUpdate(PrevAlarmLabelLine2ComplicationDataSourceService.class);
        requestAlarmComplicationUpdate(NextAlarmLabelLine1ComplicationDataSourceService.class);
        requestAlarmComplicationUpdate(NextAlarmLabelLine2ComplicationDataSourceService.class);
    }

    private void requestAlarmComplicationUpdate(Class<?> serviceClass) {
        try {
            ComplicationDataSourceUpdateRequester.create(
                    this,
                    new ComponentName(this, serviceClass)
            ).requestUpdateAll();
        } catch (Exception e) {
            Log.e(TAG, "Request alarm complication update failed", e);
        }
    }
}
