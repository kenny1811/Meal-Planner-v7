package com.kenny.watchface.wear;

import android.content.ComponentName;
import android.util.Log;

import androidx.wear.watchface.complications.datasource.ComplicationDataSourceUpdateRequester;

import com.google.android.gms.wearable.DataEvent;
import com.google.android.gms.wearable.DataEventBuffer;
import com.google.android.gms.wearable.DataMap;
import com.google.android.gms.wearable.DataMapItem;
import com.google.android.gms.wearable.WearableListenerService;

public class PhoneBatteryDataListenerService extends WearableListenerService {
    private static final String TAG = "PhoneBatteryData";

    @Override
    public void onDataChanged(DataEventBuffer dataEvents) {
        for (DataEvent event : dataEvents) {
            if (event.getType() != DataEvent.TYPE_CHANGED) {
                continue;
            }
            if (!PhoneBatteryStore.PATH.equals(event.getDataItem().getUri().getPath())) {
                continue;
            }

            DataMap dataMap = DataMapItem.fromDataItem(event.getDataItem()).getDataMap();
            int percent = dataMap.getInt(PhoneBatteryStore.KEY_PERCENT, -1);
            long timestamp = dataMap.getLong(PhoneBatteryStore.KEY_TIMESTAMP, System.currentTimeMillis());
            if (percent >= 0) {
                Log.d(TAG, "Received phone battery " + percent + "%");
                PhoneBatteryStore.save(this, percent, timestamp);
                requestComplicationUpdate();
            }
        }
    }

    private void requestComplicationUpdate() {
        ComponentName componentName = new ComponentName(
                this,
                PhoneBatteryComplicationDataSourceService.class
        );
        ComplicationDataSourceUpdateRequester
                .create(this, componentName)
                .requestUpdateAll();
    }
}
