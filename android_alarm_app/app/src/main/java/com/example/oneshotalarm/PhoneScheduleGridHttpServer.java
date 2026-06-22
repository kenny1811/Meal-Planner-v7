package com.example.oneshotalarm;

import android.content.Context;
import android.util.Log;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.net.ServerSocket;
import java.net.Socket;
import java.text.SimpleDateFormat;
import java.util.Locale;

final class PhoneScheduleGridHttpServer {
    private static final String TAG = "PhoneScheduleHttp";
    private static final int PORT = 8765;
    private static final Object LOCK = new Object();
    private static volatile boolean started = false;

    private PhoneScheduleGridHttpServer() {
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
            if ("/export.xml".equals(path) || "/api/schedule-grid/export-xml".equals(path)) {
                writeResponse(out, 200, "application/xml; charset=utf-8", buildScheduleGridXml(context).getBytes("UTF-8"));
                return;
            }
            writeResponse(out, 404, "text/plain; charset=utf-8", "Not found\n".getBytes("UTF-8"));
        } catch (IOException e) {
            Log.e(TAG, "Handle phone schedule_grid HTTP request failed", e);
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

    private static String buildScheduleGridXml(Context context) {
        String exportDate = AlarmStore.getPlanDate(context);
        if (exportDate == null || exportDate.trim().isEmpty()) {
            exportDate = new SimpleDateFormat("yyyy-MM-dd", Locale.getDefault()).format(System.currentTimeMillis());
        }
        String rosterCode = AlarmStore.getRosterCode(context);
        if (rosterCode == null) {
            rosterCode = "";
        }
        JSONArray alarms = AlarmStore.getAlarms(context);
        StringBuilder builder = new StringBuilder();
        builder.append("<?xml version='1.0' encoding='UTF-8' standalone='yes'?>").append('\n');
        builder.append("<schedule_grid effective_date=\"").append(escapeXml(exportDate))
                .append("\" roster_code=\"").append(escapeXml(rosterCode.trim())).append("\">").append('\n');
        String header = exportDate.trim() + (rosterCode.trim().isEmpty() ? "" : " " + rosterCode.trim());
        builder.append("  <section>").append(escapeXml(header)).append("</section>").append('\n');
        for (int i = 0; i < alarms.length(); i++) {
            JSONObject alarm = alarms.optJSONObject(i);
            if (alarm == null) {
                continue;
            }
            long triggerAt = alarm.optLong("trigger_at_epoch_ms", 0L);
            String trigger = triggerAt > 0L
                    ? new SimpleDateFormat("HH:mm", Locale.getDefault()).format(triggerAt)
                    : "";
            String label = alarm.optString("label", "").trim();
            if (trigger.isEmpty() || label.isEmpty()) {
                continue;
            }
            builder.append("  <alarm>").append('\n');
            builder.append("    <time>").append(escapeXml(trigger)).append("</time>").append('\n');
            builder.append("    <content>").append(escapeXml(label)).append("</content>").append('\n');
            builder.append("  </alarm>").append('\n');
        }
        builder.append("</schedule_grid>").append('\n');
        return builder.toString();
    }

    private static String escapeXml(String value) {
        if (value == null) {
            return "";
        }
        return value
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("\"", "&quot;")
                .replace("'", "&apos;");
    }
}
