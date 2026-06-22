package com.example.oneshotalarm;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.os.IBinder;
import android.os.PowerManager;
import android.os.VibrationEffect;
import android.os.Vibrator;
import android.media.AudioAttributes;

public class AlarmAlertService extends Service {
    static final String ACTION_START = "com.example.oneshotalarm.ACTION_ALERT_START";
    static final String ACTION_STOP = "com.example.oneshotalarm.ACTION_ALERT_STOP";
    static final String CHANNEL_ID = "alarm_channel_v2";
    static final int NOTIFICATION_ID = 8801;

    private PowerManager.WakeLock wakeLock;
    private Vibrator vibrator;
    private boolean stopping = false;

    static void start(Context context, String id, String label, long triggerAtMillis) {
        Intent intent = new Intent(context, AlarmAlertService.class);
        intent.setAction(ACTION_START);
        intent.putExtra(AlarmScheduler.EXTRA_ALARM_ID, id);
        intent.putExtra(AlarmScheduler.EXTRA_ALARM_LABEL, label);
        intent.putExtra(AlarmScheduler.EXTRA_ALARM_TRIGGER_AT, triggerAtMillis);
        context.startService(intent);
    }

    static void stop(Context context) {
        Intent intent = new Intent(context, AlarmAlertService.class);
        intent.setAction(ACTION_STOP);
        context.startService(intent);
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && ACTION_STOP.equals(intent.getAction())) {
            if (stopping) {
                return START_NOT_STICKY;
            }
            stopping = true;
            stopAlert();
            stopSelf();
            return START_NOT_STICKY;
        }

        String id = intent == null ? "" : intent.getStringExtra(AlarmScheduler.EXTRA_ALARM_ID);
        String label = intent == null ? "鬧鐘" : intent.getStringExtra(AlarmScheduler.EXTRA_ALARM_LABEL);
        long triggerAtMillis = intent == null ? 0L : intent.getLongExtra(AlarmScheduler.EXTRA_ALARM_TRIGGER_AT, 0L);
        if (label == null || label.trim().isEmpty()) {
            label = "鬧鐘響喇";
        }

        acquireWakeLock();
        startStrongVibration();
        AlarmScheduler.sendAlarmActivity(this, id, label, triggerAtMillis);
        return START_STICKY;
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    @Override
    public void onDestroy() {
        stopAlert();
        super.onDestroy();
    }

    private Notification buildNotification(String id, String label, long triggerAtMillis) {
        createChannel();

        Notification.Builder builder = Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
                ? new Notification.Builder(this, CHANNEL_ID)
                : new Notification.Builder(this);

        builder.setSmallIcon(android.R.drawable.ic_lock_idle_alarm)
                .setContentTitle(formatAlarmMessage(label, triggerAtMillis))
                .setContentText("撳入去停止")
                .setPriority(Notification.PRIORITY_MAX)
                .setCategory(Notification.CATEGORY_ALARM)
                .setVisibility(Notification.VISIBILITY_PUBLIC)
                .setOngoing(true)
                .setAutoCancel(false)
                .setSound(null)
                .setDefaults(Notification.DEFAULT_LIGHTS)
                .setVibrate(new long[] {0, 650, 90, 650, 90, 900, 120, 1200})
                .setContentIntent(
                        AlarmScheduler.activityPendingIntent(this, id, label, triggerAtMillis, android.app.PendingIntent.FLAG_UPDATE_CURRENT)
                );
        return builder.build();
    }

    private String formatAlarmMessage(String label, long triggerAtMillis) {
        long millis = triggerAtMillis > 0L ? triggerAtMillis : System.currentTimeMillis();
        String time = new java.text.SimpleDateFormat("HH:mm", java.util.Locale.getDefault()).format(millis);
        String text = label == null ? "" : label.trim();
        if (text.isEmpty()) {
            text = "鬧鐘";
        }
        return time + " " + text;
    }

    private void createChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
            return;
        }
        NotificationChannel channel = new NotificationChannel(
                CHANNEL_ID,
                "Alarm alerts",
                NotificationManager.IMPORTANCE_HIGH
        );
        channel.setDescription("One shot alarm alerts");
        channel.setLockscreenVisibility(Notification.VISIBILITY_PUBLIC);
        channel.enableVibration(true);
        channel.setVibrationPattern(new long[] {0, 650, 90, 650, 90, 900, 120, 1200});
        channel.setBypassDnd(true);
        channel.setSound(null, null);

        NotificationManager notificationManager =
                (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        notificationManager.createNotificationChannel(channel);
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
                "oneshotalarm:alarm"
        );
        wakeLock.acquire(2 * 60 * 1000L);
    }

    private void startStrongVibration() {
        if (vibrator == null) {
            vibrator = (Vibrator) getSystemService(VIBRATOR_SERVICE);
        }
        if (vibrator == null || !vibrator.hasVibrator()) {
            return;
        }

        long[] pattern = {0, 650, 90, 650, 90, 900, 120, 1200, 160, 1500};

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            if (vibrator.hasAmplitudeControl()) {
                int[] amplitudes = {0, 255, 0, 255, 0, 255, 0, 255, 0, 255};
                vibrator.vibrate(
                        VibrationEffect.createWaveform(pattern, amplitudes, 0),
                        new AudioAttributes.Builder()
                                .setUsage(AudioAttributes.USAGE_ALARM)
                                .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                                .build()
                );
                return;
            }
            vibrator.vibrate(
                    VibrationEffect.createWaveform(pattern, 0),
                    new AudioAttributes.Builder()
                            .setUsage(AudioAttributes.USAGE_ALARM)
                            .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                            .build()
            );
            return;
        }

        vibrator.vibrate(pattern, 0);
    }

    private void stopVibration() {
        if (vibrator != null) {
            vibrator.cancel();
        }
        vibrator = null;
    }

    private void stopAlert() {
        stopVibration();
        if (wakeLock != null && wakeLock.isHeld()) {
            wakeLock.release();
        }
        wakeLock = null;

        NotificationManager notificationManager =
                (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        notificationManager.cancel(NOTIFICATION_ID);
    }
}
