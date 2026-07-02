package com.example.oneshotalarm.watch;

import android.app.Activity;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.PowerManager;
import android.os.Process;
import android.util.Log;
import android.view.Gravity;
import android.view.Window;
import android.view.WindowManager;
import android.widget.LinearLayout;
import android.widget.TextView;

public class WatchAlarmActivity extends Activity {
    private static final String TAG = "ShiftAlarmWatch";
    static final String EXTRA_ALARM_ID = "alarm_id";
    static final String EXTRA_TIME = "time";
    static final String EXTRA_LABEL = "label";
    static final String EXTRA_DISMISS = "dismiss";
    static final String ACTION_DISMISS_LOCAL = "com.example.oneshotalarm.watch.ACTION_DISMISS_LOCAL";

    private boolean dismissed = false;
    private boolean receiverRegistered = false;
    private PowerManager.WakeLock wakeLock;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final BroadcastReceiver dismissReceiver = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            Log.d(TAG, "Watch alarm local dismiss");
            dismissed = true;
            stopAlert();
            finishAndExitSoon();
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        if (getIntent().getBooleanExtra(EXTRA_DISMISS, false)) {
            dismissed = true;
            stopAlert();
            finishAndExitSoon();
            return;
        }
        turnScreenOn();
        acquireWakeLock();
        buildUi();
    }

    @Override
    protected void onStart() {
        super.onStart();
        registerDismissReceiver();
    }

    @Override
    protected void onStop() {
        super.onStop();
        unregisterDismissReceiver();
    }

    @Override
    protected void onDestroy() {
        unregisterDismissReceiver();
        releaseWakeLock();
        if (dismissed) {
            stopAlert();
        }
        super.onDestroy();
    }

    @Override
    protected void onNewIntent(android.content.Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        if (intent != null && intent.getBooleanExtra(EXTRA_DISMISS, false)) {
            dismissed = true;
            stopAlert();
            finishAndExitSoon();
        }
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
        String time = getIntent().getStringExtra(EXTRA_TIME);
        String label = getIntent().getStringExtra(EXTRA_LABEL);
        if (time == null || time.trim().isEmpty()) {
            time = "--:--";
        }
        if (label == null || label.trim().isEmpty()) {
            label = "Waiting for phone alarm";
        }

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setGravity(Gravity.CENTER);
        root.setPadding(dp(10), dp(8), dp(10), dp(8));
        root.setBackgroundColor(0xFF000000);
        root.setClickable(true);
        root.setOnClickListener(v -> dismissByTouch());

        TextView timeView = new TextView(this);
        timeView.setText(time);
        timeView.setTextColor(0xFFFFFFFF);
        timeView.setTextSize(42);
        timeView.setGravity(Gravity.CENTER);
        timeView.setIncludeFontPadding(false);
        root.addView(timeView, weightedHeight(1f));

        TextView labelView = new TextView(this);
        labelView.setText(label);
        labelView.setTextColor(0xFFFFFFFF);
        labelView.setTextSize(24);
        labelView.setGravity(Gravity.CENTER);
        labelView.setSingleLine(false);
        labelView.setPadding(dp(8), dp(6), dp(8), dp(6));
        root.addView(labelView, weightedHeight(2f));

        setContentView(root);
    }

    private void dismissByTouch() {
        if (dismissed) {
            return;
        }
        Log.d(TAG, "Watch alarm screen tapped");
        dismissed = true;
        stopAlert();
        sendDismissToPhone();
        WatchScheduleDisplayState.refreshFromCacheAndRequest(this);
        finishAndExitSoon();
    }

    private void registerDismissReceiver() {
        if (receiverRegistered) {
            return;
        }
        IntentFilter filter = new IntentFilter(ACTION_DISMISS_LOCAL);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            registerReceiver(dismissReceiver, filter, Context.RECEIVER_NOT_EXPORTED);
        } else {
            registerReceiver(dismissReceiver, filter);
        }
        receiverRegistered = true;
    }

    private void unregisterDismissReceiver() {
        if (!receiverRegistered) {
            return;
        }
        try {
            unregisterReceiver(dismissReceiver);
        } catch (IllegalArgumentException ignored) {
        }
        receiverRegistered = false;
    }

    private void stopAlert() {
        WatchAlarmService.stop(this);
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
                "oneshotalarm:watch-alarm"
        );
        wakeLock.acquire();
    }

    private void releaseWakeLock() {
        if (wakeLock != null && wakeLock.isHeld()) {
            wakeLock.release();
        }
        wakeLock = null;
    }

    private void sendDismissToPhone() {
        WatchDismissBridge.sendDismiss(this, alarmId());
    }

    private String alarmId() {
        String alarmId = getIntent().getStringExtra(EXTRA_ALARM_ID);
        return alarmId == null ? "" : alarmId;
    }

    private void finishAndExitSoon() {
        releaseWakeLock();
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            finishAndRemoveTask();
        } else {
            finish();
        }
        handler.postDelayed(() -> Process.killProcess(Process.myPid()), 2600);
    }

    private LinearLayout.LayoutParams weightedHeight(float weight) {
        return new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                0,
                weight
        );
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }
}
