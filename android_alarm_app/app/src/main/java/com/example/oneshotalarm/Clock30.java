package com.example.oneshotalarm;

import java.text.SimpleDateFormat;
import java.util.Calendar;
import java.util.Locale;

/**
 * 30 小時制顯示：凌晨 00:00–05:59 屬前一日，寫成 24:00–29:59。
 * 全 project（電腦、電話、手錶）都係咁睇時間——顯示層轉，底層時間戳一個字都唔郁。
 * 電話端所有 30 小時制格式化都經呢度（以前 MainActivity 另有一份硬寫 Asia/Hong_Kong 嘅）。
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
        return shiftDay(millis, "yyyy-MM-dd") + " " + format(millis);
    }

    /** "dd/MM/yyyy EEE HH:mm:ss"（餐單頁 Last update 用），30 小時制。 */
    static String formatFull(long millis) {
        Calendar calendar = Calendar.getInstance();
        calendar.setTimeInMillis(millis);
        int hour = calendar.get(Calendar.HOUR_OF_DAY);
        return String.format(
                Locale.US,
                "%s %02d:%02d:%02d",
                shiftDay(millis, "dd/MM/yyyy EEE"),
                hour < 6 ? hour + 24 : hour,
                calendar.get(Calendar.MINUTE),
                calendar.get(Calendar.SECOND)
        );
    }

    /** 30 小時制嘅「今日」yyyy-MM-dd：凌晨 00:00–05:59 仍然算前一日。 */
    static String todayIso() {
        return shiftDay(System.currentTimeMillis(), "yyyy-MM-dd");
    }

    /** "yyyy-MM-dd" → "dd/MM/yyyy EEE"（行位表 header／餐單日期用）；唔似 ISO 就原樣回傳。 */
    static String formatPlanDate(String iso) {
        if (iso == null || iso.trim().isEmpty()) {
            return "";
        }
        String[] parts = iso.split("-");
        if (parts.length != 3) {
            return iso;
        }
        try {
            int year = Integer.parseInt(parts[0]);
            int month = Integer.parseInt(parts[1]);
            int day = Integer.parseInt(parts[2]);
            Calendar calendar = Calendar.getInstance();
            calendar.set(year, month - 1, day, 0, 0, 0);
            calendar.set(Calendar.MILLISECOND, 0);
            String weekday = new SimpleDateFormat("EEE", Locale.getDefault()).format(calendar.getTime());
            return parts[2] + "/" + parts[1] + "/" + parts[0] + " " + weekday;
        } catch (RuntimeException ex) {
            return parts[2] + "/" + parts[1] + "/" + parts[0];
        }
    }

    private static String shiftDay(long millis, String pattern) {
        Calendar calendar = Calendar.getInstance();
        calendar.setTimeInMillis(millis);
        if (calendar.get(Calendar.HOUR_OF_DAY) < 6) {
            calendar.add(Calendar.DAY_OF_MONTH, -1);
        }
        return new SimpleDateFormat(pattern, Locale.US).format(calendar.getTime());
    }
}
