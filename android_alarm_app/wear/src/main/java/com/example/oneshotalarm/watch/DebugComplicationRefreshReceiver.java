package com.example.oneshotalarm.watch;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

public class DebugComplicationRefreshReceiver extends BroadcastReceiver {
    public static final String ACTION_REFRESH =
            "com.example.oneshotalarm.watch.DEBUG_REFRESH_COMPLICATIONS";

    @Override
    public void onReceive(Context context, Intent intent) {
        if (intent == null || !ACTION_REFRESH.equals(intent.getAction())) {
            return;
        }
        // Recompute prev/next from the cached schedule before re-requesting the
        // complications, so a debug refresh reflects the latest schedule/format.
        WatchScheduleDisplayState.refreshFromCacheAndRequest(context);
    }
}
