package com.example.oneshotalarm.watch;

import android.content.Context;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;

import com.google.android.gms.wearable.Node;
import com.google.android.gms.wearable.PutDataMapRequest;
import com.google.android.gms.wearable.Wearable;

import org.json.JSONObject;

import java.nio.charset.StandardCharsets;
import java.util.List;

final class WatchDismissBridge {
    private static final String TAG = "ShiftAlarmWatch";
    private static final String DISMISS_PATH = "/oneshotalarm/dismiss";
    private static final String DISMISS_DATA_PATH = "/oneshotalarm/dismiss-data";

    private WatchDismissBridge() {
    }

    static void sendDismiss(Context context, String alarmId) {
        Context appContext = context.getApplicationContext();
        String id = alarmId == null ? "" : alarmId;
        long dismissId = System.currentTimeMillis();
        Handler handler = new Handler(Looper.getMainLooper());
        sendDismissNow(appContext, id, dismissId);
        handler.postDelayed(() -> sendDismissNow(appContext, id, dismissId), 300);
        handler.postDelayed(() -> sendDismissNow(appContext, id, dismissId), 900);
        handler.postDelayed(() -> sendDismissNow(appContext, id, dismissId), 1500);
    }

    private static void sendDismissNow(Context context, String alarmId, long dismissId) {
        sendDismissData(context, alarmId, dismissId);
        sendDismissMessage(context, alarmId, dismissId);
    }

    private static void sendDismissData(Context context, String alarmId, long dismissId) {
        PutDataMapRequest request = PutDataMapRequest.create(DISMISS_DATA_PATH);
        request.getDataMap().putLong("dismiss_id", dismissId);
        request.getDataMap().putLong("ts", System.currentTimeMillis());
        request.getDataMap().putString("alarm_id", alarmId);
        Wearable.getDataClient(context)
                .putDataItem(request.asPutDataRequest().setUrgent())
                .addOnSuccessListener(item -> Log.d(TAG, "Sent dismiss data to phone: " + alarmId))
                .addOnFailureListener(e -> Log.e(TAG, "Send dismiss data to phone failed", e));
    }

    private static void sendDismissMessage(Context context, String alarmId, long dismissId) {
        JSONObject json = new JSONObject();
        try {
            json.put("dismiss_id", dismissId);
            json.put("alarm_id", alarmId);
        } catch (Exception ignored) {
        }
        byte[] payload = json.toString().getBytes(StandardCharsets.UTF_8);
        Wearable.getNodeClient(context).getConnectedNodes()
                .addOnSuccessListener(nodes -> sendDismissToNodes(context, nodes, payload, alarmId))
                .addOnFailureListener(e -> Log.e(TAG, "Get phone nodes for dismiss failed", e));
    }

    private static void sendDismissToNodes(
            Context context,
            List<Node> nodes,
            byte[] payload,
            String alarmId
    ) {
        if (nodes == null || nodes.isEmpty()) {
            Log.d(TAG, "No phone nodes for dismiss: " + alarmId);
            return;
        }
        for (Node node : nodes) {
            Wearable.getMessageClient(context)
                    .sendMessage(node.getId(), DISMISS_PATH, payload)
                    .addOnSuccessListener(id -> Log.d(TAG, "Sent dismiss message to phone: " + alarmId))
                    .addOnFailureListener(e -> Log.e(TAG, "Send dismiss message to phone failed", e));
        }
    }
}
