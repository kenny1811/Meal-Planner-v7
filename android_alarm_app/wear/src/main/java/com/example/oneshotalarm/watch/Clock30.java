package com.example.oneshotalarm.watch;

import java.util.Calendar;
import java.util.Locale;

/**
 * 30 小時制顯示：凌晨 00:00–05:59 屬前一日，寫成 24:00–29:59。
 * 同電話嗰個 Clock30 一樣規則（兩個 module 唔共用 code，所以各有一份）。
 */
public final class Clock30 {
    private Clock30() {
    }

    public static String format(long millis) {
        Calendar calendar = Calendar.getInstance();
        calendar.setTimeInMillis(millis);
        int hour = calendar.get(Calendar.HOUR_OF_DAY);
        int minute = calendar.get(Calendar.MINUTE);
        return String.format(Locale.US, "%02d:%02d", hour < 6 ? hour + 24 : hour, minute);
    }
}
