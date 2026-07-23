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
 * 手錶截圖橋：電話出 message 叫手錶影相，手錶經 ChannelClient 回傳 PNG。
 * PC 經電話 HTTP /capture/watch 叫（電話做中繼，手錶連 WiFi 都唔使）。
 */
final class WatchCaptureBridge {
    private static final String TAG = "WatchCaptureBridge";
    static final String CAPTURE_REQUEST_PATH = "/oneshotalarm/capture-request";
    static final String CAPTURE_RESULT_PATH = "/oneshotalarm/capture-result";

    private static final Object LOCK = new Object();
    private static CountDownLatch pending;
    private static byte[] resultBytes;

    private WatchCaptureBridge() {
    }

    /** 同步問手錶攞一張截圖（喺 worker thread 叫）；null＝手錶唔喺度/超時/服務未開。 */
    static byte[] requestCapture(Context context, long timeoutMs) {
        CountDownLatch latch = new CountDownLatch(1);
        synchronized (LOCK) {
            pending = latch;
            resultBytes = null;
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
                Log.w(TAG, "No watch node connected");
                return null;
            }
            Tasks.await(Wearable.getMessageClient(context)
                    .sendMessage(watch.getId(), CAPTURE_REQUEST_PATH, new byte[0]),
                    5, TimeUnit.SECONDS);
        } catch (Exception e) {
            Log.e(TAG, "Send capture request failed", e);
            return null;
        }
        try {
            latch.await(timeoutMs, TimeUnit.MILLISECONDS);
        } catch (InterruptedException ignored) {
        }
        synchronized (LOCK) {
            byte[] result = resultBytes;
            pending = null;
            resultBytes = null;
            return result != null && result.length > 0 ? result : null;
        }
    }

    /** PhoneWearListenerService 收到手錶回傳嘅 PNG 時叫。 */
    static void deliver(byte[] bytes) {
        synchronized (LOCK) {
            resultBytes = bytes;
            if (pending != null) {
                pending.countDown();
            }
        }
    }
}
