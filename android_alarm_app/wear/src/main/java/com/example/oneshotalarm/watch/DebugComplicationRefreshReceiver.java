package com.example.oneshotalarm.watch;

import android.content.BroadcastReceiver;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.util.Log;

import androidx.wear.watchface.complications.datasource.ComplicationDataSourceUpdateRequester;

public class DebugComplicationRefreshReceiver extends BroadcastReceiver {
    public static final String ACTION_REFRESH =
            "com.example.oneshotalarm.watch.DEBUG_REFRESH_COMPLICATIONS";
    private static final String TAG = "ShiftAlarmDebugRefresh";

    @Override
    public void onReceive(Context context, Intent intent) {
        if (intent == null || !ACTION_REFRESH.equals(intent.getAction())) {
            return;
        }
        requestUpdate(context, PrevAlarmComplicationDataSourceService.class);
        requestUpdate(context, NextAlarmComplicationDataSourceService.class);
        requestUpdate(context, PrevAlarmLabelLine1ComplicationDataSourceService.class);
        requestUpdate(context, PrevAlarmLabelLine2ComplicationDataSourceService.class);
        requestUpdate(context, NextAlarmLabelLine1ComplicationDataSourceService.class);
        requestUpdate(context, NextAlarmLabelLine2ComplicationDataSourceService.class);
    }

    private static void requestUpdate(Context context, Class<?> serviceClass) {
        try {
            ComplicationDataSourceUpdateRequester.create(
                    context,
                    new ComponentName(context, serviceClass)
            ).requestUpdateAll();
        } catch (Exception e) {
            Log.e(TAG, "Debug complication refresh failed", e);
        }
    }
}
