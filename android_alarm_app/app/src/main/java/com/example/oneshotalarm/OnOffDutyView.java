package com.example.oneshotalarm;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.graphics.Typeface;
import android.net.Uri;
import android.text.InputType;
import android.view.Gravity;
import android.widget.ArrayAdapter;
import android.widget.AutoCompleteTextView;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.Switch;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

/**
 * OnOffDuty tab：每日 On Duty / Off Duty Google Form 打卡（同電腦 OnOffDuty panel 對齊）。
 * 時間由電腦 API 計（更時表＋加班表），電話只做：睇 + 撳開預填 form + 記 log。
 * 冇 edit——臨時改時間喺 Google Form 入面改完先撳 Submit；正式改就改加班表。
 */
class OnOffDutyView {

    private static final int HTTP_CONNECT_TIMEOUT_MS = 2500;
    private static final int HTTP_READ_TIMEOUT_MS = 30000;

    private final Activity activity;
    private final LinearLayout container;
    private final Typeface regularTypeface;
    private final Typeface boldTypeface;
    private JSONObject plan;
    private boolean loading = false;
    private String lastError = "";
    private int serverIndex = 0;
    private String viewDate = "";

    OnOffDutyView(Activity activity, LinearLayout container, Typeface regular, Typeface bold) {
        this.activity = activity;
        this.container = container;
        this.regularTypeface = regular != null ? regular : Typeface.DEFAULT;
        this.boldTypeface = bold != null ? bold : Typeface.DEFAULT_BOLD;
    }

    // ---------------------------------------------------------------- 網絡

    void refresh() {
        if (loading) {
            return;
        }
        loading = true;
        lastError = "";
        renderLoading();
        final String path = "/api/onoffduty/plan"
                + (viewDate.isEmpty() ? "" : "?date_iso=" + viewDate);
        new Thread(() -> {
            try {
                String body = requestWithFailover("GET", path, null);
                JSONObject parsed = new JSONObject(body);
                activity.runOnUiThread(() -> {
                    plan = parsed;
                    loading = false;
                    render();
                });
            } catch (Exception e) {
                activity.runOnUiThread(() -> {
                    loading = false;
                    lastError = "Cannot reach PC: " + e.getMessage();
                    render();
                });
            }
        }, "onoffduty-fetch").start();
    }

    void shiftDate(int deltaDays) {
        if (plan == null || loading) {
            return;
        }
        String base = plan.optString("date_iso", "");
        if (base.length() != 10) {
            return;
        }
        try {
            java.util.Calendar cal = java.util.Calendar.getInstance();
            cal.set(Integer.parseInt(base.substring(0, 4)),
                    Integer.parseInt(base.substring(5, 7)) - 1,
                    Integer.parseInt(base.substring(8, 10)), 12, 0, 0);
            cal.add(java.util.Calendar.DAY_OF_MONTH, deltaDays);
            String iso = String.format(java.util.Locale.US, "%04d-%02d-%02d",
                    cal.get(java.util.Calendar.YEAR),
                    cal.get(java.util.Calendar.MONTH) + 1,
                    cal.get(java.util.Calendar.DAY_OF_MONTH));
            viewDate = iso.equals(plan.optString("today_iso", "")) ? "" : iso;
            refresh();
        } catch (Exception ignored) {
        }
    }

    /** 撳 Open form：背後記 log（fire-and-forget），即刻開瀏覽器去預填 form。 */
    private void openForm(JSONObject action) {
        String url = action.optString("url", "");
        String kind = action.optString("kind", "");
        if (url.isEmpty()) {
            return;
        }
        JSONObject payload = new JSONObject();
        try {
            payload.put("kind", kind);
            payload.put("status", "opened");
            payload.put("source", "phone");
            if (!viewDate.isEmpty()) {
                payload.put("date_iso", viewDate);
            }
        } catch (Exception ignored) {
        }
        new Thread(() -> {
            try {
                String body = requestWithFailover("POST", "/api/onoffduty/log", payload.toString());
                JSONObject parsed = new JSONObject(body);
                activity.runOnUiThread(() -> {
                    plan = parsed;
                    render();
                });
            } catch (Exception ignored) {
                // log 失敗唔阻開 form；下次 refresh 會見返真狀態。
            }
        }, "onoffduty-log").start();
        try {
            activity.startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url)));
        } catch (Exception e) {
            Toast.makeText(activity, "Cannot open browser: " + e.getMessage(), Toast.LENGTH_LONG).show();
        }
    }

    /** 現場改開工/收工時間：寫入加班表（全系統一致），留空＝還原跟更時表。 */
    private void showTimeEditDialog(JSONObject action) {
        String kind = action.optString("kind", "");
        String label = action.optString("label", "");
        if (kind.isEmpty()) {
            return;
        }
        LinearLayout box = new LinearLayout(activity);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setPadding(dp(16), dp(8), dp(16), 0);
        EditText timeInput = new EditText(activity);
        timeInput.setInputType(InputType.TYPE_CLASS_DATETIME | InputType.TYPE_DATETIME_VARIATION_TIME);
        timeInput.setHint("21:30 / 2130");
        timeInput.setText(action.optString("time", ""));
        timeInput.setSelectAllOnFocus(true);
        box.addView(timeInput);
        EditText noteInput = new EditText(activity);
        noteInput.setInputType(InputType.TYPE_CLASS_TEXT);
        noteInput.setHint("備註（加班表，可留空）");
        box.addView(noteInput);
        new AlertDialog.Builder(activity)
                .setTitle(label + " — 現場改時間（寫入加班表）")
                .setView(box)
                .setPositiveButton("OK", (d, w) -> {
                    String value = timeInput.getText().toString().trim();
                    if (value.isEmpty()) {
                        Toast.makeText(activity, "要還原請用「還原」掣", Toast.LENGTH_SHORT).show();
                        return;
                    }
                    postOverride(kind, value, noteInput.getText().toString().trim());
                })
                .setNeutralButton("還原跟更時表", (d, w) -> postOverride(kind, "", ""))
                .setNegativeButton("Cancel", null)
                .show();
    }

    /** 現場轉更：改當日更碼（寫入更表）——開工/收工時間、報平安更、日曆全部即時跟住重排。 */
    private void showCodeEditDialog() {
        if (plan == null || loading) {
            return;
        }
        LinearLayout box = new LinearLayout(activity);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setPadding(dp(16), dp(8), dp(16), 0);
        AutoCompleteTextView codeInput = new AutoCompleteTextView(activity);
        codeInput.setInputType(InputType.TYPE_CLASS_TEXT);
        codeInput.setHint("e.g. TSB / IFCA1 / SB");
        codeInput.setText(plan.optString("roster_code", ""));
        codeInput.setSelectAllOnFocus(true);
        JSONArray known = plan.optJSONArray("known_codes");
        if (known != null && known.length() > 0) {
            String[] codes = new String[known.length()];
            for (int i = 0; i < known.length(); i++) {
                codes[i] = known.optString(i, "");
            }
            codeInput.setAdapter(new ArrayAdapter<>(
                    activity, android.R.layout.simple_dropdown_item_1line, codes));
            codeInput.setThreshold(1);
        }
        box.addView(codeInput);
        new AlertDialog.Builder(activity)
                .setTitle("轉更 — 改 " + plan.optString("date_iso", "") + " 更碼（寫入更表）")
                .setMessage("開工/收工時間、報平安更、日曆會即時跟新更碼重排。")
                .setView(box)
                .setPositiveButton("OK", (d, w) -> {
                    String value = codeInput.getText().toString().trim();
                    if (value.isEmpty()) {
                        Toast.makeText(activity, "更碼唔可以留空", Toast.LENGTH_SHORT).show();
                        return;
                    }
                    postRosterCode(value);
                })
                .setNegativeButton("Cancel", null)
                .show();
    }

    private void postRosterCode(String code) {
        if (loading || plan == null) {
            return;
        }
        loading = true;
        JSONObject payload = new JSONObject();
        try {
            payload.put("date_iso", plan.optString("date_iso", ""));
            payload.put("code", code);
        } catch (Exception ignored) {
        }
        new Thread(() -> {
            try {
                String body = requestWithFailover("POST", "/api/onoffduty/roster-code", payload.toString());
                JSONObject parsed = new JSONObject(body);
                activity.runOnUiThread(() -> {
                    plan = parsed;
                    loading = false;
                    render();
                });
            } catch (Exception e) {
                activity.runOnUiThread(() -> {
                    loading = false;
                    lastError = "Code change failed: " + e.getMessage();
                    render();
                });
            }
        }, "onoffduty-code").start();
    }

    private void postOverride(String kind, String timeValue, String note) {
        if (loading || plan == null) {
            return;
        }
        loading = true;
        JSONObject payload = new JSONObject();
        try {
            payload.put("date_iso", plan.optString("date_iso", ""));
            payload.put("start".equals(kind) ? "start" : "end", timeValue);
            if (!note.isEmpty()) {
                payload.put("note", note);
            }
        } catch (Exception ignored) {
        }
        new Thread(() -> {
            try {
                String body = requestWithFailover("POST", "/api/onoffduty/override", payload.toString());
                JSONObject parsed = new JSONObject(body);
                activity.runOnUiThread(() -> {
                    plan = parsed;
                    loading = false;
                    render();
                });
            } catch (Exception e) {
                activity.runOnUiThread(() -> {
                    loading = false;
                    lastError = "Override failed: " + e.getMessage();
                    render();
                });
            }
        }, "onoffduty-override").start();
    }

    /** Semi ⇄ Auto：寫入電腦 config，成功後用 API 回傳嘅 plan 重新 render。 */
    private void postConfig(boolean autoSend) {
        if (loading) {
            return;
        }
        loading = true;
        JSONObject payload = new JSONObject();
        try {
            payload.put("auto_send", autoSend);
        } catch (Exception ignored) {
        }
        new Thread(() -> {
            try {
                String body = requestWithFailover("POST", "/api/onoffduty/config", payload.toString());
                JSONObject parsed = new JSONObject(body);
                activity.runOnUiThread(() -> {
                    plan = parsed;
                    loading = false;
                    render();
                });
            } catch (Exception e) {
                activity.runOnUiThread(() -> {
                    loading = false;
                    lastError = "Config failed: " + e.getMessage();
                    render();
                });
            }
        }, "onoffduty-config").start();
    }

    /** 逐個 server 試（LAN → Meshnet），成功嗰個記住做首選。 */
    private String requestWithFailover(String method, String path, String jsonBody) throws Exception {
        String[] candidates = AlarmStore.getAutoSyncServerCandidates(activity);
        Exception lastException = null;
        for (int i = 0; i < candidates.length; i++) {
            String base = candidates[(serverIndex + i) % candidates.length];
            try {
                String body = "POST".equals(method)
                        ? httpPost(base + path, jsonBody)
                        : httpGet(base + path);
                serverIndex = (serverIndex + i) % candidates.length;
                return body;
            } catch (Exception e) {
                lastException = e;
            }
        }
        throw lastException != null ? lastException : new Exception("no server candidates");
    }

    // ---------------------------------------------------------------- render

    private void renderLoading() {
        container.removeAllViews();
        container.addView(textView("Loading OnOffDuty...", 12, 0xFF64748B, false));
    }

    private void render() {
        container.removeAllViews();
        if (!lastError.isEmpty()) {
            TextView err = textView(lastError, 11, 0xFFB91C1C, false);
            err.setPadding(dp(8), dp(4), dp(8), dp(4));
            container.addView(err);
        }
        if (plan == null) {
            Button retry = actionButton("Retry");
            retry.setOnClickListener(v -> refresh());
            container.addView(retry, buttonParams());
            return;
        }

        String relation = plan.optString("relation", "today");
        boolean isToday = "today".equals(relation);
        boolean isPast = "past".equals(relation);

        // 第一行：日期（左右撥動轉日）
        LinearLayout dateRow = row();
        String relationLabel = isToday ? "Today" : isPast ? "Past" : "Future";
        TextView dateLabel = textView(
                plan.optString("date_iso", "") + " (" + relationLabel + ") · 30h day",
                13, 0xFF0F172A, true);
        dateLabel.setGravity(Gravity.CENTER_VERTICAL);
        dateRow.addView(dateLabel, weighted(1f));
        if (!isToday) {
            Button today = actionButton("Today");
            today.setTextColor(0xFF0B3EA8);
            today.setOnClickListener(v -> {
                viewDate = "";
                refresh();
            });
            dateRow.addView(today, buttonParams());
        }
        Button refreshButton = actionButton("↻");
        refreshButton.setOnClickListener(v -> refresh());
        dateRow.addView(refreshButton, new LinearLayout.LayoutParams(dp(44), dp(30)));
        container.addView(dateRow);

        // 第二行：Semi ⇄ Auto 掣（左=半自動出連結，右=夠鐘自動交）
        boolean autoSend = plan.optBoolean("auto_send", false);
        LinearLayout modeRow = row();
        TextView modeLabel = textView(
                autoSend ? "Auto: submits at the shift time" : "Semi: open link, submit yourself",
                11, autoSend ? 0xFF0B3EA8 : 0xFF64748B, true);
        modeLabel.setGravity(Gravity.CENTER_VERTICAL);
        modeRow.addView(modeLabel, weighted(1f));
        TextView semiText = textView("Semi", 10, autoSend ? 0xFF9AA1A9 : 0xFF0B3EA8, !autoSend);
        modeRow.addView(semiText, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT));
        Switch autoSwitch = new Switch(activity);
        autoSwitch.setChecked(autoSend);
        autoSwitch.setOnClickListener(v -> {
            autoSwitch.setChecked(autoSend); // 等 API 成功先反映
            if (autoSend) {
                postConfig(false);
            } else {
                new AlertDialog.Builder(activity)
                        .setTitle("Turn full-auto on?")
                        .setMessage("On/Off Duty forms will be submitted automatically at the shift times.")
                        .setPositiveButton("OK", (d, w) -> postConfig(true))
                        .setNegativeButton("Cancel", null)
                        .show();
            }
        });
        modeRow.addView(autoSwitch, buttonParams());
        TextView autoText = textView("Auto", 10, autoSend ? 0xFF0B3EA8 : 0xFF9AA1A9, autoSend);
        modeRow.addView(autoText, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT));
        container.addView(modeRow);

        // 第三行：更碼 / form / Post（撳更碼可以現場轉更——寫入更表）
        String code = plan.optString("roster_code", "");
        String form = plan.optString("form", "");
        String formLabel = "vca".equals(form) ? "VCA form" : "other".equals(form) ? "其他 form" : "—";
        String post = plan.optString("post", "");
        TextView codeLine = textView(
                "Code " + (code.isEmpty() ? "—" : code) + " · " + formLabel + "  ✎",
                12, 0xFF0F172A, true);
        codeLine.setOnClickListener(v -> showCodeEditDialog());
        container.addView(codeLine);
        if (!post.isEmpty()) {
            container.addView(textView(post + " · Staff " + plan.optString("staff_number", ""),
                    11, 0xFF374151, false));
        }

        String note = plan.optString("note", "");
        JSONArray actions = plan.optJSONArray("actions");
        if (actions == null || actions.length() == 0) {
            container.addView(textView(note.isEmpty() ? "No report this day" : note, 12, 0xFF64748B, false));
            return;
        }
        if (!note.isEmpty()) {
            container.addView(textView(note, 10, 0xFFB91C1C, false));
        }

        for (int i = 0; i < actions.length(); i++) {
            JSONObject action = actions.optJSONObject(i);
            if (action != null) {
                container.addView(actionCard(action));
            }
        }
    }

    private LinearLayout actionCard(JSONObject action) {
        LinearLayout card = new LinearLayout(activity);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setBackgroundColor(0xFFF8FAFC);
        card.setPadding(dp(10), dp(8), dp(10), dp(10));
        LinearLayout.LayoutParams cardParams = fullWidth();
        cardParams.setMargins(dp(8), dp(6), dp(8), 0);
        card.setLayoutParams(cardParams);

        card.addView(textView(action.optString("label", ""), 11, 0xFF64748B, true));
        String time = action.optString("time", "");
        String kind = action.optString("kind", "");
        boolean overridden = plan != null && plan.optBoolean(
                "start".equals(kind) ? "start_override" : "end_override", false);
        TextView timeView = textView(
                (time.isEmpty() ? "—" : time) + (overridden ? " *" : "") + "  ✎",
                22, overridden ? 0xFF9A5B00 : 0xFF0F172A, true);
        timeView.setOnClickListener(v -> showTimeEditDialog(action));
        card.addView(timeView);
        card.addView(textView(
                overridden ? "加班表 override · 撳時間改" : "撳時間現場改（寫入加班表）",
                9, 0xFF9AA1A9, false));

        String status = action.optString("status", "");
        String loggedAt = action.optString("logged_at", "");
        String source = action.optString("log_source", "");
        String statusText;
        int statusColor;
        if ("sent".equals(status) || "opened".equals(status)) {
            statusText = "✓ " + status + " " + formatLoggedAt(loggedAt) + " · " + source;
            statusColor = 0xFF166534;
        } else if ("failed".equals(status)) {
            statusText = "✗ failed " + formatLoggedAt(loggedAt) + " · retrying";
            statusColor = 0xFFB91C1C;
        } else if ("missed".equals(status)) {
            statusText = "✗ missed — open the form yourself";
            statusColor = 0xFFB91C1C;
        } else if ("hold".equals(status)) {
            statusText = "⏸ holding — 真收工先撳齊發";
            statusColor = 0xFF9A5B00;
        } else {
            statusText = "not reported yet";
            statusColor = 0xFF9AA1A9;
        }
        card.addView(textView(statusText, 10, statusColor, false));

        String url = action.optString("url", "");
        if (!url.isEmpty()) {
            Button open = actionButton("Open form ↗");
            open.setTypeface(boldTypeface);
            open.setTextColor(0xFF0B3EA8);
            open.setOnClickListener(v -> openForm(action));
            LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT, dp(38));
            params.setMargins(0, dp(6), 0, 0);
            card.addView(open, params);
        }

        // 收工卡（今日）：遲收工 Hold（兩邊一齊 hold）＋ 真收工齊發。
        boolean isToday = plan != null && "today".equals(plan.optString("relation", "today"));
        if ("end".equals(kind) && isToday && !"sent".equals(status)) {
            boolean holding = "hold".equals(status);
            LinearLayout lateRow = row();
            Button holdButton = actionButton(holding ? "取消 Hold" : "遲收工 Hold");
            holdButton.setOnClickListener(v -> postLateOff(holding ? "release" : "hold", ""));
            lateRow.addView(holdButton, weighted(1f));
            Button sendButton = actionButton("真收工 · 齊發");
            sendButton.setTypeface(boldTypeface);
            sendButton.setTextColor(0xFFB91C1C);
            sendButton.setOnClickListener(v -> showLateSendDialog());
            lateRow.addView(sendButton, weighted(1f));
            LinearLayout.LayoutParams lateParams = fullWidth();
            lateParams.setMargins(0, dp(4), 0, 0);
            card.addView(lateRow, lateParams);
        }
        return card;
    }

    /** 真收工齊發：以而家時間 交 form + 出 WhatsApp；遲 ≥15 分鐘先寫加班表。 */
    private void showLateSendDialog() {
        LinearLayout box = new LinearLayout(activity);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setPadding(dp(16), dp(8), dp(16), 0);
        EditText noteInput = new EditText(activity);
        noteInput.setInputType(InputType.TYPE_CLASS_TEXT);
        noteInput.setHint("加班表備註（留空＝現場真收工）");
        box.addView(noteInput);
        new AlertDialog.Builder(activity)
                .setTitle("以而家時間齊發？")
                .setMessage("· 交 Off Duty form（實際時間）\n· 出 WhatsApp 報收工/報平安更\n· 超出更時表窗口（早開工/遲收工）兼 總工時>10.25h 先寫加班表")
                .setView(box)
                .setPositiveButton("齊發", (d, w) -> postLateOff("send_now", noteInput.getText().toString().trim()))
                .setNegativeButton("Cancel", null)
                .show();
    }

    private void postLateOff(String actionName, String note) {
        if (loading) {
            return;
        }
        loading = true;
        JSONObject payload = new JSONObject();
        try {
            payload.put("action", actionName);
            if (!note.isEmpty()) {
                payload.put("note", note);
            }
        } catch (Exception ignored) {
        }
        new Thread(() -> {
            try {
                String body = requestWithFailover("POST", "/api/onoffduty/lateoff", payload.toString());
                JSONObject parsed = new JSONObject(body);
                activity.runOnUiThread(() -> {
                    plan = parsed;
                    loading = false;
                    render();
                    JSONObject result = parsed.optJSONObject("lateoff_result");
                    if (result != null) {
                        String message = "齊發完成 " + result.optString("actual", "")
                                + "\nForm: sent\nWhatsApp: " + result.optString("whatsapp", "?")
                                + "\n加班表: " + (result.optBoolean("overtime_written", false) ? "已寫入" : "未達加班條件，冇寫");
                        new AlertDialog.Builder(activity).setMessage(message).setPositiveButton("OK", null).show();
                    }
                });
            } catch (Exception e) {
                activity.runOnUiThread(() -> {
                    loading = false;
                    lastError = "Late-off failed: " + e.getMessage();
                    render();
                });
            }
        }, "onoffduty-lateoff").start();
    }

    private static String formatLoggedAt(String iso) {
        if (iso.length() >= 16 && iso.charAt(10) == 'T') {
            return iso.substring(8, 10) + "/" + iso.substring(5, 7) + " " + iso.substring(11, 16);
        }
        return iso;
    }

    // ---------------------------------------------------------------- helpers

    private TextView textView(String text, int sizeSp, int color, boolean bold) {
        TextView view = new TextView(activity);
        view.setText(text);
        view.setTextSize(sizeSp);
        view.setTextColor(color);
        view.setTypeface(bold ? boldTypeface : regularTypeface);
        view.setPadding(dp(8), dp(2), dp(8), dp(2));
        return view;
    }

    private LinearLayout row() {
        LinearLayout layout = new LinearLayout(activity);
        layout.setOrientation(LinearLayout.HORIZONTAL);
        layout.setGravity(Gravity.CENTER_VERTICAL);
        return layout;
    }

    private Button actionButton(String label) {
        Button button = new Button(activity);
        button.setText(label);
        button.setAllCaps(false);
        button.setTypeface(regularTypeface);
        button.setTextSize(11);
        button.setMinHeight(dp(30));
        button.setMinimumHeight(dp(30));
        button.setMinWidth(0);
        button.setMinimumWidth(0);
        button.setPadding(dp(6), 0, dp(6), 0);
        return button;
    }

    private LinearLayout.LayoutParams buttonParams() {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT, dp(30));
        params.setMargins(dp(3), 0, 0, 0);
        return params;
    }

    private LinearLayout.LayoutParams weighted(float weight) {
        return new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, weight);
    }

    private LinearLayout.LayoutParams fullWidth() {
        return new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
    }

    private int dp(int value) {
        return Math.round(activity.getResources().getDisplayMetrics().density * value);
    }

    // ---------------------------------------------------------------- HTTP

    private static String httpGet(String endpoint) throws Exception {
        HttpURLConnection conn = null;
        try {
            conn = (HttpURLConnection) new URL(endpoint).openConnection();
            conn.setRequestMethod("GET");
            conn.setConnectTimeout(HTTP_CONNECT_TIMEOUT_MS);
            conn.setReadTimeout(HTTP_READ_TIMEOUT_MS);
            return readResponse(conn, endpoint);
        } finally {
            if (conn != null) {
                conn.disconnect();
            }
        }
    }

    private static String httpPost(String endpoint, String jsonBody) throws Exception {
        HttpURLConnection conn = null;
        try {
            conn = (HttpURLConnection) new URL(endpoint).openConnection();
            conn.setRequestMethod("POST");
            conn.setConnectTimeout(HTTP_CONNECT_TIMEOUT_MS);
            conn.setReadTimeout(HTTP_READ_TIMEOUT_MS);
            conn.setDoOutput(true);
            conn.setRequestProperty("Content-Type", "application/json; charset=utf-8");
            byte[] bytes = jsonBody.getBytes(StandardCharsets.UTF_8);
            conn.setFixedLengthStreamingMode(bytes.length);
            try (OutputStream out = conn.getOutputStream()) {
                out.write(bytes);
            }
            return readResponse(conn, endpoint);
        } finally {
            if (conn != null) {
                conn.disconnect();
            }
        }
    }

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

    private static String readStream(InputStream stream) throws Exception {
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
