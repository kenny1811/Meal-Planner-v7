package com.example.oneshotalarm;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageInstaller;
import android.util.Log;
import android.widget.Toast;

/**
 * PackageInstaller commit 結果：PENDING_USER_ACTION 就帶起系統確認框，
 * 其他 status 用 Toast 話你知成功/失敗。
 */
public class InstallResultReceiver extends BroadcastReceiver {
    private static final String TAG = "AppUpdater";
    static final String ACTION_INSTALL_RESULT = "com.example.oneshotalarm.INSTALL_RESULT";

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
                    Log.e(TAG, "Cannot start install confirm", e);
                }
            }
            return;
        }
        String message = status == PackageInstaller.STATUS_SUCCESS
                ? "Update installed"
                : "Install failed: " + intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE);
        Log.d(TAG, "Install result: " + status + " " + message);
        Toast.makeText(context, message, Toast.LENGTH_LONG).show();
    }
}
