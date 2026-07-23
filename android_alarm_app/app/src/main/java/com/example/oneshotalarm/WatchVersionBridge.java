package com.example.oneshotalarm;

import android.content.Context;
import android.util.Log;

import com.google.android.gms.tasks.Tasks;
import com.google.android.gms.wearable.Node;
import com.google.android.gms.wearable.Wearable;

import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

/**
 * 問手錶 app 而家裝咗邊個 versionCode（message 去、message 返）。
 * 舊版手錶唔識答 → 回 0，caller 當唔知照傳。
 */
final class WatchVersionBridge {
    private static final String TAG = "WatchVersionBridge";
    static final String VERSION_REQUEST_PATH = "/oneshotalarm/version-request";
    static final String VERSION_RESULT_PATH = "/oneshotalarm/version-result";

    private static final Object LOCK = new Object();
    private static CountDownLatch pending;
    private static long resultVersion;

    private WatchVersionBridge() {
    }

    /** 同步查手錶版本（worker thread）；0＝手錶唔喺度/舊版唔識答/超時。 */
    static long requestVersion(Context context, long timeoutMs) {
        CountDownLatch latch = new CountDownLatch(1);
        synchronized (LOCK) {
            pending = latch;
            resultVersion = 0;
        }
        try {
            List<Node> nodes = Tasks.await(
                    Wearable.getNodeClient(context).getConnectedNodes(), 5, TimeUnit.SECONDS);
            Node watch = null;
            for (Node node : nodes) {
                if (node.isNearby()) {
                    watch = node;
                    break;
                }
            }
            if (watch == null && !nodes.isEmpty()) {
                watch = nodes.get(0);
            }
            if (watch == null) {
                return 0;
            }
            Tasks.await(Wearable.getMessageClient(context)
                    .sendMessage(watch.getId(), VERSION_REQUEST_PATH, new byte[0]),
                    5, TimeUnit.SECONDS);
        } catch (Exception e) {
            Log.w(TAG, "Send version request failed", e);
            return 0;
        }
        try {
            latch.await(timeoutMs, TimeUnit.MILLISECONDS);
        } catch (InterruptedException ignored) {
        }
        synchronized (LOCK) {
            long version = resultVersion;
            pending = null;
            resultVersion = 0;
            return version;
        }
    }

    static void deliver(long version) {
        synchronized (LOCK) {
            resultVersion = version;
            if (pending != null) {
                pending.countDown();
            }
        }
    }
}
