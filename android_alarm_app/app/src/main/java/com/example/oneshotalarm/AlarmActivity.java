package com.example.oneshotalarm;

import android.app.Activity;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.media.AudioAttributes;
import android.os.Build;
import android.os.Bundle;
import android.os.PowerManager;
import android.os.VibrationEffect;
import android.os.Vibrator;
import android.view.Gravity;
import android.view.Window;
import android.view.WindowManager;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.text.SimpleDateFormat;
import java.util.Locale;

public class AlarmActivity extends Activity {
    static final String ACTION_WATCH_DISMISS = "com.example.oneshotalarm.ACTION_WATCH_DISMISS";
    private static final String PREFS = "alarm_activity";
    private static final String KEY_WATCH_DISMISS_AT = "watch_dismiss_at";
    private static final long WATCH_DISMISS_VALID_MS = 30 * 1000L;
    private boolean stopped = false;
    private PowerManager.WakeLock wakeLock;
    private Vibrator vibrator;
    private final BroadcastReceiver watchDismissReceiver = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            if (intent != null && ACTION_WATCH_DISMISS.equals(intent.getAction())) {
                dismissAlarm();
            }
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        turnScreenOn();
        acquireWakeLock();
        startStrongVibration();
        buildUi();
        registerWatchDismissReceiver();
        if (hasRecentWatchDismiss()) {
            dismissAlarm();
        }
    }

    @Override
    protected void onDestroy() {
        try {
            unregisterReceiver(watchDismissReceiver);
        } catch (Exception ignored) {
        }
        stopAlert();
        super.onDestroy();
    }

    private void turnScreenOn() {
        Window window = getWindow();
        window.addFlags(
                WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED
                        | WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON
                        | WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON
                        | WindowManager.LayoutParams.FLAG_DISMISS_KEYGUARD
        );

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O_MR1) {
            setShowWhenLocked(true);
            setTurnScreenOn(true);
        }
    }

    private void buildUi() {
        String label = getIntent().getStringExtra(AlarmScheduler.EXTRA_ALARM_LABEL);
        if (label == null || label.trim().isEmpty()) {
            label = "鬧鐘";
        }
        long triggerAtMillis = getIntent().getLongExtra(AlarmScheduler.EXTRA_ALARM_TRIGGER_AT, 0L);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setGravity(Gravity.CENTER);
        root.setPadding(dp(22), dp(22), dp(22), dp(22));
        root.setBackgroundColor(0xFF000000);
        root.setClickable(true);
        root.setOnClickListener(v -> dismissAlarm());

        TextView timeView = new TextView(this);
        timeView.setText(formatAlarmTime(triggerAtMillis));
        timeView.setTextColor(0xFFFFFFFF);
        timeView.setTextSize(76);
        timeView.setGravity(Gravity.CENTER);
        timeView.setIncludeFontPadding(false);
        root.addView(timeView, weightedHeight(1f));

        TextView labelView = new TextView(this);
        labelView.setText(label);
        labelView.setTextColor(0xFFFFFFFF);
        labelView.setTextSize(44);
        labelView.setGravity(Gravity.CENTER);
        labelView.setSingleLine(false);
        labelView.setPadding(dp(10), dp(10), dp(10), dp(10));
        root.addView(labelView, weightedHeight(2f));

        setContentView(root);
    }

    private void dismissAlarm() {
        if (stopped) {
            return;
        }
        stopped = true;
        WatchBridge.sendDismiss(this);
        WatchBridge.sendTileState(this);
        stopAlert();
        finish();
    }

    private void registerWatchDismissReceiver() {
        IntentFilter filter = new IntentFilter(ACTION_WATCH_DISMISS);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            registerReceiver(watchDismissReceiver, filter, Context.RECEIVER_NOT_EXPORTED);
        } else {
            registerReceiver(watchDismissReceiver, filter);
        }
    }

    static void markWatchDismiss(Context context) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
                .putLong(KEY_WATCH_DISMISS_AT, System.currentTimeMillis())
                .apply();
    }

    private boolean hasRecentWatchDismiss() {
        long at = getSharedPreferences(PREFS, MODE_PRIVATE).getLong(KEY_WATCH_DISMISS_AT, 0L);
        long now = System.currentTimeMillis();
        return at > 0L && now - at >= 0L && now - at < WATCH_DISMISS_VALID_MS;
    }

    private LinearLayout.LayoutParams weightedHeight(float weight) {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                0,
                weight
        );
        return params;
    }

    private String formatAlarmTime(long triggerAtMillis) {
        long millis = triggerAtMillis > 0L ? triggerAtMillis : System.currentTimeMillis();
        return new SimpleDateFormat("HH:mm", Locale.getDefault()).format(millis);
    }

    private void acquireWakeLock() {
        if (wakeLock != null && wakeLock.isHeld()) {
            return;
        }
        PowerManager powerManager = (PowerManager) getSystemService(POWER_SERVICE);
        if (powerManager == null) {
            return;
        }
        wakeLock = powerManager.newWakeLock(
                PowerManager.SCREEN_BRIGHT_WAKE_LOCK
                        | PowerManager.ACQUIRE_CAUSES_WAKEUP
                        | PowerManager.ON_AFTER_RELEASE,
                "oneshotalarm:alarm-activity"
        );
        wakeLock.acquire();
    }

    private void startStrongVibration() {
        if (vibrator == null) {
            vibrator = (Vibrator) getSystemService(VIBRATOR_SERVICE);
        }
        if (vibrator == null || !vibrator.hasVibrator()) {
            return;
        }

        long[] pattern = {
                0,
                1200, 80,
                1200, 80,
                1500, 100,
                1500, 100,
                1800, 120,
                2200, 160
        };

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            AudioAttributes attributes = new AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_ALARM)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                    .build();
            if (vibrator.hasAmplitudeControl()) {
                int[] amplitudes = {
                        0,
                        255, 0,
                        255, 0,
                        255, 0,
                        255, 0,
                        255, 0,
                        255, 0
                };
                vibrator.vibrate(VibrationEffect.createWaveform(pattern, amplitudes, 0), attributes);
                return;
            }
            vibrator.vibrate(VibrationEffect.createWaveform(pattern, 0), attributes);
            return;
        }

        vibrator.vibrate(pattern, 0);
    }

    private void stopAlert() {
        if (vibrator != null) {
            vibrator.cancel();
        }
        vibrator = null;
        if (wakeLock != null && wakeLock.isHeld()) {
            wakeLock.release();
        }
        wakeLock = null;
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }
}
