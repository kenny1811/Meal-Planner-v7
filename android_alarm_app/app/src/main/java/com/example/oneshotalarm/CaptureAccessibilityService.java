package com.example.oneshotalarm;

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
 * 遠端截圖（Accessibility takeScreenshot）：喺 設定→協助工具 開一次，
 * 重啟唔甩、唔使每次批准、idle 零耗電。PC 經電話 HTTP /capture 叫，唔使 adb。
 */
public class CaptureAccessibilityService extends AccessibilityService {
    private static final String TAG = "CaptureService";
    private static volatile CaptureAccessibilityService instance;

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
        Log.d(TAG, "Capture service connected");
    }

    @Override
    public void onDestroy() {
        if (instance == this) {
            instance = null;
        }
        super.onDestroy();
    }

    static boolean isEnabled() {
        return instance != null;
    }

    /** 同步影一張全螢幕 PNG（喺 worker thread 叫）；null＝服務未開或失敗。 */
    static byte[] captureNow() {
        CaptureAccessibilityService service = instance;
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
                            Log.e(TAG, "Convert screenshot failed", e);
                        }
                        latch.countDown();
                    }

                    @Override
                    public void onFailure(int errorCode) {
                        Log.e(TAG, "takeScreenshot failed: " + errorCode);
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
