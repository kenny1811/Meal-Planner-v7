package com.example.oneshotalarm;

import android.content.Context;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

/**
 * LAN→meshnet failover HTTP client——全 app 共用一份。
 * 之前 DutyReportView / OnOffDutyView / ScheduleGridAutoImporter 各自抄一套，
 * 已經 drift（views 識記 last-good server、importer 唔識）；而家收歸呢度。
 * candidates 排序來自 AlarmStore.getAutoSyncServerCandidates（屋企 LAN 行先、
 * 出街 meshnet 行先）；成功嗰個 server 記住做首選，全 app 共用。
 */
final class ApiClient {
    static final int CONNECT_TIMEOUT_MS = 2500;

    /** last-good server index（對應 candidates 排陣）；volatile 俾唔同 thread 嘅 view/worker 共用。 */
    private static volatile int serverIndex = 0;

    private ApiClient() {
    }

    /** 逐個 server 試（LAN → Meshnet），成功嗰個記住做首選。method 係 "GET" 或 "POST"（jsonBody 可以 null＝無 body POST）。 */
    static String request(Context context, String method, String path, String jsonBody, int readTimeoutMs) throws Exception {
        String[] candidates = AlarmStore.getAutoSyncServerCandidates(context);
        Exception lastException = null;
        for (int i = 0; i < candidates.length; i++) {
            int idx = (serverIndex + i) % candidates.length;
            String base = normalizeServer(candidates[idx]);
            if (base.isEmpty()) {
                continue;
            }
            try {
                String body = "POST".equals(method)
                        ? httpPost(base + path, jsonBody, readTimeoutMs)
                        : httpGet(base + path, readTimeoutMs);
                serverIndex = idx;
                return body;
            } catch (Exception e) {
                lastException = e;
            }
        }
        throw lastException != null ? lastException : new Exception("no server candidates");
    }

    static String normalizeServer(String raw) {
        String server = raw == null ? "" : raw.trim();
        if (server.endsWith("/")) {
            server = server.substring(0, server.length() - 1);
        }
        if (!server.startsWith("http://") && !server.startsWith("https://")) {
            return "";
        }
        return server;
    }

    static String httpGet(String endpoint, int readTimeoutMs) throws Exception {
        HttpURLConnection conn = null;
        try {
            conn = (HttpURLConnection) new URL(endpoint).openConnection();
            conn.setRequestMethod("GET");
            conn.setConnectTimeout(CONNECT_TIMEOUT_MS);
            conn.setReadTimeout(readTimeoutMs);
            return readResponse(conn, endpoint);
        } finally {
            if (conn != null) {
                conn.disconnect();
            }
        }
    }

    static String httpPost(String endpoint, String jsonBody, int readTimeoutMs) throws Exception {
        HttpURLConnection conn = null;
        try {
            conn = (HttpURLConnection) new URL(endpoint).openConnection();
            conn.setRequestMethod("POST");
            conn.setConnectTimeout(CONNECT_TIMEOUT_MS);
            conn.setReadTimeout(readTimeoutMs);
            if (jsonBody != null) {
                conn.setDoOutput(true);
                conn.setRequestProperty("Content-Type", "application/json; charset=utf-8");
                byte[] bytes = jsonBody.getBytes(StandardCharsets.UTF_8);
                conn.setFixedLengthStreamingMode(bytes.length);
                try (OutputStream out = conn.getOutputStream()) {
                    out.write(bytes);
                }
            }
            return readResponse(conn, endpoint);
        } finally {
            if (conn != null) {
                conn.disconnect();
            }
        }
    }

    /** 非 2xx：試吓由 JSON body 抽 detail（FastAPI 格式），冇就 "HTTP code endpoint"。 */
    private static String readResponse(HttpURLConnection conn, String endpoint) throws Exception {
        int code = conn.getResponseCode();
        if (code < 200 || code >= 300) {
            String error = readStream(conn.getErrorStream());
            String detail = "";
            try {
                JSONObject body = new JSONObject(error);
                detail = body.optString("detail", "");
                if (detail.trim().isEmpty()) {
                    JSONObject errorBody = body.optJSONObject("error");
                    if (errorBody != null) {
                        detail = errorBody.optString("message", "");
                    }
                }
            } catch (Exception ignored) {
            }
            throw new Exception(!detail.trim().isEmpty()
                    ? detail
                    : "HTTP " + code + " " + endpoint);
        }
        return readStream(conn.getInputStream());
    }

    static String readStream(InputStream stream) throws Exception {
        if (stream == null) {
            return "";
        }
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        byte[] buffer = new byte[2048];
        int read;
        while ((read = stream.read(buffer)) >= 0) {
            out.write(buffer, 0, read);
        }
        return out.toString("UTF-8");
    }
}
