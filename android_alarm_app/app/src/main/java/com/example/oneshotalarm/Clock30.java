package com.example.oneshotalarm;

import java.text.SimpleDateFormat;
import java.util.Calendar;
import java.util.Locale;

/**
 * 30 小時制顯示：凌晨 00:00–05:59 屬前一日，寫成 24:00–29:59。
 * 全 project（電腦、電話、手錶）都係咁睇時間——顯示層轉，底層時間戳一個字都唔郁。
 */
final class Clock30 {
    private Clock30() {
    }

    /** epoch 毫秒 → "HH:mm"（凌晨嗰段出 24:00–29:59）。 */
    static String format(long millis) {
        Calendar calendar = Calendar.getInstance();
        calendar.setTimeInMillis(millis);
        int hour = calendar.get(Calendar.HOUR_OF_DAY);
        int minute = calendar.get(Calendar.MINUTE);
        return String.format(Locale.US, "%02d:%02d", hour < 6 ? hour + 24 : hour, minute);
    }

    /** 日期 + 時間（例如上次匯入時間）——日期都要跟 30 小時制，凌晨算前一日。 */
    static String formatDateTime(long millis) {
        Calendar calendar = Calendar.getInstance();
        calendar.setTimeInMillis(millis);
        int hour = calendar.get(Calendar.HOUR_OF_DAY);
        if (hour < 6) {
            calendar.add(Calendar.DAY_OF_MONTH, -1);
        }
        String day = new SimpleDateFormat("yyyy-MM-dd", Locale.US).format(calendar.getTime());
        return day + " " + format(millis);
    }
}
