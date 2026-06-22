package com.kenny.watchface.wear;

import android.content.Context;
import android.content.SharedPreferences;

final class PhoneBatteryStore {
    static final String PATH = "/phone_battery";
    static final String KEY_PERCENT = "percent";
    static final String KEY_TIMESTAMP = "timestamp";
    private static final String PREFS = "phone_battery";

    private PhoneBatteryStore() {
    }

    static void save(Context context, int percent, long timestamp) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                .edit()
                .putInt(KEY_PERCENT, percent)
                .putLong(KEY_TIMESTAMP, timestamp)
                .apply();
    }

    static int percent(Context context) {
        return prefs(context).getInt(KEY_PERCENT, -1);
    }

    static long timestamp(Context context) {
        return prefs(context).getLong(KEY_TIMESTAMP, 0L);
    }

    private static SharedPreferences prefs(Context context) {
        return context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }
}
