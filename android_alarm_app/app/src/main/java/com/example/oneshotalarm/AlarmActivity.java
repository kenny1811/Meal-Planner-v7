package com.example.oneshotalarm;

import android.app.Activity;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.os.Build;
import android.os.Bundle;
import android.os.PowerManager;
import android.view.Gravity;
import android.view.Window;
import android.view.WindowManager;
import android.widget.LinearLayout;
import android.widget.TextView;

public class AlarmActivity extends Activity {
    static final String ACTION_WATCH_DISMISS = "com.example.oneshotalarm.ACTION_WATCH_DISMISS";
    static final String EXTRA_DISMISS_ALARM_ID = "dismiss_alarm_id";
    static final String EXTRA_DISMISS_TS = "dismiss_ts";
    private static final String PREFS = "alarm_activity";
    private static final String KEY_WATCH_DISMISS_AT = "watch_dismiss_at";
    private static final String KEY_WATCH_DISMISS_ID = "watch_dismiss_id";
    private static final long WATCH_DISMISS_VALID_MS = 30 * 1000L;
    private boolean stopped = false;
    private PowerManager.WakeLock wakeLock;
    private final BroadcastReceiver watchDismissReceiver = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            if (intent != null
                    && ACTION_WATCH_DISMISS.equals(intent.getAction())
                    && shouldDismissFor(
                            intent.getStringExtra(EXTRA_DISMISS_ALARM_ID),
                            intent.getLongExtra(EXTRA_DISMISS_TS, 0L))) {
                dismissAlarm("watch-dismiss-broadcast id="
                        + intent.getStringExtra(EXTRA_DISMISS_ALARM_ID));
            }
        }
    };

    /**
     * 診斷用：記低每一下真實觸控（accessibility 合成 click 唔會經過呢度——
     * 有 dismiss 而冇 touch 記錄，就證明唔係掂螢幕）。唔影響事件處理。
     */
    @Override
    public boolean dispatchTouchEvent(android.view.MotionEvent ev) {
        int action = ev.getActionMasked();
        if (action == android.view.MotionEvent.ACTION_DOWN
                || action == android.view.MotionEvent.ACTION_UP) {
            DiagLog.log(this, "touch " + (action == android.view.MotionEvent.ACTION_DOWN ? "down" : "up")
                    + " x=" + (int) ev.getX() + " y=" + (int) ev.getY());
        }
        return super.dispatchTouchEvent(ev);
    }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        turnScreenOn();
        acquireWakeLock();
        buildUi();
        registerWatchDismissReceiver();
        DiagLog.log(this, "AlarmActivity onCreate id=" + myAlarmId());
        if (hasRecentWatchDismiss()) {
            dismissAlarm("recent-watch-dismiss-at-create");
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
        root.setOnClickListener(v -> dismissAlarm("screen-click"));

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

    private void dismissAlarm(String reason) {
        if (stopped) {
            return;
        }
        stopped = true;
        DiagLog.log(this, "dismissAlarm reason=" + reason + " id=" + myAlarmId());
        // 淨係送 dismiss；行位表冇改就唔好推嘢上錶。
        WatchBridge.sendDismiss(this, getIntent().getStringExtra(AlarmScheduler.EXTRA_ALARM_ID));
        AlarmAlertService.stop(this);
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

    static void markWatchDismiss(Context context, String alarmId) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
                .putLong(KEY_WATCH_DISMISS_AT, System.currentTimeMillis())
                .putString(KEY_WATCH_DISMISS_ID, alarmId == null ? "" : alarmId.trim())
                .apply();
    }

    /**
     * 手錶嗰下 dismiss 係咪熄緊我呢隻鬧鐘。
     *
     * <p>一定要 id 夾到先算（2026-09-21 Kenny 指示）。以前 id 一有一冇就退返去
     * 「三十秒內就當係」，結果：你喺手錶熄咗 07:00，07:01 第二隻響，佢仲喺三十秒
     * 窗入面，就會自己收聲 —— 你根本未見過第二隻。而家夾唔到就照響，等你自己撳。
     *
     * <p>手錶送 dismiss 一路都帶 id（WatchAlarmActivity.alarmId()），電話開鬧鐘畫面
     * 亦一定帶 id（AlarmScheduler / AlarmAlertService），所以正常情況兩邊都有得對。
     */
    private boolean shouldDismissFor(String dismissAlarmId, long sentAtMillis) {
        String id = dismissAlarmId == null ? "" : dismissAlarmId.trim();
        String myId = myAlarmId();
        if (id.isEmpty() || myId.isEmpty()) {
            DiagLog.log(this, "watch dismiss ignored: no id to match (theirs='"
                    + id + "' mine='" + myId + "')");
            return false;
        }
        return id.equals(myId);
    }

    private String myAlarmId() {
        String id = getIntent().getStringExtra(AlarmScheduler.EXTRA_ALARM_ID);
        return id == null ? "" : id.trim();
    }

    /**
     * 開畫面之前，手錶係咪啱啱已經熄咗<b>同一隻</b>鬧鐘。
     *
     * <p>個三十秒窗係為咗趕時間差：手錶嗰個訊息可能喺畫面開之前就到咗，冇呢個記錄
     * 就會落空，電話照響，要撳兩次。但一定要 id 夾到先收聲（2026-09-21 Kenny 指示）
     * —— 三十秒內響起嘅<b>另一隻</b>鬧鐘要繼續響，等你自己 dismiss。
     */
    private boolean hasRecentWatchDismiss() {
        long at = getSharedPreferences(PREFS, MODE_PRIVATE).getLong(KEY_WATCH_DISMISS_AT, 0L);
        long now = System.currentTimeMillis();
        if (at <= 0L || now - at < 0L || now - at >= WATCH_DISMISS_VALID_MS) {
            return false;
        }
        String dismissedId = getSharedPreferences(PREFS, MODE_PRIVATE).getString(KEY_WATCH_DISMISS_ID, "");
        String myId = myAlarmId();
        if (dismissedId.isEmpty() || myId.isEmpty()) {
            return false;
        }
        return dismissedId.equals(myId);
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
        return Clock30.format(millis);
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

    private void stopAlert() {
        if (wakeLock != null && wakeLock.isHeld()) {
            wakeLock.release();
        }
        wakeLock = null;
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }
}
