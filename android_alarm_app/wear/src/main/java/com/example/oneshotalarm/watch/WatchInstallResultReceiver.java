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
            }
            return;
        }
        String message = status == PackageInstaller.STATUS_SUCCESS
                ? "Watch app updated"
                : "Watch install failed: " + intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE);
        Log.d(TAG, "Watch install result: " + status + " " + message);
        Toast.makeText(context, message, Toast.LENGTH_LONG).show();
    }
}
