package com.example.oneshotalarm;

import android.app.Activity;
import android.app.AlertDialog;
import android.graphics.Typeface;
import android.text.InputType;
import android.view.Gravity;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Calendar;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 報更 tab：功能同電腦端 Duty Report panel 對齊（日期導航／auto-send 掣／
 * 逐項改時間・改group・skip・即發／override／對照表+template 編輯），手機排版。
 * 只透過電腦 API 讀寫報更 overlay；唔郁本機更表／鬧鐘。
 */
class DutyReportView {

    private static final int HTTP_READ_TIMEOUT_MS = 90000;

    private final Activity activity;
    private final LinearLayout container;
    private final PanelUi ui;
    private final Typeface regularTypeface;
    private final Typeface boldTypeface;
    private JSONObject plan;
    private boolean loading = false;
    private String lastError = "";
    private String viewDate = "";
    private boolean mappingExpanded = false;
    private boolean logExpanded = false;

    DutyReportView(Activity activity, LinearLayout container, Typeface regular, Typeface bold) {
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
        final String path = "/api/duty-report/plan"
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
        }, "duty-report-fetch").start();
    }

    private void postJson(String path, JSONObject payload, String busyText) {
        if (loading) {
            return;
        }
        loading = true;
        lastError = "";
        Toast.makeText(activity, busyText, Toast.LENGTH_SHORT).show();
        new Thread(() -> {
            try {
                String body = ApiClient.request(activity, "POST", path, payload.toString(), HTTP_READ_TIMEOUT_MS);
                JSONObject parsed = new JSONObject(body);
                activity.runOnUiThread(() -> {
                    plan = parsed;
                    loading = false;
                    render();
                });
            } catch (Exception e) {
                activity.runOnUiThread(() -> {
                    loading = false;
                    lastError = "Action failed: " + e.getMessage();
                    render();
                });
            }
        }, "duty-report-post").start();
    }

    private JSONObject overridePayload() {
        JSONObject payload = new JSONObject();
        try {
            payload.put("source", "phone");
            if (!viewDate.isEmpty()) {
                payload.put("date_iso", viewDate);
            }
        } catch (Exception ignored) {
        }
        return payload;
    }

    private void postOverride(JSONObject payload, String busyText) {
        postJson("/api/duty-report/override", payload, busyText);
    }

    private void postConfig(JSONObject payload, String busyText) {
        postJson("/api/duty-report/config", payload, busyText);
    }

    // ---------------------------------------------------------------- render

    private void renderLoading() {
        container.removeAllViews();
        container.addView(textView("Loading duty report...", 12, 0xFF64748B, false));
    }

    private String relation() {
        return plan != null ? plan.optString("relation", "today") : "today";
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

        String relation = relation();
        boolean isToday = "today".equals(relation);
        boolean isPast = "past".equals(relation);
        JSONObject health = plan.optJSONObject("health");
        boolean cdpOk = health != null && health.optBoolean("cdp", false);
        boolean waOk = health != null && health.optBoolean("whatsapp", false);
        boolean autoSend = plan.optBoolean("auto_send", false);
        String mode = plan.optString("mode", "auto");

        // 第一行：日期（左右撥動轉日，由 MainActivity dispatchTouchEvent 處理）
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

        // 第二行：健康 chip + auto-send pill
        LinearLayout chipRow = row();
        chipRow.setPadding(dp(8), dp(4), dp(8), dp(2));
        chipRow.addView(ui.chip(cdpOk ? "✓ CDP" : "✗ CDP",
                cdpOk ? 0xFF085041 : 0xFF791F1F, cdpOk ? 0xFFE1F5EE : 0xFFFCEBEB));
        chipRow.addView(ui.chip(waOk ? "✓ WhatsApp" : "✗ WhatsApp",
                waOk ? 0xFF085041 : 0xFF791F1F, waOk ? 0xFFE1F5EE : 0xFFFCEBEB), ui.chipParams());
        LinearLayout chipSpacer = new LinearLayout(activity);
        chipRow.addView(chipSpacer, weighted(1f));
        Button autoButton = actionButton("Auto-send " + (autoSend ? "ON" : "OFF"));
        autoButton.setTextColor(autoSend ? 0xFF0C447C : 0xFF64748B);
        autoButton.setTypeface(boldTypeface);
        autoButton.setBackground(ui.roundedBg(autoSend ? 0xFFE6F1FB : 0xFFF1F5F9, 99, 0, 0));
        autoButton.setOnClickListener(v -> new AlertDialog.Builder(activity)
                .setTitle(autoSend ? "Turn auto-send off?" : "Turn auto-send on?")
                .setMessage(autoSend ? "Only manual send will work while off." : "Reports are sent via WhatsApp automatically at each time.")
                .setPositiveButton("OK", (d, w) -> {
                    JSONObject payload = new JSONObject();
                    try {
                        payload.put("auto_send", !autoSend);
                    } catch (Exception ignored) {
                    }
                    postConfig(payload, "Updating...");
                })
                .setNegativeButton("Cancel", null)
                .show());
        chipRow.addView(autoButton, buttonParams());
        container.addView(chipRow);

        // 第三行：摘要卡（code + 來源/next + sent 進度）
        String segText = segmentsText();
        String source = plan.optString("source", "");
        String sourceLabel = "override".equals(source) ? "override" : "roster".equals(source) ? "roster" : "—";
        String nextTime = plan.optString("next_time", "");
        int sentCount = plan.optInt("sent_count", 0);
        int totalCount = plan.optInt("total_count", 0);

        LinearLayout summaryCard = ui.card(0xFFF1F5F9, 0, 0);
        summaryCard.setOrientation(LinearLayout.HORIZONTAL);
        summaryCard.setGravity(Gravity.CENTER_VERTICAL);
        LinearLayout summaryLeft = new LinearLayout(activity);
        summaryLeft.setOrientation(LinearLayout.VERTICAL);
        TextView codeText = textView(segText.isEmpty() ? "—" : segText, 16, 0xFF0F172A, true);
        codeText.setPadding(0, 0, 0, 0);
        summaryLeft.addView(codeText);
        String subLine = sourceLabel
                + ("stop".equals(mode) ? " · stopped" : "")
                + (nextTime.isEmpty() ? "" : " · next " + nextTime);
        TextView subText = textView(subLine, 11, "stop".equals(mode) ? 0xFFB91C1C : 0xFF64748B, false);
        subText.setPadding(0, 0, 0, 0);
        summaryLeft.addView(subText);
        summaryCard.addView(summaryLeft, weighted(1f));

        LinearLayout summaryRight = new LinearLayout(activity);
        summaryRight.setOrientation(LinearLayout.VERTICAL);
        summaryRight.setGravity(Gravity.END);
        TextView sentText = textView(sentCount + "/" + totalCount, 16, 0xFF0F172A, true);
        sentText.setPadding(0, 0, 0, 0);
        sentText.setGravity(Gravity.END);
        summaryRight.addView(sentText);
        TextView sentLabel = textView("sent", 11, 0xFF64748B, false);
        sentLabel.setPadding(0, 0, 0, 0);
        sentLabel.setGravity(Gravity.END);
        summaryRight.addView(sentLabel);
        summaryCard.addView(summaryRight, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT));

        LinearLayout progressTrack = new LinearLayout(activity);
        progressTrack.setOrientation(LinearLayout.HORIZONTAL);
        progressTrack.setBackground(ui.roundedBg(0xFFD8DEE6, 3, 0, 0));
        int doneWeight = totalCount > 0 ? sentCount : 0;
        int restWeight = totalCount > 0 ? totalCount - sentCount : 1;
        android.view.View doneBar = new android.view.View(activity);
        doneBar.setBackground(ui.roundedBg(0xFF1D9E75, 3, 0, 0));
        progressTrack.addView(doneBar, new LinearLayout.LayoutParams(0, dp(6), doneWeight));
        android.view.View restBar = new android.view.View(activity);
        progressTrack.addView(restBar, new LinearLayout.LayoutParams(0, dp(6), restWeight));
        LinearLayout.LayoutParams trackParams = new LinearLayout.LayoutParams(dp(44), dp(6));
        trackParams.setMargins(dp(10), 0, 0, 0);
        summaryCard.addView(progressTrack, trackParams);
        container.addView(summaryCard, ui.cardParams());

        String dataError = plan.optString("data_error", "");
        if (!dataError.isEmpty()) {
            container.addView(textView(dataError, 10, 0xFFB91C1C, false));
        }

        // slot 列表
        JSONArray slots = plan.optJSONArray("slots");
        if (slots == null || slots.length() == 0) {
            LinearLayout emptyCard = ui.card(0xFFF8FAFC, 0xFFE2E8F0, 1);
            emptyCard.setGravity(Gravity.CENTER_HORIZONTAL);
            emptyCard.setPadding(dp(16), dp(24), dp(16), dp(24));
            TextView emptyIcon = textView("🛡", 30, 0xFF94A3B8, false);
            emptyIcon.setGravity(Gravity.CENTER_HORIZONTAL);
            emptyCard.addView(emptyIcon, fullWidth());
            TextView emptyTitle = textView("No safety reports this day", 15, 0xFF0F172A, true);
            emptyTitle.setGravity(Gravity.CENTER_HORIZONTAL);
            emptyCard.addView(emptyTitle, fullWidth());
            TextView emptySub = textView(
                    "Code " + (segText.isEmpty() ? "—" : segText) + " — nothing is scheduled to send.",
                    12, 0xFF64748B, false);
            emptySub.setGravity(Gravity.CENTER_HORIZONTAL);
            emptyCard.addView(emptySub, fullWidth());
            container.addView(emptyCard, ui.cardParams());
        } else {
            for (int i = 0; i < slots.length(); i++) {
                JSONObject slot = slots.optJSONObject(i);
                if (slot != null) {
                    container.addView(slotRow(slot, relation), ui.cardParams());
                }
            }
        }

        // 全日操作（過去日唔俾改）
        if (!isPast) {
            container.addView(actionBar(mode, source));
            container.addView(ui.noteStrip(
                    "⚠ 轉code只改報更——更表／行位表／餐單／報開工收工唔郁"),
                    ui.cardParams());
        } else {
            container.addView(textView("Past day is read-only.", 10, 0xFF9AA1A9, false));
        }

        // 對照表 + template（預設摺埋，撳標題展開；撳一行即編輯，改完即儲存）
        JSONObject mapping = plan.optJSONObject("mapping");
        List<String> codes = new ArrayList<>();
        if (mapping != null) {
            Iterator<String> keys = mapping.keys();
            while (keys.hasNext()) {
                codes.add(keys.next());
            }
            java.util.Collections.sort(codes);
        }
        container.addView(sectionHeader("Code → WhatsApp group mapping",
                codes.size() + " codes", mappingExpanded, v -> {
                    mappingExpanded = !mappingExpanded;
                    render();
                }));
        if (mappingExpanded) {
            for (String code : codes) {
                String group = mapping.optString(code, "");
                TextView rowView = textView(code + " → " + group, 11, 0xFF374151, false);
                rowView.setBackground(ui.roundedBg(0xFFF8FAFC, 6, 0, 0));
                rowView.setPadding(dp(10), dp(5), dp(10), dp(5));
                LinearLayout.LayoutParams params = fullWidth();
                params.setMargins(dp(8), dp(2), dp(8), 0);
                rowView.setOnClickListener(v -> showMappingEditDialog(code, group));
                container.addView(rowView, params);
            }
            LinearLayout mapActions = row();
            Button addCode = actionButton("+ Add code");
            addCode.setOnClickListener(v -> showMappingEditDialog("", ""));
            mapActions.addView(addCode, weighted(1f));
            Button templateButton = actionButton("Template...");
            templateButton.setOnClickListener(v -> showTemplateDialog());
            mapActions.addView(templateButton, weighted(1f));
            container.addView(mapActions);
            container.addView(textView("Template: " + plan.optString("message_template", ""), 10, 0xFF9AA1A9, false));
        }

        // Control log（預設摺埋）
        JSONArray events = plan.optJSONArray("events");
        int eventCount = events != null ? events.length() : 0;
        container.addView(sectionHeader("Control log",
                eventCount + " events", logExpanded, v -> {
                    logExpanded = !logExpanded;
                    render();
                }));
        if (logExpanded && events != null) {
            int shown = Math.min(events.length(), 8);
            for (int i = 0; i < shown; i++) {
                JSONObject ev = events.optJSONObject(i);
                if (ev == null) {
                    continue;
                }
                String line = formatEventTime(ev.optString("at", "")) + " "
                        + ev.optString("detail", ev.optString("action", ""))
                        + " · " + ev.optString("source", "");
                container.addView(textView(line, 10, 0xFF64748B, false));
            }
        }
    }

    /** 可摺疊 section 標題行：左標題、右數量+箭咀，撳一下 toggle。 */
    private LinearLayout sectionHeader(String title, String count, boolean expanded,
            android.view.View.OnClickListener onClick) {
        LinearLayout header = row();
        header.setPadding(dp(8), dp(8), dp(8), dp(4));
        TextView titleView = textView(title, 12, 0xFF334155, true);
        titleView.setPadding(0, 0, 0, 0);
        header.addView(titleView, weighted(1f));
        TextView countView = textView(count + " " + (expanded ? "▴" : "▾"), 11, 0xFF94A3B8, false);
        countView.setPadding(0, 0, 0, 0);
        header.addView(countView);
        header.setOnClickListener(onClick);
        return header;
    }

    private LinearLayout actionBar(String mode, String source) {
        LinearLayout actionRow = row();
        String dayLabel = viewDate.isEmpty() ? "today" : "this day";
        if ("stop".equals(mode)) {
            Button resume = actionButton("Resume " + dayLabel);
            resume.setTextColor(0xFF0B3EA8);
            resume.setOnClickListener(v -> confirmThenPost(
                    "Resume " + dayLabel + "?", "Rebuilds the schedule from the schedule grid.",
                    modePayload("auto"), "Rescheduling..."));
            actionRow.addView(resume, weighted(1f));
        } else {
            Button stop = actionButton("Stop " + dayLabel);
            stop.setTextColor(0xFFB91C1C);
            stop.setOnClickListener(v -> confirmThenPost(
                    "Stop " + dayLabel + "?", "Clears the remaining schedule (already-sent unaffected).",
                    modePayload("stop"), "Clearing..."));
            actionRow.addView(stop, weighted(1f));
        }
        Button changeCode = actionButton("Change code");
        changeCode.setOnClickListener(v -> showChangeCodeDialog(false));
        actionRow.addView(changeCode, weighted(1f));
        Button changeCodeFrom = actionButton("Mid-day");
        changeCodeFrom.setOnClickListener(v -> showChangeCodeDialog(true));
        actionRow.addView(changeCodeFrom, weighted(1f));
        if ("override".equals(source)) {
            Button follow = actionButton("Follow roster");
            follow.setOnClickListener(v -> {
                JSONObject payload = overridePayload();
                try {
                    payload.put("segments", new JSONArray());
                } catch (Exception ignored) {
                }
                postOverride(payload, "Restoring...");
            });
            actionRow.addView(follow, weighted(1f));
        }
        return actionRow;
    }

    private LinearLayout slotRow(JSONObject slot, String relation) {
        String status = slot.optString("status", "");
        boolean isPast = "past".equals(relation);
        boolean isToday = "today".equals(relation);
        boolean editable = !isPast && !"sent".equals(status) && !"stopped".equals(status);

        LinearLayout rowLayout = row();
        rowLayout.setBackground("due".equals(status)
                ? ui.roundedBg(0xFFE6F1FB, 10, 0xFF378ADD, 2)
                : ui.roundedBg(0xFFFFFFFF, 10, 0xFFD8DEE6, 1));
        rowLayout.setPadding(dp(10), dp(6), dp(10), dp(6));

        LinearLayout textColumn = new LinearLayout(activity);
        textColumn.setOrientation(LinearLayout.VERTICAL);
        LinearLayout timeLine = row();
        String timeText = slot.optString("time", "");
        if (!timeText.equals(slot.optString("original_time", timeText))) {
            timeText += "*";
        }
        TextView time = textView(timeText, 18, editable ? 0xFF0B3EA8 : 0xFF64748B, true);
        time.setPadding(0, 0, dp(10), 0);
        if (editable) {
            time.setOnClickListener(v -> showTimeDialog(slot));
        }
        timeLine.addView(time);
        timeLine.addView(statusView(slot, status));
        textColumn.addView(timeLine);

        TextView message = textView(slot.optString("message", ""), 10, 0xFF64748B, false);
        textColumn.addView(message);
        String groupName = slot.optString("group", "");
        TextView group = textView(
                "→ " + (groupName.isEmpty() ? "(no group)" : groupName) + (editable ? " ▾" : ""),
                10, editable ? 0xFF0B3EA8 : 0xFF64748B, false);
        if (editable) {
            group.setOnClickListener(v -> showGroupPicker(slot));
        }
        textColumn.addView(group);
        rowLayout.addView(textColumn, weighted(1f));

        String slotId = slot.optString("id", "");
        if ("sent".equals(status)) {
            if (isToday) {
                rowLayout.addView(sendButton("Resend", slotId, true), buttonParams());
            }
        } else if ("skipped".equals(status)) {
            // skipped：Skip 掣變 Skipped（dim，撳一下取消 skip）；Send 照常可用（收工先報）。
            Button skipped = actionButton("Skipped");
            skipped.setAlpha(0.45f);
            skipped.setOnClickListener(v -> postSlotPatch(slotId, "skip", Boolean.FALSE));
            rowLayout.addView(skipped, buttonParams());
            if (isToday) {
                rowLayout.addView(sendButton("Send", slotId, false), buttonParams());
            }
        } else if (!"stopped".equals(status) && !isPast) {
            Button skip = actionButton("Skip");
            skip.setOnClickListener(v -> postSlotPatch(slotId, "skip", Boolean.TRUE));
            rowLayout.addView(skip, buttonParams());
            if (isToday) {
                rowLayout.addView(
                        sendButton(("failed".equals(status) || "missed".equals(status)) ? "Retry" : "Send",
                                slotId, false),
                        buttonParams());
            }
        }
        return rowLayout;
    }

    private TextView statusView(JSONObject slot, String status) {
        switch (status) {
            case "sent":
                return ui.chip("✓ " + timeOnly(slot.optString("sent_at", ""))
                        + (slot.optBoolean("manual", false) ? " (manual)" : ""),
                        0xFF085041, 0xFFE1F5EE);
            case "failed":
                return ui.chip("✗ failed", 0xFF791F1F, 0xFFFCEBEB);
            case "missed":
                return ui.chip("✗ missed", 0xFF791F1F, 0xFFFCEBEB);
            case "skipped":
                return ui.chip("skipped", 0xFF5F5E5A, 0xFFF1EFE8);
            case "stopped":
                return ui.chip("stopped", 0xFF5F5E5A, 0xFFF1EFE8);
            case "no_record":
                return textView("—", 11, 0xFF9AA1A9, false);
            case "due":
                return textView(plan.optBoolean("auto_send", false)
                        ? "\u23f3 sending..." : "due (auto-send off)", 11, 0xFF0C447C, true);
            default:
                return textView("⏱ " + countdownText(slot), 11, 0xFF9AA1A9, false);
        }
    }

    private String countdownText(JSONObject slot) {
        try {
            String[] dateParts = plan.optString("date_iso", "").split("-");
            String[] timeParts = slot.optString("time", "").split(":");
            Calendar cal = Calendar.getInstance();
            cal.set(Integer.parseInt(dateParts[0]), Integer.parseInt(dateParts[1]) - 1,
                    Integer.parseInt(dateParts[2]), Integer.parseInt(timeParts[0]),
                    Integer.parseInt(timeParts[1]), 0);
            if (Integer.parseInt(timeParts[0]) < 6) {
                cal.add(Calendar.DAY_OF_MONTH, 1);
            }
            long diffMs = cal.getTimeInMillis() - System.currentTimeMillis();
            if (diffMs <= 0) {
                return "now";
            }
            long mins = Math.round(diffMs / 60000.0);
            if (mins < 60) {
                return "in " + mins + "m";
            }
            return "in " + (mins / 60) + "h " + (mins % 60) + "m";
        } catch (Exception e) {
            return "pending";
        }
    }

    private Button sendButton(String label, String slotId, boolean resend) {
        Button button = actionButton(label);
        button.setTextColor(0xFF0B3EA8);
        button.setOnClickListener(v -> new AlertDialog.Builder(activity)
                .setTitle(resend ? "Resend?" : "Send now?")
                .setMessage("Sends this report via the PC WhatsApp immediately.")
                .setPositiveButton("Send", (d, w) -> {
                    JSONObject payload = new JSONObject();
                    try {
                        payload.put("slot_id", slotId);
                        payload.put("source", "phone");
                        if (!viewDate.isEmpty()) {
                            payload.put("date_iso", viewDate);
                        }
                    } catch (Exception ignored) {
                    }
                    postJson("/api/duty-report/send", payload, "Sending...");
                })
                .setNegativeButton("Cancel", null)
                .show());
        return button;
    }

    private void postSlotPatch(String slotId, String key, Object value) {
        JSONObject payload = overridePayload();
        try {
            JSONObject slot = new JSONObject();
            slot.put("id", slotId);
            slot.put(key, value);
            payload.put("slot", slot);
        } catch (Exception ignored) {
        }
        postOverride(payload, "Updating...");
    }

    void shiftDate(int deltaDays) {
        if (plan == null || loading) {
            return;
        }
        final String target;
        final String iso;
        try {
            String[] parts = plan.optString("date_iso", "").split("-");
            Calendar cal = Calendar.getInstance();
            cal.set(Integer.parseInt(parts[0]), Integer.parseInt(parts[1]) - 1, Integer.parseInt(parts[2]), 12, 0, 0);
            cal.add(Calendar.DAY_OF_MONTH, deltaDays);
            iso = String.format(java.util.Locale.US, "%04d-%02d-%02d",
                    cal.get(Calendar.YEAR), cal.get(Calendar.MONTH) + 1, cal.get(Calendar.DAY_OF_MONTH));
            target = iso.equals(plan.optString("today_iso", "")) ? "" : iso;
        } catch (Exception e) {
            return;
        }
        loading = true;
        new Thread(() -> {
            try {
                String body = ApiClient.request(
                        activity,
                        "GET",
                        "/api/duty-report/plan" + (target.isEmpty() ? "" : "?date_iso=" + target),
                        null,
                        HTTP_READ_TIMEOUT_MS);
                JSONObject parsed = new JSONObject(body);
                activity.runOnUiThread(() -> {
                    loading = false;
                    // 未有更碼嘅日子（更表未出）唔入去。
                    if ("none".equals(parsed.optString("source", ""))) {
                        Toast.makeText(activity, iso + " has no roster code yet", Toast.LENGTH_SHORT).show();
                        return;
                    }
                    viewDate = target;
                    plan = parsed;
                    render();
                });
            } catch (Exception e) {
                activity.runOnUiThread(() -> {
                    loading = false;
                    Toast.makeText(activity, "Cannot reach PC: " + e.getMessage(), Toast.LENGTH_SHORT).show();
                });
            }
        }, "duty-report-shift").start();
    }

    // ---------------------------------------------------------------- dialogs

    /** 大窗時間輸入（同行位表一致）：兩個大數字格，打滿自動跳；時 0–29（30小時制）。 */
    private void showTimeDialog(JSONObject slot) {
        String slotId = slot.optString("id", "");
        String[] parts = slot.optString("time", "00:00").split(":");

        LinearLayout box = new LinearLayout(activity);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setPadding(dp(18), dp(4), dp(18), 0);

        LinearLayout inputs = new LinearLayout(activity);
        inputs.setOrientation(LinearLayout.HORIZONTAL);
        inputs.setGravity(Gravity.CENTER);

        EditText hourInput = timePartInput(parts.length > 0 ? parts[0] : "00");
        EditText minuteInput = timePartInput(parts.length > 1 ? parts[1] : "00");
        TextView colon = new TextView(activity);
        colon.setText(":");
        colon.setTextSize(34);
        colon.setGravity(Gravity.CENTER);
        colon.setTextColor(0xFF111827);

        inputs.addView(hourInput, weighted(1f));
        inputs.addView(colon, new LinearLayout.LayoutParams(dp(28), LinearLayout.LayoutParams.WRAP_CONTENT));
        inputs.addView(minuteInput, weighted(1f));
        box.addView(inputs, fullWidth());

        LinearLayout labels = new LinearLayout(activity);
        labels.setOrientation(LinearLayout.HORIZONTAL);
        labels.setGravity(Gravity.CENTER);
        labels.addView(timePartLabel("Hour (0-29)"), weighted(1f));
        labels.addView(timePartLabel(""), new LinearLayout.LayoutParams(dp(28), LinearLayout.LayoutParams.WRAP_CONTENT));
        labels.addView(timePartLabel("Minute"), weighted(1f));
        box.addView(labels, fullWidth());

        hourInput.addTextChangedListener(new android.text.TextWatcher() {
            @Override public void beforeTextChanged(CharSequence s, int start, int count, int after) {}
            @Override public void onTextChanged(CharSequence s, int start, int before, int count) {
                if (digitsOnly(s).length() >= 2) {
                    minuteInput.requestFocus();
                    minuteInput.selectAll();
                }
            }
            @Override public void afterTextChanged(android.text.Editable s) {}
        });
        minuteInput.addTextChangedListener(new android.text.TextWatcher() {
            @Override public void beforeTextChanged(CharSequence s, int start, int count, int after) {}
            @Override public void onTextChanged(CharSequence s, int start, int before, int count) {
                if (digitsOnly(s).length() >= 2) {
                    hideKeyboard(minuteInput);
                }
            }
            @Override public void afterTextChanged(android.text.Editable s) {}
        });

        AlertDialog dialog = new AlertDialog.Builder(activity)
                .setTitle("Edit time (original " + slot.optString("original_time", "") + ")")
                .setView(box)
                .setNegativeButton("Cancel", null)
                .setNeutralButton("Restore original", (d, w) -> postSlotPatch(slotId, "time", ""))
                .setPositiveButton("OK", null)
                .create();
        dialog.setOnShowListener(d -> {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v -> {
                int hour = parseTwoDigit(hourInput, -1);
                int minute = parseTwoDigit(minuteInput, -1);
                if (hour < 0 || hour > 29 || minute < 0 || minute > 59) {
                    Toast.makeText(activity, "00:00 - 29:59 (24-29 = next-day early morning)", Toast.LENGTH_SHORT).show();
                    return;
                }
                postSlotPatch(slotId, "time", String.format(java.util.Locale.US, "%02d%02d", hour, minute));
                dialog.dismiss();
            });
            hourInput.requestFocus();
            hourInput.selectAll();
            hourInput.postDelayed(() -> {
                android.view.inputmethod.InputMethodManager imm =
                        (android.view.inputmethod.InputMethodManager) activity.getSystemService(android.content.Context.INPUT_METHOD_SERVICE);
                if (imm != null) {
                    imm.showSoftInput(hourInput, android.view.inputmethod.InputMethodManager.SHOW_IMPLICIT);
                }
            }, 180);
        });
        dialog.show();
    }

    private EditText timePartInput(String value) {
        EditText input = new EditText(activity);
        input.setText(value);
        input.setTextSize(42);
        input.setGravity(Gravity.CENTER);
        input.setSelectAllOnFocus(true);
        input.setSingleLine(true);
        input.setFilters(new android.text.InputFilter[]{new android.text.InputFilter.LengthFilter(2)});
        input.setInputType(InputType.TYPE_CLASS_NUMBER);
        input.setPadding(dp(10), dp(8), dp(10), dp(8));
        return input;
    }

    private TextView timePartLabel(String text) {
        TextView label = new TextView(activity);
        label.setText(text);
        label.setTextSize(12);
        label.setTextColor(0xFF6B7280);
        label.setGravity(Gravity.CENTER);
        label.setTypeface(regularTypeface);
        label.setPadding(0, dp(4), 0, 0);
        return label;
    }

    private static String digitsOnly(CharSequence s) {
        return String.valueOf(s == null ? "" : s).replaceAll("\\D+", "");
    }

    private static int parseTwoDigit(EditText input, int fallback) {
        try {
            String raw = digitsOnly(input.getText());
            if (raw.isEmpty()) {
                return fallback;
            }
            return Integer.parseInt(raw);
        } catch (NumberFormatException e) {
            return fallback;
        }
    }

    private void hideKeyboard(EditText input) {
        android.view.inputmethod.InputMethodManager imm =
                (android.view.inputmethod.InputMethodManager) activity.getSystemService(android.content.Context.INPUT_METHOD_SERVICE);
        if (imm != null) {
            imm.hideSoftInputFromWindow(input.getWindowToken(), 0);
        }
    }

    private void showGroupPicker(JSONObject slot) {
        String slotId = slot.optString("id", "");
        List<String> groups = new ArrayList<>();
        JSONObject mapping = plan.optJSONObject("mapping");
        if (mapping != null) {
            Iterator<String> it = mapping.keys();
            while (it.hasNext()) {
                String group = mapping.optString(it.next(), "");
                if (!group.isEmpty() && !groups.contains(group)) {
                    groups.add(group);
                }
            }
        }
        String current = slot.optString("group", "");
        if (!current.isEmpty() && !groups.contains(current)) {
            groups.add(current);
        }
        List<String> labels = new ArrayList<>(groups);
        labels.add("(Default: follow mapping)");
        labels.add("Custom...");
        String[] items = labels.toArray(new String[0]);
        new AlertDialog.Builder(activity)
                .setTitle("Pick WhatsApp group")
                .setItems(items, (dialog, which) -> {
                    if (which < groups.size()) {
                        postSlotPatch(slotId, "group", groups.get(which));
                    } else if (which == groups.size()) {
                        postSlotPatch(slotId, "group", "");
                    } else {
                        promptText("Enter WhatsApp group name", current, text -> {
                            if (!text.trim().isEmpty()) {
                                postSlotPatch(slotId, "group", text.trim());
                            }
                        });
                    }
                })
                .show();
    }

    private void showChangeCodeDialog(boolean midDay) {
        java.util.TreeSet<String> merged = new java.util.TreeSet<>();
        JSONObject mapping = plan != null ? plan.optJSONObject("mapping") : null;
        if (mapping != null) {
            Iterator<String> it = mapping.keys();
            while (it.hasNext()) {
                merged.add(it.next());
            }
        }
        JSONArray known = plan != null ? plan.optJSONArray("known_codes") : null;
        if (known != null) {
            for (int i = 0; i < known.length(); i++) {
                String c = known.optString(i, "").trim();
                if (!c.isEmpty()) {
                    merged.add(c);
                }
            }
        }
        List<String> codes = new ArrayList<>(merged);
        codes.add("Other code...");
        String[] labels = codes.toArray(new String[0]);
        new AlertDialog.Builder(activity)
                .setTitle(midDay ? "Mid-day switch (from a time)" : "Change code (whole day)")
                .setItems(labels, (dialog, which) -> {
                    String picked = labels[which];
                    if ("Other code...".equals(picked)) {
                        promptText("Enter code", "", code -> {
                            if (!code.trim().isEmpty()) {
                                afterCodePicked(code.trim(), midDay);
                            }
                        });
                    } else {
                        afterCodePicked(picked, midDay);
                    }
                })
                .show();
    }

    private void afterCodePicked(String code, boolean midDay) {
        if (!midDay) {
            JSONObject payload = overridePayload();
            try {
                payload.put("mode", "auto");
                JSONArray segments = new JSONArray();
                segments.put(new JSONObject().put("from", "00:00").put("code", code));
                payload.put("segments", segments);
            } catch (Exception ignored) {
            }
            postOverride(payload, "Rescheduling...");
            return;
        }
        promptText("Switch to " + code + " from? (09:16 / 0916)", "", from -> {
            String trimmed = from.trim();
            if (trimmed.matches("\\d{3,4}")) {
                String minutePart = trimmed.substring(trimmed.length() - 2);
                String hourPart = trimmed.substring(0, trimmed.length() - 2);
                trimmed = (hourPart.length() == 1 ? "0" + hourPart : hourPart) + ":" + minutePart;
            }
            if (!trimmed.matches("\\d{1,2}:\\d{2}")) {
                Toast.makeText(activity, "Time must be HH:MM or HHMM", Toast.LENGTH_LONG).show();
                return;
            }
            JSONObject payload = overridePayload();
            try {
                payload.put("mode", "auto");
                JSONArray segments = new JSONArray();
                JSONArray current = plan != null ? plan.optJSONArray("segments") : null;
                if (current != null) {
                    for (int i = 0; i < current.length(); i++) {
                        JSONObject seg = current.optJSONObject(i);
                        if (seg != null && seg.optString("from", "00:00").compareTo(trimmed) < 0) {
                            segments.put(new JSONObject()
                                    .put("from", seg.optString("from", "00:00"))
                                    .put("code", seg.optString("code", "")));
                        }
                    }
                }
                segments.put(new JSONObject().put("from", trimmed).put("code", code));
                payload.put("segments", segments);
            } catch (Exception ignored) {
            }
            postOverride(payload, "Rescheduling...");
        });
    }

    /** 對照表：改一行即儲存；code 留空＝刪除該行；group 用 pickup list 揀。 */
    private void showMappingEditDialog(String originalCode, String originalGroup) {
        LinearLayout form = new LinearLayout(activity);
        form.setOrientation(LinearLayout.VERTICAL);
        form.setPadding(dp(16), dp(4), dp(16), 0);
        EditText codeInput = new EditText(activity);
        codeInput.setTypeface(regularTypeface);
        codeInput.setHint("Code (blank = delete this row)");
        codeInput.setText(originalCode);
        form.addView(codeInput);

        final String[] pickedGroup = {originalGroup};
        TextView groupPicker = textView(
                "Group: " + (originalGroup.isEmpty() ? "(tap to pick)" : originalGroup) + " \u25be",
                13, 0xFF0B3EA8, false);
        groupPicker.setPadding(dp(4), dp(10), dp(4), dp(10));
        groupPicker.setOnClickListener(v -> {
            List<String> groups = uniqueGroups(pickedGroup[0]);
            List<String> labels = new ArrayList<>(groups);
            labels.add("Custom...");
            new AlertDialog.Builder(activity)
                    .setTitle("Pick WhatsApp group")
                    .setItems(labels.toArray(new String[0]), (dialog, which) -> {
                        if (which < groups.size()) {
                            pickedGroup[0] = groups.get(which);
                            groupPicker.setText("Group: " + pickedGroup[0] + " \u25be");
                        } else {
                            promptText("Enter WhatsApp group name", pickedGroup[0], text -> {
                                if (!text.trim().isEmpty()) {
                                    pickedGroup[0] = text.trim();
                                    groupPicker.setText("Group: " + pickedGroup[0] + " \u25be");
                                }
                            });
                        }
                    })
                    .show();
        });
        form.addView(groupPicker);

        new AlertDialog.Builder(activity)
                .setTitle(originalCode.isEmpty() ? "Add code mapping" : "Edit mapping: " + originalCode)
                .setView(form)
                .setPositiveButton("Save", (d, w) -> {
                    LinkedHashMap<String, String> updated = currentMapping();
                    if (!originalCode.isEmpty()) {
                        updated.remove(originalCode);
                    }
                    String newCode = codeInput.getText().toString().trim();
                    if (!newCode.isEmpty()) {
                        updated.put(newCode, pickedGroup[0]);
                    }
                    postMapping(updated);
                })
                .setNegativeButton("Cancel", null)
                .show();
    }

    /** 對照表入面所有唔重覆嘅 group 名（可加埋當前值）。 */
    private List<String> uniqueGroups(String includeCurrent) {
        List<String> groups = new ArrayList<>();
        JSONObject mapping = plan != null ? plan.optJSONObject("mapping") : null;
        if (mapping != null) {
            Iterator<String> it = mapping.keys();
            while (it.hasNext()) {
                String group = mapping.optString(it.next(), "");
                if (!group.isEmpty() && !groups.contains(group)) {
                    groups.add(group);
                }
            }
        }
        if (includeCurrent != null && !includeCurrent.isEmpty() && !groups.contains(includeCurrent)) {
            groups.add(includeCurrent);
        }
        return groups;
    }

    private LinkedHashMap<String, String> currentMapping() {
        LinkedHashMap<String, String> out = new LinkedHashMap<>();
        JSONObject mapping = plan != null ? plan.optJSONObject("mapping") : null;
        if (mapping != null) {
            Iterator<String> it = mapping.keys();
            while (it.hasNext()) {
                String key = it.next();
                out.put(key, mapping.optString(key, ""));
            }
        }
        return out;
    }

    private void postMapping(LinkedHashMap<String, String> mapping) {
        JSONObject payload = new JSONObject();
        try {
            JSONObject json = new JSONObject();
            for (Map.Entry<String, String> entry : mapping.entrySet()) {
                json.put(entry.getKey(), entry.getValue());
            }
            payload.put("mapping", json);
        } catch (Exception ignored) {
        }
        postConfig(payload, "Saving mapping...");
    }

    private void showTemplateDialog() {
        EditText input = new EditText(activity);
        input.setText(plan != null ? plan.optString("message_template", "") : "");
        input.setHint("{code} SAPP1801 報平安更正常");
        new AlertDialog.Builder(activity)
                .setTitle("Message template (must contain {code})")
                .setView(input)
                .setPositiveButton("Save", (d, w) -> {
                    String text = input.getText().toString();
                    if (!text.contains("{code}")) {
                        Toast.makeText(activity, "Template must contain {code}", Toast.LENGTH_LONG).show();
                        return;
                    }
                    JSONObject payload = new JSONObject();
                    try {
                        payload.put("message_template", text);
                    } catch (Exception ignored) {
                    }
                    postConfig(payload, "Saving template...");
                })
                .setNegativeButton("Cancel", null)
                .show();
    }

    private void confirmThenPost(String title, String message, JSONObject payload, String busyText) {
        new AlertDialog.Builder(activity)
                .setTitle(title)
                .setMessage(message)
                .setPositiveButton("OK", (d, w) -> postOverride(payload, busyText))
                .setNegativeButton("Cancel", null)
                .show();
    }

    private void promptText(String title, String preset, TextCallback callback) {
        EditText input = new EditText(activity);
        input.setInputType(InputType.TYPE_CLASS_TEXT);
        input.setText(preset);
        new AlertDialog.Builder(activity)
                .setTitle(title)
                .setView(input)
                .setPositiveButton("OK", (d, w) -> callback.onText(input.getText().toString()))
                .setNegativeButton("Cancel", null)
                .show();
    }

    private interface TextCallback {
        void onText(String text);
    }

    private JSONObject modePayload(String mode) {
        JSONObject payload = overridePayload();
        try {
            payload.put("mode", mode);
        } catch (Exception ignored) {
        }
        return payload;
    }

    // ---------------------------------------------------------------- helpers

    private String segmentsText() {
        JSONArray segments = plan != null ? plan.optJSONArray("segments") : null;
        if (segments == null || segments.length() == 0) {
            return "";
        }
        StringBuilder out = new StringBuilder();
        for (int i = 0; i < segments.length(); i++) {
            JSONObject seg = segments.optJSONObject(i);
            if (seg == null) {
                continue;
            }
            if (out.length() > 0) {
                out.append(" → ");
            }
            out.append(seg.optString("code", ""));
            String from = seg.optString("from", "00:00");
            if (!"00:00".equals(from)) {
                out.append("(from ").append(from).append(")");
            }
        }
        return out.toString();
    }

    private static String timeOnly(String iso) {
        int t = iso.indexOf('T');
        if (t >= 0 && iso.length() >= t + 6) {
            return iso.substring(t + 1, t + 6);
        }
        return "";
    }

    private static String formatEventTime(String iso) {
        if (iso.length() >= 19 && iso.charAt(10) == 'T') {
            return iso.substring(8, 10) + "/" + iso.substring(5, 7) + " " + iso.substring(11, 19);
        }
        return iso;
    }


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
