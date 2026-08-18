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
 * candidates 來自 AlarmStore.getAutoSyncServerCandidates（屋企＝LAN 行先 meshnet 後備、
 * 出街＝淨係 meshnet）；成功嗰個 server 記住做首選，全 app 共用。
 */
final class ApiClient {
    /** LAN candidate：唔喺屋企個網就一定唔通，唔好等，快啲 fail 去試 meshnet。 */
    static final int CONNECT_TIMEOUT_MS = 2500;

    /**
     * Meshnet candidate：出街用流動數據，部機啱啱由 Doze／radio idle 醒返嗰陣，
     * NordVPN 條 tunnel 要幾秒先重建好——等 2.5 秒一定 fail（"after 2500ms"），
     * 撳多次先得。所以 meshnet 嗰個 candidate 俾多啲時間，一 tap 就成事。
     */
    static final int MESHNET_CONNECT_TIMEOUT_MS = 9000;

    /**
     * 電話每次打上電腦都報上名——電腦記低嗰個來源 IP，就可以反過來 push 落電話
     * （例如打風改咗行位表，即刻叫電話重新匯入），唔使喺 config 寫死電話 IP。
     */
    private static final String CLIENT_HEADER = "X-Alarm-Client";
    private static final String CLIENT_HEADER_VALUE = "phone";

    /**
     * last-good server：記住個 URL，唔記陣列位置——candidates 嘅次序同長度會跟
     * 屋企／出街變（出街得 meshnet 一個），記位置即係記錯嘢。
     * volatile 俾唔同 thread 嘅 view/worker 共用。
     */
    private static volatile String lastGoodServer = "";

    private ApiClient() {
    }

    /** 逐個 server 試（LAN → Meshnet），成功嗰個記住做首選。method 係 "GET" 或 "POST"（jsonBody 可以 null＝無 body POST）。 */
    static String request(Context context, String method, String path, String jsonBody, int readTimeoutMs) throws Exception {
        byte[] body = jsonBody == null ? null : jsonBody.getBytes(StandardCharsets.UTF_8);
        return request(context, method, path, body, "application/json; charset=utf-8", readTimeoutMs);
    }

    /** 同上，但可以送任何 content-type（例如行位表 XML push）。 */
    static String request(
            Context context,
            String method,
            String path,
            byte[] body,
            String contentType,
            int readTimeoutMs
    ) throws Exception {
        String[] candidates = orderByLastGood(AlarmStore.getAutoSyncServerCandidates(context), lastGoodServer);
        Exception lastException = null;
        for (String candidate : candidates) {
            String base = normalizeServer(candidate);
            if (base.isEmpty()) {
                continue;
            }
            try {
                String responseBody = "POST".equals(method)
                        ? httpPost(base + path, body, contentType, readTimeoutMs)
                        : httpGet(base + path, readTimeoutMs);
                lastGoodServer = base;
                return responseBody;
            } catch (Exception e) {
                lastException = e;
            }
        }
        throw lastException != null ? lastException : new Exception("no server candidates");
    }

    /** 上次成功嗰個排先（要仲喺候選名單先算）；其餘維持原本次序。 */
    static String[] orderByLastGood(String[] candidates, String preferred) {
        if (preferred == null || preferred.isEmpty() || candidates.length < 2) {
            return candidates;
        }
        java.util.ArrayList<String> first = new java.util.ArrayList<>(candidates.length);
        java.util.ArrayList<String> rest = new java.util.ArrayList<>(candidates.length);
        for (String candidate : candidates) {
            if (preferred.equals(normalizeServer(candidate))) {
                first.add(candidate);
            } else {
                rest.add(candidate);
            }
        }
        if (first.isEmpty()) {
            return candidates;
        }
        first.addAll(rest);
        return first.toArray(new String[0]);
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

    /** Meshnet 個 host 俾長 timeout，其餘（LAN）維持短 timeout。 */
    static int connectTimeoutFor(String endpoint) {
        return endpoint != null && endpoint.startsWith(AlarmStore.MESHNET_AUTO_SYNC_SERVER)
                ? MESHNET_CONNECT_TIMEOUT_MS
                : CONNECT_TIMEOUT_MS;
    }

    static String httpGet(String endpoint, int readTimeoutMs) throws Exception {
        HttpURLConnection conn = null;
        try {
            conn = (HttpURLConnection) new URL(endpoint).openConnection();
            conn.setRequestMethod("GET");
            conn.setConnectTimeout(connectTimeoutFor(endpoint));
            conn.setReadTimeout(readTimeoutMs);
            conn.setRequestProperty(CLIENT_HEADER, CLIENT_HEADER_VALUE);
            return readResponse(conn, endpoint);
        } finally {
            if (conn != null) {
                conn.disconnect();
            }
        }
    }

    static String httpPost(String endpoint, byte[] body, String contentType, int readTimeoutMs) throws Exception {
        HttpURLConnection conn = null;
        try {
            conn = (HttpURLConnection) new URL(endpoint).openConnection();
            conn.setRequestMethod("POST");
            conn.setConnectTimeout(connectTimeoutFor(endpoint));
            conn.setReadTimeout(readTimeoutMs);
            conn.setRequestProperty(CLIENT_HEADER, CLIENT_HEADER_VALUE);
            if (body != null) {
                conn.setDoOutput(true);
                conn.setRequestProperty("Content-Type", contentType);
                conn.setFixedLengthStreamingMode(body.length);
                try (OutputStream out = conn.getOutputStream()) {
                    out.write(body);
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
