package com.example.oneshotalarm;

import android.content.Context;
import android.net.Uri;
import android.util.Log;

import org.json.JSONArray;
import org.json.JSONObject;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.NodeList;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.text.ParseException;
import java.text.SimpleDateFormat;
import java.util.Calendar;
import java.util.Locale;

import javax.xml.parsers.DocumentBuilderFactory;

final class ScheduleGridAutoImporter {
    private static final String TAG = "ScheduleGridAutoImport";
    private static final int HTTP_CONNECT_TIMEOUT_MS = 4000;
    private static final int HTTP_READ_TIMEOUT_MS = 12000;

    private ScheduleGridAutoImporter() {
    }

    static ImportResult importFromPc(Context context) throws Exception {
        if (!AlarmScheduler.canScheduleExactAlarm(context)) {
            return new ImportResult(false, 0, "", "", "no exact alarm permission");
        }
        Exception lastError = null;
        for (String candidate : AlarmStore.getAutoSyncServerCandidates(context)) {
            String server = normalizeServer(candidate);
            if (server.isEmpty()) {
                continue;
            }
            try {
                return importAllVariants(context, server);
            } catch (Exception e) {
                lastError = e;
                Log.w(TAG, "Auto import failed at " + server, e);
            }
        }
        String message = lastError == null ? "no usable server" : lastError.getMessage();
        return new ImportResult(false, 0, "", "", message);
    }

    private static ImportResult importAllVariants(Context context, String server) throws Exception {
        String body = get(server + "/api/maint/sheets/schedule_grid/export-all-xml");
        JSONObject response = new JSONObject(body);
        if (!response.optBoolean("ok", false)) {
            return new ImportResult(false, 0, "", "", "all variants response not ok");
        }
        JSONArray variants = response.optJSONArray("variants");
        if (variants == null || variants.length() == 0) {
            return new ImportResult(false, 0, "", "", "no schedule variants");
        }
        String currentRoster = response.optString("current_roster_code", "");
        JSONArray storedVariants = new JSONArray();
        ParsedScheduleGrid selected = null;
        String selectedRoster = "";
        int totalAlarmCount = 0;
        for (int i = 0; i < variants.length(); i++) {
            JSONObject item = variants.optJSONObject(i);
            if (item == null) {
                continue;
            }
            String xml = item.optString("xml", "");
            if (xml.trim().isEmpty()) {
                continue;
            }
            ParsedScheduleGrid parsed = parse(xml);
            if (parsed.alarms.length() == 0) {
                continue;
            }
            String rosterCode = item.optString("roster_code", parsed.rosterCode);
            JSONObject stored = new JSONObject();
            stored.put("plan_date", parsed.planDate);
            stored.put("roster_code", rosterCode);
            stored.put("alarm_count", parsed.alarms.length());
            stored.put("alarms", parsed.alarms);
            storedVariants.put(stored);
            totalAlarmCount += parsed.alarms.length();
            if (item.optBoolean("is_current", false)
                    || (!currentRoster.trim().isEmpty() && rosterCode.equals(currentRoster.trim()))) {
                selected = parsed;
                selectedRoster = rosterCode;
            }
        }
        if (storedVariants.length() == 0) {
            return new ImportResult(false, 0, "", "", "no usable schedule variants");
        }
        if (selected == null) {
            String missingRoster = currentRoster == null ? "" : currentRoster.trim();
            String message = missingRoster.isEmpty()
                    ? "搵唔到當日更碼行位表"
                    : "搵唔到 " + missingRoster + " 行位表";
            return new ImportResult(false, 0, "", missingRoster, message);
        }
        AlarmStore.saveScheduleGridVariants(context, storedVariants);
        AlarmScheduler.schedulePlan(context, selected.alarms, 0L, selected.planDate, selectedRoster);
        AlarmStore.markLastImportNow(context);
        Log.d(TAG, "Imported " + storedVariants.length() + " variants; active " + selectedRoster);
        return new ImportResult(
                true,
                selected.alarms.length(),
                selected.planDate,
                selectedRoster,
                "ok variants=" + storedVariants.length(),
                storedVariants.length(),
                totalAlarmCount
        );
    }

    private static String normalizeServer(String raw) {
        String server = raw == null ? "" : raw.trim();
        if (server.endsWith("/")) {
            server = server.substring(0, server.length() - 1);
        }
        if (!server.startsWith("http://") && !server.startsWith("https://")) {
            return "";
        }
        return server;
    }

    private static void post(String endpoint) throws Exception {
        HttpURLConnection conn = null;
        try {
            conn = (HttpURLConnection) new URL(endpoint).openConnection();
            conn.setRequestMethod("POST");
            conn.setConnectTimeout(HTTP_CONNECT_TIMEOUT_MS);
            conn.setReadTimeout(HTTP_READ_TIMEOUT_MS);
            int code = conn.getResponseCode();
            if (code < 200 || code >= 300) {
                throw new Exception("HTTP " + code + " POST " + endpoint);
            }
        } finally {
            if (conn != null) {
                conn.disconnect();
            }
        }
    }

    private static String get(String endpoint) throws Exception {
        HttpURLConnection conn = null;
        try {
            conn = (HttpURLConnection) new URL(endpoint).openConnection();
            conn.setRequestMethod("GET");
            conn.setConnectTimeout(HTTP_CONNECT_TIMEOUT_MS);
            conn.setReadTimeout(HTTP_READ_TIMEOUT_MS);
            int code = conn.getResponseCode();
            if (code < 200 || code >= 300) {
                String error = readInputStreamText(conn.getErrorStream());
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
                if (!detail.trim().isEmpty()) {
                    throw new Exception(detail);
                }
                throw new Exception(error.trim().isEmpty()
                        ? "HTTP " + code + " GET " + endpoint
                        : "HTTP " + code + " " + error);
            }
            return readInputStreamText(conn.getInputStream());
        } finally {
            if (conn != null) {
                conn.disconnect();
            }
        }
    }

    private static String readInputStreamText(InputStream inputStream) throws Exception {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        byte[] buffer = new byte[2048];
        int read;
        while ((read = inputStream.read(buffer)) >= 0) {
            out.write(buffer, 0, read);
        }
        return out.toString("UTF-8");
    }

    private static ParsedScheduleGrid parse(String xml) throws Exception {
        DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
        try {
            factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
        } catch (Exception ignored) {
        }
        Document document = factory.newDocumentBuilder().parse(
                new ByteArrayInputStream(xml.getBytes("UTF-8"))
        );
        Element root = document.getDocumentElement();
        String planDate = "";
        String rosterCode = "";
        if (root != null) {
            planDate = normalizeDate(root.getAttribute("effective_date"));
        }

        NodeList sections = document.getElementsByTagName("section");
        if (sections.getLength() > 0) {
            String header = text(sections.item(0));
            String headerDate = dateFromHeader(header);
            if (!headerDate.isEmpty()) {
                planDate = headerDate;
            }
            rosterCode = rosterFromHeader(header);
        }

        if (planDate.isEmpty()) {
            planDate = todayIso();
        }

        JSONArray alarms = new JSONArray();
        NodeList timeNodes = document.getElementsByTagName("alarm_time");
        NodeList labelNodes = document.getElementsByTagName("alarm_label");
        int xmlRowCount = Math.min(timeNodes.getLength(), labelNodes.getLength());
        for (int i = 0; i < xmlRowCount; i++) {
            String time = text(timeNodes.item(i));
            String content = text(labelNodes.item(i));
            if (time.isEmpty() || content.isEmpty()) {
                continue;
            }
            long triggerAt = triggerAt(planDate, time);
            JSONObject alarm = new JSONObject();
            alarm.put("id", "auto-xml-" + planDate + "-" + Uri.encode(time) + "-" + i);
            alarm.put("label", content);
            alarm.put("trigger_at_epoch_ms", triggerAt);
            alarm.put("trigger_at", formatIso(triggerAt));
            alarms.put(alarm);
        }
        if (alarms.length() > 0) {
            return new ParsedScheduleGrid(alarms, planDate, rosterCode);
        }

        NodeList alarmNodes = document.getElementsByTagName("alarm");
        for (int i = 0; i < alarmNodes.getLength(); i++) {
            if (!(alarmNodes.item(i) instanceof Element)) {
                continue;
            }
            Element alarmElement = (Element) alarmNodes.item(i);
            String time = firstChildText(alarmElement, "time");
            String content = firstChildText(alarmElement, "content");
            if (time.isEmpty() || content.isEmpty()) {
                continue;
            }
            long triggerAt = triggerAt(planDate, time);
            JSONObject alarm = new JSONObject();
            alarm.put("id", "auto-xml-" + planDate + "-" + Uri.encode(time) + "-" + i);
            alarm.put("label", content);
            alarm.put("trigger_at_epoch_ms", triggerAt);
            alarm.put("trigger_at", formatIso(triggerAt));
            alarms.put(alarm);
        }
        return new ParsedScheduleGrid(alarms, planDate, rosterCode);
    }

    private static String firstChildText(Element element, String tagName) {
        NodeList nodes = element.getElementsByTagName(tagName);
        if (nodes.getLength() == 0) {
            return "";
        }
        return text(nodes.item(0));
    }

    private static String text(org.w3c.dom.Node node) {
        if (node == null || node.getTextContent() == null) {
            return "";
        }
        return node.getTextContent().trim();
    }

    private static String dateFromHeader(String header) {
        if (header == null) {
            return "";
        }
        String[] parts = header.trim().split("\\s+");
        for (String part : parts) {
            String date = normalizeDate(part);
            if (!date.isEmpty()) {
                return date;
            }
        }
        return "";
    }

    private static String rosterFromHeader(String header) {
        if (header == null) {
            return "";
        }
        String[] parts = header.trim().split("\\s+");
        for (int i = parts.length - 1; i >= 0; i--) {
            String value = parts[i].trim();
            if (value.isEmpty()) {
                continue;
            }
            if (normalizeDate(value).isEmpty() && !isWeekday(value)) {
                return value;
            }
        }
        return "";
    }

    private static boolean isWeekday(String value) {
        String lower = value == null ? "" : value.trim().toLowerCase(Locale.US);
        return "mon".equals(lower)
                || "tue".equals(lower)
                || "wed".equals(lower)
                || "thu".equals(lower)
                || "fri".equals(lower)
                || "sat".equals(lower)
                || "sun".equals(lower);
    }

    private static String normalizeDate(String raw) {
        String value = raw == null ? "" : raw.trim();
        if (value.isEmpty()) {
            return "";
        }
        String[] patterns = new String[]{"yyyy-MM-dd", "dd/MM/yyyy", "d/M/yyyy", "dd-MM-yyyy", "d-M-yyyy"};
        for (String pattern : patterns) {
            try {
                SimpleDateFormat input = new SimpleDateFormat(pattern, Locale.US);
                input.setLenient(false);
                return new SimpleDateFormat("yyyy-MM-dd", Locale.US).format(input.parse(value));
            } catch (ParseException ignored) {
            }
        }
        return "";
    }

    private static long triggerAt(String planDate, String time) {
        String[] dateParts = planDate.split("-");
        String[] timeParts = time.trim().split(":");
        Calendar calendar = Calendar.getInstance();
        calendar.set(Calendar.YEAR, Integer.parseInt(dateParts[0]));
        calendar.set(Calendar.MONTH, Integer.parseInt(dateParts[1]) - 1);
        calendar.set(Calendar.DAY_OF_MONTH, Integer.parseInt(dateParts[2]));
        calendar.set(Calendar.HOUR_OF_DAY, Integer.parseInt(timeParts[0]));
        calendar.set(Calendar.MINUTE, Integer.parseInt(timeParts[1]));
        calendar.set(Calendar.SECOND, 0);
        calendar.set(Calendar.MILLISECOND, 0);
        return calendar.getTimeInMillis();
    }

    private static String todayIso() {
        return new SimpleDateFormat("yyyy-MM-dd", Locale.US).format(System.currentTimeMillis());
    }

    private static String formatIso(long millis) {
        return new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ssZ", Locale.US).format(millis);
    }

    static final class ImportResult {
        final boolean ok;
        final int alarmCount;
        final String planDate;
        final String rosterCode;
        final String message;
        final int variantCount;
        final int totalAlarmCount;

        ImportResult(boolean ok, int alarmCount, String planDate, String rosterCode, String message) {
            this(ok, alarmCount, planDate, rosterCode, message, 0, alarmCount);
        }

        ImportResult(
                boolean ok,
                int alarmCount,
                String planDate,
                String rosterCode,
                String message,
                int variantCount,
                int totalAlarmCount
        ) {
            this.ok = ok;
            this.alarmCount = alarmCount;
            this.planDate = planDate == null ? "" : planDate;
            this.rosterCode = rosterCode == null ? "" : rosterCode;
            this.message = message == null ? "" : message;
            this.variantCount = variantCount;
            this.totalAlarmCount = totalAlarmCount;
        }
    }

    private static final class ParsedScheduleGrid {
        final JSONArray alarms;
        final String planDate;
        final String rosterCode;

        ParsedScheduleGrid(JSONArray alarms, String planDate, String rosterCode) {
            this.alarms = alarms == null ? new JSONArray() : alarms;
            this.planDate = planDate == null ? "" : planDate;
            this.rosterCode = rosterCode == null ? "" : rosterCode;
        }
    }
}
