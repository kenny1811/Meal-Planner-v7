package com.example.oneshotalarm;

import android.content.Context;
import android.util.Log;

import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.net.ServerSocket;
import java.net.Socket;

/**
 * 電話本機 HTTP server：淨係做手錶遠端截圖（/capture/watch，電話做中繼），唔使 adb。
 * 電話自己嗰個 accessibility 截圖 service 已經拆——Mox Bank 會當佢係惡意程式，
 * 用戶要長期喺 設定→協助工具 熄咗佢，即係實質永遠用唔到。
 * 行位表以前經 /export.xml 俾電腦 pull，而家改由電話「to Computer」推，嗰條路亦拆咗。
 */
final class PhoneCaptureHttpServer {
    private static final String TAG = "PhoneCaptureHttp";
    private static final int PORT = 8765;
    private static final Object LOCK = new Object();
    private static volatile boolean started = false;

    private PhoneCaptureHttpServer() {
    }

    static void start(Context context) {
        synchronized (LOCK) {
            if (started) {
                return;
            }
            started = true;
            Context appContext = context.getApplicationContext();
            Thread thread = new Thread(() -> runServer(appContext), "phone-schedule-grid-http");
            thread.setDaemon(true);
            thread.start();
        }
    }

    private static void runServer(Context context) {
        try (ServerSocket server = new ServerSocket(PORT)) {
            while (true) {
                Socket socket = server.accept();
                Thread worker = new Thread(() -> handleClient(context, socket), "phone-schedule-grid-http-client");
                worker.setDaemon(true);
                worker.start();
            }
        } catch (IOException e) {
            Log.e(TAG, "Phone schedule_grid HTTP server stopped", e);
            synchronized (LOCK) {
                started = false;
            }
        }
    }

    private static void handleClient(Context context, Socket socket) {
        try (Socket client = socket;
             BufferedInputStream in = new BufferedInputStream(client.getInputStream());
             BufferedOutputStream out = new BufferedOutputStream(client.getOutputStream())) {
            String requestLine = readRequestLine(in);
            drainHeaders(in);
            String path = parsePath(requestLine);
            if ("/health".equals(path)) {
                writeResponse(out, 200, "application/json; charset=utf-8", "{\"ok\":true}\n".getBytes("UTF-8"));
                return;
            }
            if ("/capture/watch".equals(path)) {
                // 手錶截圖：電話做中繼（message 去、ChannelClient 返）。
                byte[] png = WatchCaptureBridge.requestCapture(context, 20000);
                if (png == null) {
                    writeResponse(out, 503, "text/plain; charset=utf-8",
                            "Watch capture failed (watch offline or service not enabled)\n".getBytes("UTF-8"));
                } else {
                    writeResponse(out, 200, "image/png", png);
                }
                return;
            }
            writeResponse(out, 404, "text/plain; charset=utf-8", "Not found\n".getBytes("UTF-8"));
        } catch (IOException e) {
            Log.e(TAG, "Handle phone capture HTTP request failed", e);
        }
    }

    private static String readRequestLine(BufferedInputStream in) throws IOException {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        int b;
        while ((b = in.read()) >= 0) {
            if (b == '\n') {
                break;
            }
            if (b != '\r') {
                buffer.write(b);
            }
            if (buffer.size() > 4096) {
                break;
            }
        }
        return buffer.toString("UTF-8");
    }

    private static void drainHeaders(BufferedInputStream in) throws IOException {
        int previous = -1;
        int current;
        int lfCount = 0;
        while ((current = in.read()) >= 0) {
            if (current == '\n') {
                lfCount++;
                if (previous == '\n' || lfCount >= 2) {
                    return;
                }
            } else if (current != '\r') {
                lfCount = 0;
            }
            previous = current;
        }
    }

    private static String parsePath(String requestLine) {
        if (requestLine == null) {
            return "";
        }
        String[] parts = requestLine.trim().split("\\s+");
        if (parts.length < 2) {
            return "";
        }
        String path = parts[1];
        int query = path.indexOf('?');
        return query >= 0 ? path.substring(0, query) : path;
    }

    private static void writeResponse(BufferedOutputStream out, int status, String contentType, byte[] body) throws IOException {
        String reason = status == 200 ? "OK" : status == 404 ? "Not Found" : "Error";
        String head = "HTTP/1.1 " + status + " " + reason + "\r\n"
                + "Content-Type: " + contentType + "\r\n"
                + "Content-Length: " + body.length + "\r\n"
                + "Connection: close\r\n"
                + "\r\n";
        out.write(head.getBytes("UTF-8"));
        out.write(body);
        out.flush();
    }

}
