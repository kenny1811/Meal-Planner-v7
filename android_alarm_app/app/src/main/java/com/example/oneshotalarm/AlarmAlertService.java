package com.example.oneshotalarm;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.hardware.Sensor;
import android.hardware.SensorEvent;
import android.hardware.SensorEventListener;
import android.hardware.SensorManager;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.PowerManager;
import android.os.VibrationEffect;
import android.os.Vibrator;
import android.media.AudioAttributes;

public class AlarmAlertService extends Service {
    static final String ACTION_START = "com.example.oneshotalarm.ACTION_ALERT_START";
    static final String ACTION_STOP = "com.example.oneshotalarm.ACTION_ALERT_STOP";
    static final String CHANNEL_ID = "alarm_channel_v2";
    static final int NOTIFICATION_ID = 8801;

    private static final float LAUNCH_LUX_THRESHOLD = 10f;

    private PowerManager.WakeLock wakeLock;
    private Vibrator vibrator;
    private boolean stopping = false;
    private SensorManager sensorManager;
    private SensorEventListener lightListener;
    private BroadcastReceiver pocketReceiver;
    private boolean activityLaunched = false;
    private boolean gotLightSample = false;
    private boolean darkLogged = false;
    private String pendingId = "";
    private String pendingLabel = "";
    private long pendingTriggerAt = 0L;
    private final Handler handler = new Handler(Looper.getMainLooper());

    static void start(Context context, String id, String label, long triggerAtMillis) {
        Intent intent = new Intent(context, AlarmAlertService.class);
        intent.setAction(ACTION_START);
        intent.putExtra(AlarmScheduler.EXTRA_ALARM_ID, id);
        intent.putExtra(AlarmScheduler.EXTRA_ALARM_LABEL, label);
        intent.putExtra(AlarmScheduler.EXTRA_ALARM_TRIGGER_AT, triggerAtMillis);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            context.startForegroundService(intent);
        } else {
            context.startService(intent);
        }
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
            DiagLog.log(this, "AlarmAlertService stop");
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

        stopping = false;
        startForeground(NOTIFICATION_ID, buildNotification(id, label, triggerAtMillis));
        acquireWakeLock();
        startStrongVibration();
        startPocketGuard(id, label, triggerAtMillis);
        return START_STICKY;
    }

    /**
     * 褲袋防誤觸（Kenny 11/08 拍板）：黑暗（袋入面）唔開鬧鐘畫面、唔亮屏——
     * 螢幕唔著就冇得誤觸，震照震；見光（攞咗出嚟）先開 AlarmActivity（原裝
     * turn-screen-on + show-when-locked 全套，浮喺鎖屏上面，撳一下即 dismiss）。
     * 用戶自己撳 power 開芒都當攞咗出嚟。冇 sensor／一秒內冇讀數 → 照舊即開（保底）。
     * 因為黑暗期冇 activity 幫手轉發，service 要自己聽埋手錶 dismiss。
     */
    private void startPocketGuard(String id, String label, long triggerAtMillis) {
        pendingId = id == null ? "" : id.trim();
        pendingLabel = label;
        pendingTriggerAt = triggerAtMillis;
        activityLaunched = false;
        gotLightSample = false;
        darkLogged = false;
        registerPocketReceiver();
        sensorManager = (SensorManager) getSystemService(SENSOR_SERVICE);
        Sensor light = sensorManager == null ? null : sensorManager.getDefaultSensor(Sensor.TYPE_LIGHT);
        if (light == null) {
            launchAlarmActivity("no-light-sensor");
            return;
        }
        lightListener = new SensorEventListener() {
            @Override
            public void onSensorChanged(SensorEvent event) {
                gotLightSample = true;
                float lux = event.values[0];
                if (lux >= LAUNCH_LUX_THRESHOLD) {
                    launchAlarmActivity("lux=" + lux);
                } else if (!darkLogged) {
                    darkLogged = true;
                    DiagLog.log(AlarmAlertService.this,
                            "pocket-guard dark lux=" + lux + " holding alarm screen");
                }
            }

            @Override
            public void onAccuracyChanged(Sensor sensor, int accuracy) {
            }
        };
        sensorManager.registerListener(lightListener, light, SensorManager.SENSOR_DELAY_UI);
        handler.postDelayed(() -> {
            if (!activityLaunched && !gotLightSample) {
                launchAlarmActivity("no-lux-sample");
            }
        }, 1000);
    }

    private void launchAlarmActivity(String reason) {
        if (activityLaunched || stopping) {
            return;
        }
        activityLaunched = true;
        stopLightSensor();
        DiagLog.log(this, "pocket-guard launch reason=" + reason);
        AlarmScheduler.sendAlarmActivity(this, pendingId, pendingLabel, pendingTriggerAt);
    }

    private void registerPocketReceiver() {
        if (pocketReceiver != null) {
            return;
        }
        pocketReceiver = new BroadcastReceiver() {
            @Override
            public void onReceive(Context context, Intent intent) {
                String action = intent == null ? "" : intent.getAction();
                if (Intent.ACTION_SCREEN_ON.equals(action)) {
                    launchAlarmActivity("screen-on");
                    return;
                }
                if (AlarmActivity.ACTION_WATCH_DISMISS.equals(action)
                        && shouldStopForWatchDismiss(
                                intent.getStringExtra(AlarmActivity.EXTRA_DISMISS_ALARM_ID),
                                intent.getLongExtra(AlarmActivity.EXTRA_DISMISS_TS, 0L))) {
                    DiagLog.log(AlarmAlertService.this, "watch dismiss stops service id=" + pendingId);
                    stopping = true;
                    stopAlert();
                    stopSelf();
                }
            }
        };
        IntentFilter filter = new IntentFilter(Intent.ACTION_SCREEN_ON);
        filter.addAction(AlarmActivity.ACTION_WATCH_DISMISS);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            registerReceiver(pocketReceiver, filter, Context.RECEIVER_NOT_EXPORTED);
        } else {
            registerReceiver(pocketReceiver, filter);
        }
    }

    private boolean shouldStopForWatchDismiss(String dismissAlarmId, long sentAtMillis) {
        String id = dismissAlarmId == null ? "" : dismissAlarmId.trim();
        if (!id.isEmpty() && !pendingId.isEmpty()) {
            return id.equals(pendingId);
        }
        long now = System.currentTimeMillis();
        return sentAtMillis > 0L && Math.abs(now - sentAtMillis) < 30 * 1000L;
    }

    private void stopLightSensor() {
        if (sensorManager != null && lightListener != null) {
            sensorManager.unregisterListener(lightListener);
        }
        lightListener = null;
        handler.removeCallbacksAndMessages(null);
    }

    private void stopPocketGuard() {
        stopLightSensor();
        if (pocketReceiver != null) {
            try {
                unregisterReceiver(pocketReceiver);
            } catch (IllegalArgumentException ignored) {
            }
            pocketReceiver = null;
        }
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
        String time = Clock30.format(millis);
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
        // 褲袋防誤觸：service 唔好搶住亮屏，亮唔亮屏由 AlarmActivity 按光線判斷；
        // 呢度齋揸 CPU 保住震動。
        wakeLock = powerManager.newWakeLock(
                PowerManager.PARTIAL_WAKE_LOCK,
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
        stopPocketGuard();
        stopVibration();
        if (wakeLock != null && wakeLock.isHeld()) {
            wakeLock.release();
        }
        wakeLock = null;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
            stopForeground(STOP_FOREGROUND_REMOVE);
        } else {
            stopForeground(true);
        }

        NotificationManager notificationManager =
                (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        notificationManager.cancel(NOTIFICATION_ID);
    }
}
