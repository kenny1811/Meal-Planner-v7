package com.example.oneshotalarm.watch;

import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.media.AudioAttributes;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.VibrationEffect;
import android.os.Vibrator;
import android.os.VibratorManager;

public class WatchAlarmService extends Service {
    static final String ACTION_START = "com.example.oneshotalarm.watch.ACTION_START";
    static final String ACTION_STOP = "com.example.oneshotalarm.watch.ACTION_STOP";
    static final String ACTION_SET_STRENGTH = "com.example.oneshotalarm.watch.ACTION_SET_STRENGTH";
    static final String EXTRA_STRENGTH = "strength";
    static final String STRENGTH_STRONG = "strong";
    static final String STRENGTH_MEDIUM = "medium";
    static final String STRENGTH_WEAK = "weak";
    static final String STRENGTH_ZIG = "zig";
    static final String STRENGTH_PULSE = "pulse";
    private static final String PREFS = "watch_alarm";
    private static final String KEY_STRENGTH = "strength";
    private static final String KEY_ACTIVE = "active";
    private static final String KEY_LAST_ALARM_KEY = "last_alarm_key";
    private static final String KEY_LAST_STARTED_AT = "last_started_at";
    private static final String EXTRA_ALARM_KEY = "alarm_key";
    private static final long MAX_ALARM_MS = 60 * 1000L;
    private static final long DUPLICATE_ALARM_MS = 2 * 60 * 1000L;

    private Vibrator vibrator;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final Runnable autoStopRunnable = () -> {
        stopAlert();
        Intent intent = new Intent(WatchAlarmActivity.ACTION_DISMISS_LOCAL);
        intent.setPackage(getPackageName());
        sendBroadcast(intent);
        stopSelf();
    };

    static void start(Context context, String alarmKey) {
        Intent intent = new Intent(context, WatchAlarmService.class);
        intent.setAction(ACTION_START);
        intent.putExtra(EXTRA_ALARM_KEY, alarmKey == null ? "" : alarmKey);
        context.startService(intent);
    }

    static void stop(Context context) {
        Intent intent = new Intent(context, WatchAlarmService.class);
        markInactive(context);
        context.stopService(intent);
    }

    static void setStrength(Context context, String strength) {
        Intent intent = new Intent(context, WatchAlarmService.class);
        intent.setAction(ACTION_SET_STRENGTH);
        intent.putExtra(EXTRA_STRENGTH, strength);
        context.startService(intent);
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && ACTION_STOP.equals(intent.getAction())) {
            markInactive(this);
            stopAlert();
            stopSelf();
            return START_NOT_STICKY;
        }
        if (intent != null && ACTION_SET_STRENGTH.equals(intent.getAction())) {
            saveStrength(intent.getStringExtra(EXTRA_STRENGTH));
            return START_NOT_STICKY;
        }
        String alarmKey = intent == null ? "" : intent.getStringExtra(EXTRA_ALARM_KEY);
        if (isDuplicateActiveAlarm(alarmKey)) {
            return START_NOT_STICKY;
        }
        markActive(alarmKey);
        startVibration();
        scheduleAutoStop();
        return START_NOT_STICKY;
    }

    @Override
    public void onDestroy() {
        markInactive(this);
        stopAlert();
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    private void startVibration() {
        if (vibrator != null) {
            vibrator.cancel();
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            VibratorManager vibratorManager = (VibratorManager) getSystemService(VIBRATOR_MANAGER_SERVICE);
            vibrator = vibratorManager == null ? null : vibratorManager.getDefaultVibrator();
        } else {
            vibrator = (Vibrator) getSystemService(VIBRATOR_SERVICE);
        }
        if (vibrator == null || !vibrator.hasVibrator()) {
            return;
        }
        StrengthConfig config = strengthConfig();
        long[] pattern = config.pattern;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            AudioAttributes attributes = new AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_ALARM)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                    .build();
            if (vibrator.hasAmplitudeControl()) {
                int[] amplitudes = config.amplitudes;
                vibrator.vibrate(VibrationEffect.createWaveform(pattern, amplitudes, 0), attributes);
                return;
            }
            vibrator.vibrate(VibrationEffect.createWaveform(pattern, 0), attributes);
            return;
        }
        vibrator.vibrate(pattern, 0);
    }

    private void scheduleAutoStop() {
        handler.removeCallbacks(autoStopRunnable);
        handler.postDelayed(autoStopRunnable, MAX_ALARM_MS);
    }

    private boolean isDuplicateActiveAlarm(String alarmKey) {
        SharedPreferences preferences = getSharedPreferences(PREFS, MODE_PRIVATE);
        boolean active = preferences.getBoolean(KEY_ACTIVE, false);
        String previousKey = preferences.getString(KEY_LAST_ALARM_KEY, "");
        long previousAt = preferences.getLong(KEY_LAST_STARTED_AT, 0L);
        long now = System.currentTimeMillis();
        String key = alarmKey == null ? "" : alarmKey;
        return active
                && !key.isEmpty()
                && key.equals(previousKey)
                && now - previousAt >= 0L
                && now - previousAt < DUPLICATE_ALARM_MS;
    }

    private void markActive(String alarmKey) {
        getSharedPreferences(PREFS, MODE_PRIVATE).edit()
                .putBoolean(KEY_ACTIVE, true)
                .putString(KEY_LAST_ALARM_KEY, alarmKey == null ? "" : alarmKey)
                .putLong(KEY_LAST_STARTED_AT, System.currentTimeMillis())
                .apply();
    }

    private static void markInactive(Context context) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
                .putBoolean(KEY_ACTIVE, false)
                .apply();
    }

    private void saveStrength(String raw) {
        String value = normalizeStrength(raw);
        getSharedPreferences(PREFS, MODE_PRIVATE).edit().putString(KEY_STRENGTH, value).apply();
    }

    private StrengthConfig strengthConfig() {
        String value = normalizeStrength(
                getSharedPreferences(PREFS, MODE_PRIVATE).getString(KEY_STRENGTH, STRENGTH_PULSE)
        );
        if (STRENGTH_WEAK.equals(value)) {
            return new StrengthConfig(
                    new long[]{0, 180, 260, 180, 360, 240, 650},
                    new int[]{0, 120, 0, 120, 0, 140, 0, 150}
            );
        }
        if (STRENGTH_MEDIUM.equals(value)) {
            return new StrengthConfig(
                    new long[]{0, 260, 180, 260, 180, 450, 220, 650, 300},
                    new int[]{0, 200, 0, 200, 0, 220, 0, 230, 0}
            );
        }
        if (STRENGTH_ZIG.equals(value)) {
            return new StrengthConfig(
                    new long[]{0, 180, 90, 180, 90, 180, 520},
                    new int[]{0, 255, 0, 255, 0, 255, 0}
            );
        }
        if (STRENGTH_PULSE.equals(value)) {
            return new StrengthConfig(
                    new long[]{0, 100, 50, 100, 50, 100, 50, 100, 50, 100, 50},
                    new int[]{0, 255, 0, 255, 0, 255, 0, 255, 0, 255, 0}
            );
        }
        return new StrengthConfig(
                new long[]{0, 350, 120, 350, 120, 550, 160, 350, 120, 800, 350},
                new int[]{0, 255, 0, 255, 0, 255, 0, 255, 0, 255, 0}
        );
    }

    private String normalizeStrength(String raw) {
        String value = raw == null ? "" : raw.trim().toLowerCase();
        if (STRENGTH_WEAK.equals(value)
                || STRENGTH_MEDIUM.equals(value)
                || STRENGTH_ZIG.equals(value)
                || STRENGTH_PULSE.equals(value)) {
            return value;
        }
        return STRENGTH_STRONG;
    }

    private static final class StrengthConfig {
        final long[] pattern;
        final int[] amplitudes;

        StrengthConfig(long[] pattern, int[] amplitudes) {
            this.pattern = pattern;
            this.amplitudes = amplitudes;
        }
    }

    private void stopAlert() {
        handler.removeCallbacks(autoStopRunnable);
        if (vibrator != null) {
            vibrator.cancel();
        }
        vibrator = null;
    }
}
