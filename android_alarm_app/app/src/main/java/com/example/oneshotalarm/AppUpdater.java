package com.example.oneshotalarm;

import android.app.Activity;
import android.app.AlertDialog;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageInstaller;
import android.net.Uri;
import android.os.Build;
import android.util.Log;
import android.widget.TextView;
import android.widget.Toast;

import com.google.android.gms.wearable.ChannelClient;
import com.google.android.gms.wearable.Node;
import com.google.android.gms.wearable.Wearable;

import org.json.JSONObject;

import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.List;

/**
 * In-app updater（唔靠 adb）：
 * - 電話：問 PC /api/app-version，有新版就下載 /apk（Range 續傳）→ PackageInstaller 裝。
 * - 手錶：下載 /apk/watch → ChannelClient 推去手錶，手錶側自己 PackageInstaller 裝。
 * 任何網絡（LAN / meshnet+mobile data）都行，斷線逐段重試。
 */
final class AppUpdater {
    private static final String TAG = "AppUpdater";
    static final String WATCH_APK_CHANNEL_PATH = "/oneshotalarm/wear-apk";
    private static final int DOWNLOAD_READ_TIMEOUT_MS = 30000;
    private static final int MAX_RESUME_ATTEMPTS = 40;

    private AppUpdater() {
    }

    interface Progress {
        void update(String text);
    }

    /** 撳標題開嘅更新窗：查版本 → 兩個掣（Update phone / Update watch）。 */
    static void showUpdateDialog(Activity activity) {
        TextView status = new TextView(activity);
        status.setPadding(dp(activity, 20), dp(activity, 12), dp(activity, 20), dp(activity, 4));
        status.setTextSize(13);
        status.setText("Checking versions...");
        AlertDialog dialog = new AlertDialog.Builder(activity)
                .setTitle("App updates")
                .setView(status)
                .setPositiveButton("Update phone", null)
                .setNeutralButton("Update watch", null)
                .setNegativeButton("Close", null)
                .create();
        dialog.setOnShowListener(d -> {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v ->
                    runPhoneUpdate(activity, text -> activity.runOnUiThread(() -> status.setText(text))));
            dialog.getButton(AlertDialog.BUTTON_NEUTRAL).setOnClickListener(v ->
                    runWatchUpdate(activity, text -> activity.runOnUiThread(() -> status.setText(text))));
        });
        dialog.show();
        new Thread(() -> {
            String text;
            try {
                JSONObject info = new JSONObject(
                        ApiClient.request(activity, "GET", "/api/app-version", null, 15000));
                long current = currentVersionCode(activity);
                JSONObject phone = info.optJSONObject("app");
                JSONObject wear = info.optJSONObject("wear");
                int phoneServer = phone != null ? phone.optInt("version_code", 0) : 0;
                int wearServer = wear != null ? wear.optInt("version_code", 0) : 0;
                boolean phoneReady = phone != null && phone.optBoolean("apk_ready", false);
                boolean wearReady = wear != null && wear.optBoolean("apk_ready", false);
                text = "Phone: v" + current + " installed, server v" + phoneServer
                        + (phoneReady ? "" : " (APK not built)")
                        + (phoneServer > current ? " — update available" : " — up to date")
                        + "\nWatch: server v" + wearServer
                        + (wearReady ? "" : " (APK not built)");
            } catch (Exception e) {
                text = "Cannot reach PC: " + e.getMessage();
            }
            String finalText = text;
            activity.runOnUiThread(() -> status.setText(finalText));
        }, "app-update-check").start();
    }

    /** App 開返嚟時靜靜哋查一次（唔嘈：有新版先彈 dialog）。 */
    static void autoCheck(Activity activity) {
        new Thread(() -> {
            try {
                JSONObject info = new JSONObject(
                        ApiClient.request(activity, "GET", "/api/app-version", null, 8000));
                JSONObject phone = info.optJSONObject("app");
                int server = phone != null ? phone.optInt("version_code", 0) : 0;
                boolean ready = phone != null && phone.optBoolean("apk_ready", false);
                if (ready && server > currentVersionCode(activity)) {
                    activity.runOnUiThread(() -> new AlertDialog.Builder(activity)
                            .setTitle("New version v" + server)
                            .setMessage("Download and install now?")
                            .setPositiveButton("Update", (d, w) -> {
                                Toast.makeText(activity, "Downloading update...", Toast.LENGTH_SHORT).show();
                                runPhoneUpdate(activity, text ->
                                        Log.d(TAG, "auto update: " + text));
                            })
                            .setNegativeButton("Later", null)
                            .show());
                }
            } catch (Exception ignored) {
                // PC 唔喺度就算，下次先再查。
            }
        }, "app-update-autocheck").start();
    }

    static long currentVersionCode(Context context) {
        try {
            android.content.pm.PackageInfo info = context.getPackageManager()
                    .getPackageInfo(context.getPackageName(), 0);
            return Build.VERSION.SDK_INT >= Build.VERSION_CODES.P
                    ? info.getLongVersionCode() : info.versionCode;
        } catch (Exception e) {
            return 0;
        }
    }

    private static void runPhoneUpdate(Context context, Progress progress) {
        new Thread(() -> {
            try {
                File apk = new File(context.getCacheDir(), "update-phone.apk");
                download(context, "/apk", apk, progress);
                progress.update("Installing... confirm the system prompt.");
                installApk(context, apk);
            } catch (Exception e) {
                Log.e(TAG, "Phone update failed", e);
                progress.update("Phone update failed: " + e.getMessage());
            }
        }, "phone-update").start();
    }

    private static void runWatchUpdate(Context context, Progress progress) {
        new Thread(() -> {
            try {
                File apk = new File(context.getCacheDir(), "update-wear.apk");
                download(context, "/apk/watch", apk, progress);
                progress.update("Sending to watch over Bluetooth...");
                sendApkToWatch(context, apk, progress);
            } catch (Exception e) {
                Log.e(TAG, "Watch update failed", e);
                progress.update("Watch update failed: " + e.getMessage());
            }
        }, "watch-update").start();
    }

    /** Range 續傳下載：斷線由斷點繼續，逐次輪換 LAN/meshnet server。 */
    private static void download(Context context, String path, File dest, Progress progress)
            throws Exception {
        if (dest.exists() && !dest.delete()) {
            Log.w(TAG, "Cannot delete old " + dest);
        }
        String[] candidates = AlarmStore.getAutoSyncServerCandidates(context);
        long total = -1;
        Exception lastError = null;
        for (int attempt = 0; attempt < MAX_RESUME_ATTEMPTS; attempt++) {
            String base = ApiClient.normalizeServer(candidates[attempt % candidates.length]);
            if (base.isEmpty()) {
                continue;
            }
            long offset = dest.length();
            if (total > 0 && offset >= total) {
                return;
            }
            HttpURLConnection conn = null;
            try {
                conn = (HttpURLConnection) new URL(base + path).openConnection();
                conn.setConnectTimeout(ApiClient.CONNECT_TIMEOUT_MS);
                conn.setReadTimeout(DOWNLOAD_READ_TIMEOUT_MS);
                if (offset > 0) {
                    conn.setRequestProperty("Range", "bytes=" + offset + "-");
                }
                int code = conn.getResponseCode();
                if (code == 200) {
                    offset = 0; // server 唔理 Range：由頭嚟過
                    total = conn.getContentLengthLong();
                } else if (code == 206) {
                    String range = conn.getHeaderField("Content-Range");
                    if (range != null && range.contains("/")) {
                        total = Long.parseLong(range.substring(range.indexOf('/') + 1).trim());
                    }
                } else {
                    throw new Exception("HTTP " + code);
                }
                try (InputStream in = conn.getInputStream();
                        FileOutputStream out = new FileOutputStream(dest, offset > 0)) {
                    byte[] buffer = new byte[65536];
                    long written = offset;
                    int read;
                    while ((read = in.read(buffer)) >= 0) {
                        out.write(buffer, 0, read);
                        written += read;
                        progress.update("Downloading " + (written / 1048576) + " / "
                                + (total > 0 ? total / 1048576 : "?") + " MB");
                    }
                }
                if (total <= 0 || dest.length() >= total) {
                    return;
                }
            } catch (Exception e) {
                lastError = e;
                Log.w(TAG, "Download attempt " + attempt + " failed: " + e.getMessage());
                try {
                    Thread.sleep(1200);
                } catch (InterruptedException ignored) {
                }
            } finally {
                if (conn != null) {
                    conn.disconnect();
                }
            }
        }
        throw lastError != null ? lastError : new Exception("download failed");
    }

    /** PackageInstaller session：commit 後系統會彈確認框（InstallResultReceiver 負責帶起）。 */
    static void installApk(Context context, File apk) throws Exception {
        PackageInstaller installer = context.getPackageManager().getPackageInstaller();
        PackageInstaller.SessionParams params = new PackageInstaller.SessionParams(
                PackageInstaller.SessionParams.MODE_FULL_INSTALL);
        params.setSize(apk.length());
        int sessionId = installer.createSession(params);
        try (PackageInstaller.Session session = installer.openSession(sessionId)) {
            try (OutputStream out = session.openWrite("app.apk", 0, apk.length());
                    InputStream in = new java.io.FileInputStream(apk)) {
                byte[] buffer = new byte[65536];
                int read;
                while ((read = in.read(buffer)) >= 0) {
                    out.write(buffer, 0, read);
                }
                session.fsync(out);
            }
            Intent intent = new Intent(context, InstallResultReceiver.class)
                    .setAction(InstallResultReceiver.ACTION_INSTALL_RESULT);
            int flags = PendingIntent.FLAG_UPDATE_CURRENT;
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                flags |= PendingIntent.FLAG_MUTABLE;
            }
            PendingIntent pending = PendingIntent.getBroadcast(context, sessionId, intent, flags);
            session.commit(pending.getIntentSender());
        }
    }

    private static void sendApkToWatch(Context context, File apk, Progress progress) {
        Wearable.getNodeClient(context).getConnectedNodes()
                .addOnSuccessListener(nodes -> {
                    Node watch = pickNode(nodes);
                    if (watch == null) {
                        progress.update("Watch not connected (Bluetooth off?)");
                        return;
                    }
                    ChannelClient channelClient = Wearable.getChannelClient(context);
                    channelClient.openChannel(watch.getId(), WATCH_APK_CHANNEL_PATH)
                            .addOnSuccessListener(channel -> channelClient
                                    .sendFile(channel, Uri.fromFile(apk))
                                    .addOnSuccessListener(v -> progress.update(
                                            "Sent to watch — confirm install ON THE WATCH."))
                                    .addOnFailureListener(e -> progress.update(
                                            "Send to watch failed: " + e.getMessage())))
                            .addOnFailureListener(e -> progress.update(
                                    "Open watch channel failed: " + e.getMessage()));
                })
                .addOnFailureListener(e -> progress.update("Find watch failed: " + e.getMessage()));
    }

    private static Node pickNode(List<Node> nodes) {
        if (nodes == null || nodes.isEmpty()) {
            return null;
        }
        for (Node node : nodes) {
            if (node.isNearby()) {
                return node;
            }
        }
        return nodes.get(0);
    }

    private static int dp(Context context, int value) {
        return Math.round(context.getResources().getDisplayMetrics().density * value);
    }
}
