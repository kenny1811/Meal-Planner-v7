package com.example.oneshotalarm;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.graphics.Typeface;
import android.net.Uri;
import android.text.InputType;
import android.view.Gravity;
import android.widget.AdapterView;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.Spinner;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONArray;
import org.json.JSONObject;


/**
 * OnOffDuty tab：每日 On Duty / Off Duty Google Form 打卡（同電腦 OnOffDuty panel 對齊）。
 * 時間由電腦 API 計（更時表＋加班表），電話只做：睇 + 撳開預填 form + 記 log。
 * 冇 edit——臨時改時間喺 Google Form 入面改完先撳 Submit；正式改就改加班表。
 */
class OnOffDutyView {

    private static final int HTTP_READ_TIMEOUT_MS = 30000;

    private final Activity activity;
    private final LinearLayout container;
    private final PanelUi ui;
    private final Typeface regularTypeface;
    private final Typeface boldTypeface;
    private JSONObject plan;
    private boolean loading = false;
    private String lastError = "";
    private String viewDate = "";

    OnOffDutyView(Activity activity, LinearLayout container, Typeface regular, Typeface bold) {
        this.activity = activity;
        this.container = container;
        this.regularTypeface = regular != null ? regular : Typeface.DEFAULT;
        this.boldTypeface = bold != null ? bold : Typeface.DEFAULT_BOLD;
        this.ui = new PanelUi(activity, regular, bold);
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
                String body = ApiClient.request(activity, "GET", path, null, HTTP_READ_TIMEOUT_MS);
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
                String body = ApiClient.request(activity, "POST", "/api/onoffduty/log", payload.toString(), HTTP_READ_TIMEOUT_MS);
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

    /** 現場轉更：更碼本身係一個 Spinner pickup list，揀咗（確認後）即寫入更表——
     *  開工/收工時間、報平安更、日曆全部即時跟住重排。 */
    private Spinner buildCodeSpinner(String currentCode) {
        final java.util.List<String> codes = new java.util.ArrayList<>();
        JSONArray known = plan != null ? plan.optJSONArray("known_codes") : null;
        if (known != null) {
            for (int i = 0; i < known.length(); i++) {
                String c = known.optString(i, "").trim();
                if (!c.isEmpty()) {
                    codes.add(c);
                }
            }
        }
        if (!codes.contains("SB")) {
            codes.add("SB");
        }
        String shown = currentCode == null || currentCode.trim().isEmpty() ? "—" : currentCode.trim();
        if (!codes.contains(shown)) {
            codes.add(0, shown);
        }
        codes.add("Other code...");
        final int currentIndex = codes.indexOf(shown);

        Spinner spinner = new Spinner(activity);
        ArrayAdapter<String> adapter = new ArrayAdapter<String>(
                activity, android.R.layout.simple_spinner_item, codes) {
            @Override
            public android.view.View getView(int position, android.view.View convertView,
                    android.view.ViewGroup parent) {
                TextView view = (TextView) super.getView(position, convertView, parent);
                view.setTextSize(14);
                view.setTypeface(boldTypeface);
                view.setTextColor(0xFF0B3EA8);
                return view;
            }
        };
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);
        spinner.setAdapter(adapter);
        spinner.setSelection(currentIndex, false);
        spinner.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener() {
            @Override
            public void onItemSelected(AdapterView<?> parent, android.view.View view,
                    int position, long id) {
                if (position == currentIndex) {
                    return; // 初始 render／取消還原，唔當揀嘢
                }
                String picked = codes.get(position);
                spinner.setSelection(currentIndex); // 顯示先還原，等 API 成功 refresh 先變
                if ("Other code...".equals(picked)) {
                    promptCode(value -> confirmRosterCode(value));
                } else {
                    confirmRosterCode(picked);
                }
            }

            @Override
            public void onNothingSelected(AdapterView<?> parent) {
            }
        });
        return spinner;
    }

    private interface CodeCallback {
        void run(String code);
    }

    private void promptCode(CodeCallback callback) {
        LinearLayout box = new LinearLayout(activity);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setPadding(dp(16), dp(8), dp(16), 0);
        EditText input = new EditText(activity);
        input.setInputType(InputType.TYPE_CLASS_TEXT);
        input.setHint("e.g. WL01 / SH02 / AL03");
        box.addView(input);
        new AlertDialog.Builder(activity)
                .setTitle("Enter code")
                .setView(box)
                .setPositiveButton("OK", (d, w) -> {
                    String value = input.getText().toString().trim();
                    if (value.isEmpty()) {
                        Toast.makeText(activity, "更碼唔可以留空", Toast.LENGTH_SHORT).show();
                        return;
                    }
                    callback.run(value);
                })
                .setNegativeButton("Cancel", null)
                .show();
    }

    private void confirmRosterCode(String code) {
        new AlertDialog.Builder(activity)
                .setTitle("轉更 → " + code)
                .setMessage("寫入更表：開工/收工時間、報平安更、日曆全部跟住變。")
                .setPositiveButton("OK", (d, w) -> postRosterCode(code))
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
                String body = ApiClient.request(activity, "POST", "/api/onoffduty/roster-code", payload.toString(), HTTP_READ_TIMEOUT_MS);
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
                String body = ApiClient.request(activity, "POST", "/api/onoffduty/override", payload.toString(), HTTP_READ_TIMEOUT_MS);
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
                String body = ApiClient.request(activity, "POST", "/api/onoffduty/config", payload.toString(), HTTP_READ_TIMEOUT_MS);
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
                plan.optString("date_iso", "") + " (" + relationLabel + ")",
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

        // 第二行：30h chip + Semi ⇄ Auto segmented 掣（左=半自動出連結，右=夠鐘自動交）
        boolean autoSend = plan.optBoolean("auto_send", false);
        LinearLayout modeRow = row();
        modeRow.setPadding(dp(8), dp(4), dp(8), dp(2));
        modeRow.addView(ui.chip("30h day", 0xFF444441, 0xFFF1EFE8));
        LinearLayout modeSpacer = new LinearLayout(activity);
        modeRow.addView(modeSpacer, weighted(1f));
        LinearLayout segmented = row();
        segmented.setBackground(ui.roundedBg(0xFFFFFFFF, 99, 0xFFD8DEE6, 1));
        TextView semiText = textView("Semi", 11, autoSend ? 0xFF94A3B8 : 0xFF0C447C, !autoSend);
        semiText.setBackground(autoSend ? null : ui.roundedBg(0xFFE6F1FB, 99, 0, 0));
        semiText.setPadding(dp(12), dp(4), dp(12), dp(4));
        semiText.setOnClickListener(v -> {
            if (autoSend) {
                postConfig(false);
            }
        });
        segmented.addView(semiText);
        TextView autoText = textView("Auto", 11, autoSend ? 0xFF0C447C : 0xFF94A3B8, autoSend);
        autoText.setBackground(autoSend ? ui.roundedBg(0xFFE6F1FB, 99, 0, 0) : null);
        autoText.setPadding(dp(12), dp(4), dp(12), dp(4));
        autoText.setOnClickListener(v -> {
            if (!autoSend) {
                new AlertDialog.Builder(activity)
                        .setTitle("Turn full-auto on?")
                        .setMessage("On/Off Duty forms will be submitted automatically at the shift times.")
                        .setPositiveButton("OK", (d, w) -> postConfig(true))
                        .setNegativeButton("Cancel", null)
                        .show();
            }
        });
        segmented.addView(autoText);
        modeRow.addView(segmented);
        container.addView(modeRow);

        // 第三行：更碼摘要卡（Spinner pickup list，揀即轉更——寫入更表）
        String code = plan.optString("roster_code", "");
        String form = plan.optString("form", "");
        String formLabel = "vca".equals(form) ? "VCA form" : "other".equals(form) ? "其他 form" : "—";
        String post = plan.optString("post", "");
        LinearLayout codeCard = ui.card(0xFFF1F5F9, 0, 0);
        codeCard.setOrientation(LinearLayout.HORIZONTAL);
        codeCard.setGravity(Gravity.CENTER_VERTICAL);
        LinearLayout codeColumn = new LinearLayout(activity);
        codeColumn.setOrientation(LinearLayout.VERTICAL);
        LinearLayout codeLine = row();
        codeLine.addView(buildCodeSpinner(code), new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT));
        codeColumn.addView(codeLine);
        String codeSub = formLabel
                + (post.isEmpty() ? "" : " · " + post)
                + (plan.optString("staff_number", "").isEmpty()
                        ? "" : " · Staff " + plan.optString("staff_number", ""));
        TextView codeSubView = textView(codeSub, 11, 0xFF64748B, false);
        codeSubView.setPadding(0, 0, 0, 0);
        codeColumn.addView(codeSubView);
        codeCard.addView(codeColumn, weighted(1f));
        codeCard.addView(ui.chip(autoSend ? "auto at time" : "semi",
                autoSend ? 0xFF0C447C : 0xFF5F5E5A, autoSend ? 0xFFE6F1FB : 0xFFF1EFE8));
        container.addView(codeCard, ui.cardParams());
        container.addView(ui.noteStrip(
                "⚠ 揀code轉更會寫入更表——報更／餐單／日曆全部跟住變"),
                ui.cardParams());

        String note = plan.optString("note", "");
        JSONArray actions = plan.optJSONArray("actions");
        if (actions == null || actions.length() == 0) {
            LinearLayout emptyCard = ui.card(0xFFF8FAFC, 0xFFE2E8F0, 1);
            emptyCard.setGravity(Gravity.CENTER_HORIZONTAL);
            emptyCard.setPadding(dp(16), dp(24), dp(16), dp(24));
            TextView emptyIcon = textView("🛌", 30, 0xFF94A3B8, false);
            emptyIcon.setGravity(Gravity.CENTER_HORIZONTAL);
            emptyCard.addView(emptyIcon, fullWidth());
            TextView emptyTitle = textView("No report this day", 15, 0xFF0F172A, true);
            emptyTitle.setGravity(Gravity.CENTER_HORIZONTAL);
            emptyCard.addView(emptyTitle, fullWidth());
            TextView emptySub = textView(
                    note.isEmpty() ? code + " — no on/off duty forms." : note,
                    12, 0xFF64748B, false);
            emptySub.setGravity(Gravity.CENTER_HORIZONTAL);
            emptyCard.addView(emptySub, fullWidth());
            container.addView(emptyCard, ui.cardParams());
            return;
        }
        if (!note.isEmpty()) {
            container.addView(textView(note, 10, 0xFFB91C1C, false));
        }

        // 下一個未報嘅 action（今日先有）藍框 highlight
        int highlightIndex = -1;
        if (isToday) {
            for (int i = 0; i < actions.length(); i++) {
                JSONObject action = actions.optJSONObject(i);
                String status = action != null ? action.optString("status", "") : "";
                if (!"sent".equals(status) && !"opened".equals(status)) {
                    highlightIndex = i;
                    break;
                }
            }
        }
        for (int i = 0; i < actions.length(); i++) {
            JSONObject action = actions.optJSONObject(i);
            if (action != null) {
                container.addView(actionCard(action, i == highlightIndex), ui.cardParams());
            }
        }
    }

    private LinearLayout actionCard(JSONObject action, boolean highlight) {
        LinearLayout card = new LinearLayout(activity);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setBackground(highlight
                ? ui.roundedBg(0xFFF5FAFF, 12, 0xFF378ADD, 2)
                : ui.roundedBg(0xFFFFFFFF, 12, 0xFFD8DEE6, 1));
        card.setPadding(dp(12), dp(10), dp(12), dp(12));

        String status = action.optString("status", "");
        String loggedAt = action.optString("logged_at", "");
        String source = action.optString("log_source", "");

        // 卡頭：label + 狀態 chip
        LinearLayout headRow = row();
        TextView labelView = textView(action.optString("label", ""), 12,
                highlight ? 0xFF0C447C : 0xFF334155, true);
        labelView.setPadding(0, 0, 0, 0);
        headRow.addView(labelView, weighted(1f));
        if ("sent".equals(status) || "opened".equals(status)) {
            headRow.addView(ui.chip("✓ " + status + " " + formatLoggedAt(loggedAt) + " · " + source,
                    0xFF085041, 0xFFE1F5EE));
        } else if ("failed".equals(status)) {
            headRow.addView(ui.chip("✗ failed " + formatLoggedAt(loggedAt) + " · retrying",
                    0xFF791F1F, 0xFFFCEBEB));
        } else if ("missed".equals(status)) {
            headRow.addView(ui.chip("✗ missed — open the form yourself",
                    0xFF791F1F, 0xFFFCEBEB));
        } else if ("hold".equals(status)) {
            headRow.addView(ui.chip("⏸ holding — 真收工先撳 Send now",
                    0xFF9A5B00, 0xFFFAEEDA));
        } else {
            headRow.addView(textView("not reported yet", 11,
                    highlight ? 0xFF0C447C : 0xFF9AA1A9, highlight));
        }
        card.addView(headRow);

        String time = action.optString("time", "");
        String kind = action.optString("kind", "");
        boolean overridden = plan != null && plan.optBoolean(
                "start".equals(kind) ? "start_override" : "end_override", false);
        TextView timeView = textView(
                (time.isEmpty() ? "—" : time) + (overridden ? " *" : "") + "  ✎",
                26, overridden ? 0xFF9A5B00 : 0xFF0F172A, true);
        timeView.setPadding(0, dp(2), 0, 0);
        timeView.setOnClickListener(v -> showTimeEditDialog(action));
        card.addView(timeView);
        TextView hintView = textView(
                overridden ? "加班表 override · 撳時間改" : "撳時間現場改（寫入加班表）",
                9, overridden ? 0xFF9A5B00 : 0xFF9AA1A9, false);
        hintView.setPadding(0, 0, 0, 0);
        card.addView(hintView);

        // 掣行：Open form（＋收工卡今日加 Hold / Send now）
        String url = action.optString("url", "");
        boolean isToday = plan != null && "today".equals(plan.optString("relation", "today"));
        boolean showLate = "end".equals(kind) && isToday && !"sent".equals(status);
        LinearLayout buttonRow = row();
        boolean hasButton = false;
        if (!url.isEmpty()) {
            Button open = ui.outlineButton("Open form ↗", 0xFF0C447C, 0xFF378ADD);
            open.setOnClickListener(v -> openForm(action));
            buttonRow.addView(open, new LinearLayout.LayoutParams(0, dp(38), showLate ? 1.2f : 1f));
            hasButton = true;
        }
        if (showLate) {
            boolean holding = "hold".equals(status);
            Button holdButton = ui.outlineButton(holding ? "Cancel hold" : "Hold",
                    0xFF334155, 0xFFD8DEE6);
            holdButton.setOnClickListener(v -> postLateOff(holding ? "release" : "hold", ""));
            LinearLayout.LayoutParams holdParams = new LinearLayout.LayoutParams(0, dp(38), 1f);
            holdParams.setMargins(dp(6), 0, 0, 0);
            buttonRow.addView(holdButton, holdParams);
            Button sendButton = ui.outlineButton("Send now", 0xFFA32D2D, 0xFFF0B9B9);
            sendButton.setOnClickListener(v -> showLateSendDialog());
            LinearLayout.LayoutParams sendParams = new LinearLayout.LayoutParams(0, dp(38), 1f);
            sendParams.setMargins(dp(6), 0, 0, 0);
            buttonRow.addView(sendButton, sendParams);
            hasButton = true;
        }
        if (hasButton) {
            LinearLayout.LayoutParams rowParams = fullWidth();
            rowParams.setMargins(0, dp(8), 0, 0);
            card.addView(buttonRow, rowParams);
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
                String body = ApiClient.request(activity, "POST", "/api/onoffduty/lateoff", payload.toString(), HTTP_READ_TIMEOUT_MS);
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


    // ---- 共用 UI 工廠：薄 delegate 落 PanelUi（styling 常數得嗰邊一份） ----

    private TextView textView(String text, int sizeSp, int color, boolean bold) {
        return ui.textView(text, sizeSp, color, bold);
    }

    private LinearLayout row() {
        return ui.row();
    }

    private Button actionButton(String label) {
        return ui.actionButton(label);
    }

    private LinearLayout.LayoutParams buttonParams() {
        return ui.buttonParams();
    }

    private LinearLayout.LayoutParams weighted(float weight) {
        return ui.weighted(weight);
    }

    private LinearLayout.LayoutParams fullWidth() {
        return ui.fullWidth();
    }

    private int dp(int value) {
        return ui.dp(value);
    }
}
