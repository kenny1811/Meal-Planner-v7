package com.kenny.watchface.wear;

import android.util.Log;

import com.google.android.gms.wearable.DataEvent;
import com.google.android.gms.wearable.DataEventBuffer;
import com.google.android.gms.wearable.DataMap;
import com.google.android.gms.wearable.DataMapItem;
import com.google.android.gms.wearable.WearableListenerService;

public class SunTimesDataListenerService extends WearableListenerService {
    private static final String TAG = "SunTimesData";

    @Override
    public void onDataChanged(DataEventBuffer dataEvents) {
        for (DataEvent event : dataEvents) {
            if (event.getType() != DataEvent.TYPE_CHANGED) {
                continue;
            }
            if (!SunTimesStore.PATH.equals(event.getDataItem().getUri().getPath())) {
                continue;
            }

            DataMap dataMap = DataMapItem.fromDataItem(event.getDataItem()).getDataMap();
            String date = dataMap.getString(SunTimesStore.KEY_DATE, "");
            String sunrise = dataMap.getString(SunTimesStore.KEY_SUNRISE, "");
            String transit = dataMap.getString(SunTimesStore.KEY_TRANSIT, "");
            String sunset = dataMap.getString(SunTimesStore.KEY_SUNSET, "");
            String source = dataMap.getString(SunTimesStore.KEY_SOURCE, "HKO SRS");
            long timestamp = dataMap.getLong(SunTimesStore.KEY_TIMESTAMP, System.currentTimeMillis());
            if (!date.isEmpty() && !sunrise.isEmpty() && !sunset.isEmpty()) {
                SunTimesStore.save(this, date, sunrise, transit, sunset, source, timestamp);
                SunColorCalculator.State color = SunColorCalculator.current(this);
                Log.d(TAG, "Received HKO sun times "
                        + date
                        + " "
                        + sunrise
                        + "/"
                        + sunset
                        + "; current color "
                        + color.bucket
                        + " "
                        + color.color);
            }
        }
    }
}
