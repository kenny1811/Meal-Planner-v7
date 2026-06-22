package com.kenny.watchface.phone;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

public class SunTimesBootReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        if (Intent.ACTION_BOOT_COMPLETED.equals(intent.getAction())) {
            SunTimesSync.scheduleDailyAt0530(context);
        }
    }
}
