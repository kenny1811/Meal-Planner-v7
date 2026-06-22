package com.kenny.watchface.phone;

import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.os.BatteryManager;
import android.util.Log;

import com.google.android.gms.wearable.DataMap;
import com.google.android.gms.wearable.PutDataMapRequest;
import com.google.android.gms.wearable.PutDataRequest;
import com.google.android.gms.wearable.Wearable;

final class BatterySync {
    static final String PATH = "/phone_battery";
    static final String KEY_PERCENT = "percent";
    static final String KEY_TIMESTAMP = "timestamp";
    private static final String KEY_NONCE = "nonce";
    private static final String TAG = "BatterySync";

    private BatterySync() {
    }

    static int readBatteryPercent(Context context) {
        Intent battery = context.registerReceiver(null, new IntentFilter(Intent.ACTION_BATTERY_CHANGED));
        if (battery == null) {
            return -1;
        }
        int level = battery.getIntExtra(BatteryManager.EXTRA_LEVEL, -1);
        int scale = battery.getIntExtra(BatteryManager.EXTRA_SCALE, -1);
        if (level < 0 || scale <= 0) {
            return -1;
        }
        return Math.round(level * 100f / scale);
    }

    static void syncNow(Context context) {
        int percent = readBatteryPercent(context);
        if (percent < 0) {
            Log.w(TAG, "Battery percent unavailable");
            return;
        }

        PutDataMapRequest request = PutDataMapRequest.create(PATH);
        DataMap dataMap = request.getDataMap();
        dataMap.putInt(KEY_PERCENT, percent);
        dataMap.putLong(KEY_TIMESTAMP, System.currentTimeMillis());
        dataMap.putLong(KEY_NONCE, System.nanoTime());

        PutDataRequest putDataRequest = request.asPutDataRequest();
        putDataRequest.setUrgent();
        Wearable.getDataClient(context)
                .putDataItem(putDataRequest)
                .addOnSuccessListener(item -> Log.d(TAG, "Synced phone battery " + percent + "%"))
                .addOnFailureListener(error -> Log.w(TAG, "Phone battery sync failed", error));
    }
}
