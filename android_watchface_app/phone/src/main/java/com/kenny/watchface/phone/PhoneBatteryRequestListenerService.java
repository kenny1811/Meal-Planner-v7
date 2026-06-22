package com.kenny.watchface.phone;

import android.util.Log;

import com.google.android.gms.wearable.MessageEvent;
import com.google.android.gms.wearable.WearableListenerService;

public class PhoneBatteryRequestListenerService extends WearableListenerService {
    static final String REQUEST_PATH = "/request_phone_battery";
    private static final String TAG = "PhoneBatteryRequest";

    @Override
    public void onMessageReceived(MessageEvent messageEvent) {
        if (REQUEST_PATH.equals(messageEvent.getPath())) {
            Log.d(TAG, "Phone battery requested by watch");
            BatterySync.syncNow(this);
        }
    }
}
