package com.example.oneshotalarm.watch;

import android.content.Context;
import android.util.Log;

import com.google.android.gms.wearable.Node;
import com.google.android.gms.wearable.Wearable;

import java.util.List;

final class AlarmStateRefresh {
    private static final String PREFS = "alarm_state_refresh";
    private static final String KEY_LAST_REQUEST = "last_request";
    private static final String REQUEST_PATH = "/oneshotalarm/tile-state-request";
    private static final long MIN_REQUEST_INTERVAL_MS = 60_000L;
    private static final String TAG = "ShiftAlarmComplication";

    private AlarmStateRefresh() {
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
                .addOnFailureListener(error -> Log.e(TAG, "Get phone nodes failed", error));
    }

    private static void sendToNodes(Context context, List<Node> nodes) {
        if (nodes == null || nodes.isEmpty()) {
            Log.d(TAG, "No phone node for alarm state refresh");
            return;
        }
        for (Node node : nodes) {
            Wearable.getMessageClient(context)
                    .sendMessage(node.getId(), REQUEST_PATH, new byte[0])
                    .addOnSuccessListener(id -> Log.d(TAG, "Requested alarm state from phone"))
                    .addOnFailureListener(error -> Log.e(TAG, "Alarm state request failed", error));
        }
    }
}
