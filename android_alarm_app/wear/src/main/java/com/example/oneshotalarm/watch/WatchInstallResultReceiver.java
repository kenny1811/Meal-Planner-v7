package com.example.oneshotalarm.watch;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageInstaller;
import android.util.Log;
import android.widget.Toast;

/**
 * 手錶 PackageInstaller commit 結果：PENDING_USER_ACTION 帶起手錶上嘅確認框。
 */
public class WatchInstallResultReceiver extends BroadcastReceiver {
    private static final String TAG = "ShiftAlarmWatch";
    static final String ACTION_INSTALL_RESULT = "com.example.oneshotalarm.watch.INSTALL_RESULT";

    @Override
    public void onReceive(Context context, Intent intent) {
        if (intent == null) {
            return;
        }
        int status = intent.getIntExtra(PackageInstaller.EXTRA_STATUS,
                PackageInstaller.STATUS_FAILURE);
        if (status == PackageInstaller.STATUS_PENDING_USER_ACTION) {
            Intent confirm = intent.getParcelableExtra(Intent.EXTRA_INTENT);
            if (confirm != null) {
                confirm.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                try {
                    context.startActivity(confirm);
                } catch (Exception e) {
                    Log.e(TAG, "Cannot start watch install confirm", e);
                }
                // Background activity launch 可能被系統靜靜哋 block（收 APK 嗰陣 app 唔喺前台），
                // 所以一定出埋 notification：撳落去先帶起確認框。
                postConfirmNotification(context, confirm);
            }
            return;
        }
        cancelConfirmNotification(context);
        String message = status == PackageInstaller.STATUS_SUCCESS
                ? "Watch app updated"
                : "Watch install failed: " + intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE);
        Log.d(TAG, "Watch install result: " + status + " " + message);
        Toast.makeText(context, message, Toast.LENGTH_LONG).show();
    }

    private static void postConfirmNotification(Context context, Intent confirm) {
        try {
            android.app.NotificationManager manager = (android.app.NotificationManager)
                    context.getSystemService(Context.NOTIFICATION_SERVICE);
            if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.O) {
                manager.createNotificationChannel(new android.app.NotificationChannel(
                        CONFIRM_CHANNEL, "App update",
                        android.app.NotificationManager.IMPORTANCE_HIGH));
            }
            android.app.PendingIntent tap = android.app.PendingIntent.getActivity(
                    context, CONFIRM_NOTIFICATION_ID, confirm,
                    android.app.PendingIntent.FLAG_UPDATE_CURRENT
                            | android.app.PendingIntent.FLAG_IMMUTABLE);
            android.app.Notification.Builder builder =
                    android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.O
                            ? new android.app.Notification.Builder(context, CONFIRM_CHANNEL)
                            : new android.app.Notification.Builder(context);
            builder.setSmallIcon(android.R.drawable.stat_sys_download_done)
                    .setContentTitle("門前直樹更新")
                    .setContentText("撳一下確認安裝")
                    .setContentIntent(tap)
                    .setAutoCancel(true);
            manager.notify(CONFIRM_NOTIFICATION_ID, builder.build());
        } catch (Exception e) {
            Log.e(TAG, "Cannot post install confirm notification", e);
        }
    }

    private static void cancelConfirmNotification(Context context) {
        try {
            android.app.NotificationManager manager = (android.app.NotificationManager)
                    context.getSystemService(Context.NOTIFICATION_SERVICE);
            manager.cancel(CONFIRM_NOTIFICATION_ID);
        } catch (Exception ignored) {
        }
    }

    private static final String CONFIRM_CHANNEL = "watch_update_confirm";
    private static final int CONFIRM_NOTIFICATION_ID = 4201;
}
