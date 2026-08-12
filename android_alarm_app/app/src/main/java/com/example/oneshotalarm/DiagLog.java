package com.example.oneshotalarm;

import android.content.Context;
import android.util.Log;

import java.io.File;
import java.io.FileOutputStream;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

/**
 * 純診斷用：喺 app 私有檔案記低鬧鐘事件（response 到 adb 靠唔住嘅問題——
 * wireless debugging 一熄，adb 開嘅 logcat process 就陪葬）。
 * 唔影響任何行為；寫入失敗一律吞聲。滿 512KB 轉一個舊檔，最多佔 1MB。
 */
final class DiagLog {
    private static final String TAG = "OneShotDiag";
    private static final long MAX_BYTES = 512 * 1024;

    private DiagLog() {
    }

    static synchronized void log(Context context, String message) {
        try {
            File file = new File(context.getApplicationContext().getFilesDir(), "alarm_diag.log");
            if (file.length() > MAX_BYTES) {
                File old = new File(file.getParentFile(), "alarm_diag.1.log");
                if (old.exists()) {
                    old.delete();
                }
                file.renameTo(old);
            }
            String line = new SimpleDateFormat("dd-MM HH:mm:ss.SSS", Locale.US).format(new Date())
                    + " " + message + "\n";
            try (FileOutputStream out = new FileOutputStream(file, true)) {
                out.write(line.getBytes("UTF-8"));
            }
        } catch (Exception e) {
            Log.w(TAG, "diag log failed", e);
        }
    }
}
