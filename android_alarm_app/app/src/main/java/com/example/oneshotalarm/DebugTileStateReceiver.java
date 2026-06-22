package com.example.oneshotalarm;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

public class DebugTileStateReceiver extends BroadcastReceiver {
    public static final String ACTION_SEND_TILE_STATE =
            "com.example.oneshotalarm.ACTION_DEBUG_SEND_TILE_STATE";

    @Override
    public void onReceive(Context context, Intent intent) {
        if (intent != null && ACTION_SEND_TILE_STATE.equals(intent.getAction())) {
            WatchBridge.sendTileState(context);
        }
    }
}
