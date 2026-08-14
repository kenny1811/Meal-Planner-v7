package com.example.oneshotalarm.watch;

import android.app.Service;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.graphics.PixelFormat;
import android.media.AudioAttributes;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.PowerManager;
import android.os.VibrationEffect;
import android.os.Vibrator;
import android.os.VibratorManager;
import android.provider.Settings;
import android.util.Log;
import android.view.Gravity;
import android.view.View;
import android.view.WindowManager;
import android.widget.LinearLayout;
import android.widget.TextView;

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
    private static final String CHANNEL_ID = "watch_alarm";
    private static final int NOTIFICATION_ID = 4101;
    private static final long DUPLICATE_ALARM_MS = 2 * 60 * 1000L;
    private static final String TAG = "ShiftAlarmWatch";

    private Vibrator vibrator;
    private PowerManager.WakeLock alarmWakeLock;
    private View overlayView;
    private final Handler screenOffHandler = new Handler(Looper.getMainLooper());
    private BroadcastReceiver screenOffReceiver;

    static void start(Context context, String alarmKey) {
        Intent intent = new Intent(context, WatchAlarmService.class);
        intent.setAction(ACTION_START);
        intent.putExtra(EXTRA_ALARM_KEY, alarmKey == null ? "" : alarmKey);
        context.startService(intent);
    }

    static void stop(Context context) {
        Intent intent = new Intent(context, WatchAlarmService.class);
        markInactive(context);
        clearNotification(context);
        context.stopService(intent);
    }

    static String activeAlarmId(Context context) {
        SharedPreferences preferences = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        if (!preferences.getBoolean(KEY_ACTIVE, false)) {
            return null;
        }
        String key = preferences.getString(KEY_LAST_ALARM_KEY, "");
        int newline = key.indexOf('\n');
        return (newline >= 0 ? key.substring(0, newline) : key).trim();
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
            Log.d(TAG, "Duplicate active watch alarm ignored by service");
            return START_NOT_STICKY;
        }
        Log.d(TAG, "Watch alarm service start: " + alarmKey.replace('\n', ' '));
        acquireAlarmWakeLock();
        showAlarmNotification(alarmKey);
        showAlarmOverlay(alarmKey);
        markActive(alarmKey);
        startVibration();
        registerScreenOffReceiver();
        return START_NOT_STICKY;
    }

    @Override
    public void onDestroy() {
        markInactive(this);
        stopAlarmHardware();
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
            Log.d(TAG, "Watch vibrator unavailable");
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
                Log.d(TAG, "Watch vibration started with amplitude control");
                return;
            }
            vibrator.vibrate(VibrationEffect.createWaveform(pattern, 0), attributes);
            Log.d(TAG, "Watch vibration started");
            return;
        }
        vibrator.vibrate(pattern, 0);
        Log.d(TAG, "Watch vibration started legacy");
    }

    /**
     * 垂手黑屏嗰下，系統會 cancel 咗響緊嘅震動（熄屏前開始嘅震動先會中招；
     * 熄屏之後先開始嘅唔會）——所以聽到 SCREEN_OFF 就等半秒重新開震。
     */
    private void registerScreenOffReceiver() {
        if (screenOffReceiver != null) {
            return;
        }
        screenOffReceiver = new BroadcastReceiver() {
            @Override
            public void onReceive(Context context, Intent intent) {
                Log.d(TAG, "Screen off during alarm, re-vibrating in 500ms");
                screenOffHandler.postDelayed(() -> {
                    if (screenOffReceiver != null) {
                        startVibration();
                        Log.d(TAG, "Watch vibration restarted after screen off");
                    }
                }, 500);
            }
        };
        IntentFilter filter = new IntentFilter(Intent.ACTION_SCREEN_OFF);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            registerReceiver(screenOffReceiver, filter, Context.RECEIVER_NOT_EXPORTED);
        } else {
            registerReceiver(screenOffReceiver, filter);
        }
    }

    private void unregisterScreenOffReceiver() {
        screenOffHandler.removeCallbacksAndMessages(null);
        if (screenOffReceiver == null) {
            return;
        }
        try {
            unregisterReceiver(screenOffReceiver);
        } catch (IllegalArgumentException ignored) {
        }
        screenOffReceiver = null;
    }

    private void showAlarmOverlay(String alarmKey) {
        if (overlayView != null) {
            return;
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M && !Settings.canDrawOverlays(this)) {
            Log.e(TAG, "Watch alarm overlay unavailable: SYSTEM_ALERT_WINDOW not allowed");
            return;
        }
        AlarmParts parts = AlarmParts.from(alarmKey);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setGravity(Gravity.CENTER);
        root.setPadding(dp(10), dp(8), dp(10), dp(8));
        root.setBackgroundColor(0xFF000000);
        root.setClickable(true);
        root.setOnClickListener(v -> dismissFromOverlay(parts.id));

        // 唔好用 weight 斬開上下兩格（會變成「時間貼頂、標籤吊中下」）——
        // 兩行字 wrap content 做一嚿，由 root 嘅 gravity 揸住成嚿喺圓芒正中央。
        TextView timeView = new TextView(this);
        timeView.setText(parts.time);
        timeView.setTextColor(0xFFFFFFFF);
        timeView.setTextSize(42);
        timeView.setGravity(Gravity.CENTER);
        timeView.setIncludeFontPadding(false);
        root.addView(timeView, wrapHeight());

        TextView labelView = new TextView(this);
        labelView.setText(parts.label);
        labelView.setTextColor(0xFFFFFFFF);
        labelView.setTextSize(24);
        labelView.setGravity(Gravity.CENTER);
        labelView.setSingleLine(false);
        labelView.setPadding(dp(8), dp(6), dp(8), dp(6));
        root.addView(labelView, wrapHeight());

        WindowManager.LayoutParams params = new WindowManager.LayoutParams(
                WindowManager.LayoutParams.MATCH_PARENT,
                WindowManager.LayoutParams.MATCH_PARENT,
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON
                        | WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED
                        | WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON
                        | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
                PixelFormat.OPAQUE
        );
        params.gravity = Gravity.CENTER;
        try {
            WindowManager manager = (WindowManager) getSystemService(WINDOW_SERVICE);
            if (manager == null) {
                Log.e(TAG, "Watch alarm overlay unavailable: WindowManager missing");
                return;
            }
            manager.addView(root, params);
            overlayView = root;
            Log.d(TAG, "Watch alarm overlay shown");
        } catch (Exception e) {
            Log.e(TAG, "Watch alarm overlay failed", e);
        }
    }

    private void dismissFromOverlay(String alarmId) {
        WatchDismissBridge.sendDismiss(this, alarmId);
        Intent dismissIntent = new Intent(WatchAlarmActivity.ACTION_DISMISS_LOCAL);
        dismissIntent.setPackage(getPackageName());
        sendBroadcast(dismissIntent);
        WatchScheduleDisplayState.refreshFromCacheAndRequest(this);
        stopAlert();
        stopSelf();
    }

    private void showAlarmNotification(String alarmKey) {
        NotificationManager manager = getSystemService(NotificationManager.class);
        if (manager == null) {
            Log.d(TAG, "Notification manager unavailable");
            return;
        }
        manager.notify(NOTIFICATION_ID, buildAlarmNotification(alarmKey));
        Log.d(TAG, "Watch alarm notification shown");
    }

    private Notification buildAlarmNotification(String alarmKey) {
        ensureNotificationChannel();
        AlarmParts parts = AlarmParts.from(alarmKey);
        PendingIntent contentIntent = PendingIntent.getActivity(
                this,
                4102,
                alarmActivityIntent(parts),
                pendingIntentFlags(PendingIntent.FLAG_CANCEL_CURRENT)
        );
        PendingIntent stopIntent = PendingIntent.getBroadcast(
                this,
                4103,
                new Intent(this, WatchLocalAlarmReceiver.class)
                        .setAction(WatchLocalAlarmReceiver.ACTION_STOP_FROM_NOTIFICATION)
                        .putExtra(WatchAlarmActivity.EXTRA_ALARM_ID, parts.id),
                pendingIntentFlags(PendingIntent.FLAG_UPDATE_CURRENT)
        );
        Notification.Builder builder = Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
                ? new Notification.Builder(this, CHANNEL_ID)
                : new Notification.Builder(this);
        builder.setSmallIcon(android.R.drawable.ic_lock_idle_alarm)
                .setContentTitle(parts.time)
                .setContentText(parts.label)
                .setCategory(Notification.CATEGORY_ALARM)
                .setOngoing(true)
                .setAutoCancel(false)
                .setContentIntent(contentIntent)
                .addAction(android.R.drawable.ic_menu_close_clear_cancel, "停止", stopIntent);
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
            builder.setPriority(Notification.PRIORITY_MAX);
        }
        return builder.build();
    }

    private Intent alarmActivityIntent(AlarmParts parts) {
        Intent intent = new Intent(this, WatchAlarmActivity.class);
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        intent.putExtra(WatchAlarmActivity.EXTRA_ALARM_ID, parts.id);
        intent.putExtra(WatchAlarmActivity.EXTRA_TIME, parts.time);
        intent.putExtra(WatchAlarmActivity.EXTRA_LABEL, parts.label);
        return intent;
    }

    private void ensureNotificationChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
            return;
        }
        NotificationManager manager = getSystemService(NotificationManager.class);
        if (manager == null || manager.getNotificationChannel(CHANNEL_ID) != null) {
            return;
        }
        NotificationChannel channel = new NotificationChannel(
                CHANNEL_ID,
                "Watch alarm",
                NotificationManager.IMPORTANCE_HIGH
        );
        channel.setDescription("Local watch alarm");
        channel.setLockscreenVisibility(Notification.VISIBILITY_PUBLIC);
        channel.setSound(null, null);
        channel.enableVibration(false);
        channel.setLightColor(Color.BLUE);
        manager.createNotificationChannel(channel);
    }

    private void acquireAlarmWakeLock() {
        releaseAlarmWakeLock();
        PowerManager powerManager = (PowerManager) getSystemService(POWER_SERVICE);
        if (powerManager == null) {
            return;
        }
        alarmWakeLock = powerManager.newWakeLock(
                PowerManager.PARTIAL_WAKE_LOCK,
                TAG + ":alarm"
        );
        alarmWakeLock.setReferenceCounted(false);
        alarmWakeLock.acquire();
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
        stopAlarmHardware();
        clearNotification(this);
    }

    private void stopAlarmHardware() {
        unregisterScreenOffReceiver();
        removeAlarmOverlay();
        if (vibrator != null) {
            vibrator.cancel();
        }
        vibrator = null;
        releaseAlarmWakeLock();
    }

    private void removeAlarmOverlay() {
        if (overlayView == null) {
            return;
        }
        try {
            WindowManager manager = (WindowManager) getSystemService(WINDOW_SERVICE);
            if (manager != null) {
                manager.removeView(overlayView);
            }
        } catch (Exception ignored) {
        }
        overlayView = null;
    }

    private static void clearNotification(Context context) {
        NotificationManager manager = context.getSystemService(NotificationManager.class);
        if (manager != null) {
            manager.cancel(NOTIFICATION_ID);
        }
    }

    private void releaseAlarmWakeLock() {
        if (alarmWakeLock != null && alarmWakeLock.isHeld()) {
            alarmWakeLock.release();
        }
        alarmWakeLock = null;
    }

    private static int pendingIntentFlags(int flags) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            return flags | PendingIntent.FLAG_IMMUTABLE;
        }
        return flags;
    }

    private LinearLayout.LayoutParams wrapHeight() {
        return new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
        );
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    private static final class AlarmParts {
        final String id;
        final String time;
        final String label;

        AlarmParts(String id, String time, String label) {
            this.id = id == null ? "" : id;
            this.time = time == null || time.trim().isEmpty() ? "--:--" : time;
            this.label = label == null || label.trim().isEmpty() ? "鬧鐘" : label;
        }

        static AlarmParts from(String alarmKey) {
            String[] parts = (alarmKey == null ? "" : alarmKey).split("\\n", 3);
            if (parts.length >= 3) {
                return new AlarmParts(parts[0], parts[1], parts[2]);
            }
            if (parts.length == 2) {
                return new AlarmParts("", parts[0], parts[1]);
            }
            return new AlarmParts("", "--:--", "鬧鐘");
        }
    }
}
