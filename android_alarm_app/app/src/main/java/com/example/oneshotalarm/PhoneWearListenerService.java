package com.example.oneshotalarm;

import android.content.Intent;
import android.util.Log;

import com.google.android.gms.wearable.DataEvent;
import com.google.android.gms.wearable.DataEventBuffer;
import com.google.android.gms.wearable.MessageEvent;
import com.google.android.gms.wearable.WearableListenerService;

public class PhoneWearListenerService extends WearableListenerService {
    private static final String TAG = "OneShotWearListener";
    private static final String DISMISS_PATH = "/oneshotalarm/dismiss";
    private static final String DISMISS_DATA_PATH = "/oneshotalarm/dismiss-data";
    private static final String TILE_STATE_REQUEST_PATH = "/oneshotalarm/tile-state-request";

    @Override
    public void onDataChanged(DataEventBuffer dataEvents) {
        for (DataEvent event : dataEvents) {
            if (event != null
                    && event.getDataItem() != null
                    && event.getDataItem().getUri() != null
                    && DISMISS_DATA_PATH.equals(event.getDataItem().getUri().getPath())) {
                Log.d(TAG, "Received watch dismiss data");
                dispatchWatchDismiss();
                return;
            }
        }
    }

    @Override
    public void onMessageReceived(MessageEvent messageEvent) {
        if (messageEvent == null) {
            return;
        }
        if (TILE_STATE_REQUEST_PATH.equals(messageEvent.getPath())) {
            Log.d(TAG, "Received watch tile state request");
            WatchBridge.sendTileState(this);
            return;
        }
        if (!DISMISS_PATH.equals(messageEvent.getPath())) {
            return;
        }
        Log.d(TAG, "Received watch dismiss message");
        dispatchWatchDismiss();
    }

    private void dispatchWatchDismiss() {
        AlarmActivity.markWatchDismiss(this);
        WatchBridge.sendTileState(this);
        Intent intent = new Intent(AlarmActivity.ACTION_WATCH_DISMISS);
        intent.setPackage(getPackageName());
        sendBroadcast(intent);
    }
}
