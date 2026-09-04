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
            if (percent >= 0) {
                Log.d(TAG, "Received phone battery " + percent + "%");
                // Stamp with the watch clock, not the phone's: the complication ages this
                // value against System.currentTimeMillis() here, so a skew between the two
                // devices would otherwise make fresh data look stale (or the reverse).
                PhoneBatteryStore.save(this, percent, System.currentTimeMillis());
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
