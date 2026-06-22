package com.kenny.watchface.wear;

import android.content.Context;
import android.util.Log;

import com.google.android.gms.wearable.Node;
import com.google.android.gms.wearable.Wearable;

import java.util.List;

final class PhoneBatteryRequest {
    private static final String PREFS = "phone_battery_request";
    private static final String KEY_LAST_REQUEST = "last_request";
    private static final String REQUEST_PATH = "/request_phone_battery";
    private static final long MIN_REQUEST_INTERVAL_MS = 60_000L;
    private static final String TAG = "PhoneBatteryRequest";

    private PhoneBatteryRequest() {
    }

    static void requestIfAllowed(Context context) {
        long now = System.currentTimeMillis();
        long lastRequest = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                .getLong(KEY_LAST_REQUEST, 0L);
        if (now - lastRequest < MIN_REQUEST_INTERVAL_MS) {
            return;
        }
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                .edit()
                .putLong(KEY_LAST_REQUEST, now)
                .apply();

        Wearable.getNodeClient(context)
                .getConnectedNodes()
                .addOnSuccessListener(nodes -> sendToNodes(context, nodes))
                .addOnFailureListener(error -> Log.w(TAG, "Could not find phone node", error));
    }

    private static void sendToNodes(Context context, List<Node> nodes) {
        for (Node node : nodes) {
            Wearable.getMessageClient(context)
                    .sendMessage(node.getId(), REQUEST_PATH, new byte[0])
                    .addOnSuccessListener(id -> Log.d(TAG, "Requested phone battery from " + node.getDisplayName()))
                    .addOnFailureListener(error -> Log.w(TAG, "Phone battery request failed", error));
        }
    }
}
