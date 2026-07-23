package com.example.oneshotalarm.watch;

import android.accessibilityservice.AccessibilityService;
import android.graphics.Bitmap;
import android.hardware.HardwareBuffer;
import android.os.Build;
import android.util.Log;
import android.view.Display;
import android.view.accessibility.AccessibilityEvent;

import java.io.ByteArrayOutputStream;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

/**
 * 手錶遠端截圖（Accessibility takeScreenshot）：喺手錶 設定→協助工具 開一次。
 * 電話經 message 叫（PC → 電話 /capture/watch → 呢度），唔使 adb、唔使 WiFi。
 */
public class WatchCaptureAccessibilityService extends AccessibilityService {
    private static final String TAG = "ShiftAlarmWatch";
    private static volatile WatchCaptureAccessibilityService instance;

    @Override
    public void onAccessibilityEvent(AccessibilityEvent event) {
    }

    @Override
    public void onInterrupt() {
    }

    @Override
    protected void onServiceConnected() {
        super.onServiceConnected();
        instance = this;
        Log.d(TAG, "Watch capture service connected");
    }

    @Override
    public void onDestroy() {
        if (instance == this) {
            instance = null;
        }
        super.onDestroy();
    }

    /** 同步影一張 PNG（worker thread）；null＝服務未開/失敗。 */
    static byte[] captureNow() {
        WatchCaptureAccessibilityService service = instance;
        if (service == null || Build.VERSION.SDK_INT < Build.VERSION_CODES.R) {
            return null;
        }
        CountDownLatch latch = new CountDownLatch(1);
        AtomicReference<byte[]> result = new AtomicReference<>();
        service.takeScreenshot(Display.DEFAULT_DISPLAY,
                Executors.newSingleThreadExecutor(),
                new TakeScreenshotCallback() {
                    @Override
                    public void onSuccess(ScreenshotResult screenshot) {
                        try (HardwareBuffer buffer = screenshot.getHardwareBuffer()) {
                            Bitmap hardware = Bitmap.wrapHardwareBuffer(
                                    buffer, screenshot.getColorSpace());
                            if (hardware != null) {
                                Bitmap software = hardware.copy(Bitmap.Config.ARGB_8888, false);
                                hardware.recycle();
                                ByteArrayOutputStream out = new ByteArrayOutputStream();
                                software.compress(Bitmap.CompressFormat.PNG, 100, out);
                                software.recycle();
                                result.set(out.toByteArray());
                            }
                        } catch (Exception e) {
                            Log.e(TAG, "Convert watch screenshot failed", e);
                        }
                        latch.countDown();
                    }

                    @Override
                    public void onFailure(int errorCode) {
                        Log.e(TAG, "Watch takeScreenshot failed: " + errorCode);
                        latch.countDown();
                    }
                });
        try {
            latch.await(10, TimeUnit.SECONDS);
        } catch (InterruptedException ignored) {
        }
        return result.get();
    }
}
