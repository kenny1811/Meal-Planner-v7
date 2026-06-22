package com.kenny.watchface.wear;

import android.content.Context;
import android.content.SharedPreferences;

final class SunTimesStore {
    static final String PATH = "/sun_times";
    static final String KEY_DATE = "date";
    static final String KEY_SUNRISE = "sunrise";
    static final String KEY_SUNSET = "sunset";
    static final String KEY_TRANSIT = "transit";
    static final String KEY_TIMESTAMP = "timestamp";
    static final String KEY_SOURCE = "source";
    private static final String PREFS = "sun_times";

    private SunTimesStore() {
    }

    static void save(
            Context context,
            String date,
            String sunrise,
            String transit,
            String sunset,
            String source,
            long timestamp
    ) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                .edit()
                .putString(KEY_DATE, date)
                .putString(KEY_SUNRISE, sunrise)
                .putString(KEY_TRANSIT, transit)
                .putString(KEY_SUNSET, sunset)
                .putString(KEY_SOURCE, source)
                .putLong(KEY_TIMESTAMP, timestamp)
                .apply();
    }

    static SharedPreferences prefs(Context context) {
        return context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }
}
