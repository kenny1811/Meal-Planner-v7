package com.example.oneshotalarm;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Context;
import android.graphics.Typeface;
import android.view.Gravity;
import android.widget.Button;
import android.widget.EditText;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Calendar;
import java.util.Comparator;
import java.util.Locale;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 行位表 tab：header（日期＋更碼掣）、鬧鐘表（改時間／改內容／ON-OFF／long-press 插入刪除）、
 * import／to Computer／Append／今日+／手錶 ON-OFF 掣、status 行。
 * 由 MainActivity 拆出嚟；draftAlarms 等編輯狀態都住喺呢度，儲存即 AlarmScheduler.schedulePlan。
 */
final class ShiftTableView {

    /** status 行「餐單：已連線／未連線」問返餐單頁。 */
    interface MealPlanStatus {
        boolean isConnected();
    }

    private static final int HTTP_READ_TIMEOUT_MS = 7000;
    private static final Pattern SCHEDULE_GRID_DATE_RE = Pattern.compile(
            "^\\s*(\\d{4}-\\d{2}-\\d{2}|(\\d{1,2})/(\\d{1,2})/(\\d{4}))\\s*$"
    );
    /** 星號行「* 飯 55」：尾數係人手打嘅固定時長（同網頁 scheduleGridStarMinutes 一樣）。 */
    private static final Pattern STAR_DURATION_RE = Pattern.compile("^\\*.*?\\s(\\d{1,3})$");

    private final Activity activity;
    private final PanelUi ui;
    private final MealPlanStatus mealPlanStatus;
    private final Typeface boldTypeface;

    private TextView headerView;
    private TextView statusView;
    private LinearLayout tableView;
    private Button shiftVariantButton;
    private Button watchAlarmToggleButton;
    private JSONArray draftAlarms = new JSONArray();
    private String draftDate = "";
    private String draftRosterCode = "";
    private String shiftEmptyMessage = "";
    private ActivePlanSnapshot draftBaseSnapshot;

    /** Read all active-plan keys together, including when an importer writes on another thread. */
    private static final class ActivePlanSnapshot {
        final String alarmsJson;
        final String planDate;
        final String rosterCode;

        ActivePlanSnapshot(Map<String, ?> values) {
            alarmsJson = stringValue(values.get("alarms_json"), "[]");
            planDate = stringValue(values.get("plan_date"), "");
            rosterCode = stringValue(values.get("roster_code"), "");
        }

        private static String stringValue(Object value, String fallback) {
            return value instanceof String ? (String) value : fallback;
        }

        boolean sameAs(ActivePlanSnapshot other) {
            return other != null && alarmsJson.equals(other.alarmsJson)
                    && planDate.equals(other.planDate) && rosterCode.equals(other.rosterCode);
        }
    }

    ShiftTableView(Activity activity, LinearLayout container, Typeface regular, Typeface bold, MealPlanStatus mealPlanStatus) {
        this.activity = activity;
        this.mealPlanStatus = mealPlanStatus;
        this.boldTypeface = bold != null ? bold : Typeface.DEFAULT_BOLD;
        this.ui = new PanelUi(activity, regular, bold);
        buildUi(container);
    }

    // ---------------------------------------------------------------- MainActivity 入口

    void loadFromStore() {
        draftBaseSnapshot = readActivePlanSnapshot();
        try {
            draftAlarms = new JSONArray(draftBaseSnapshot.alarmsJson);
        } catch (JSONException e) {
            draftAlarms = new JSONArray();
        }
        draftDate = draftBaseSnapshot.planDate;
        draftRosterCode = draftBaseSnapshot.rosterCode;
        if (draftAlarms.length() > 0) {
            shiftEmptyMessage = "";
        }
    }

    private ActivePlanSnapshot readActivePlanSnapshot() {
        return new ActivePlanSnapshot(activity.getSharedPreferences(AlarmStore.PREFS, Context.MODE_PRIVATE).getAll());
    }

    private boolean requireCurrentDraft(ActivePlanSnapshot expected) {
        if (expected != null && expected.sameAs(draftBaseSnapshot)
                && expected.sameAs(readActivePlanSnapshot())) {
            return true;
        }
        loadFromStore();
        render();
        Toast.makeText(activity, "行位表已更新，已取消舊修改；請按最新行位表重新編輯。", Toast.LENGTH_LONG).show();
        return false;
    }

    void render() {
        headerView.setText(formatHeader());
        tableView.removeAllViews();
        if (draftAlarms.length() == 0 && !shiftEmptyMessage.trim().isEmpty()) {
            tableView.addView(shiftEmptyMessageView(shiftEmptyMessage), shiftEmptyMessageParams());
            if (shiftVariantButton != null) {
                shiftVariantButton.setText(shiftVariantButtonText());
            }
            applyWatchAlarmButtonState();
            statusView.setText(statusText());
            return;
        }
        tableView.addView(headerRow(), fullWidthWrapHeight());
        for (int i = 0; i < draftAlarms.length(); i++) {
            JSONObject alarm = draftAlarms.optJSONObject(i);
            if (alarm != null) {
                tableView.addView(alarmRow(i, alarm), fullWidthWrapHeight());
            }
        }
        addBlankRows(Math.max(0, 10 - draftAlarms.length()));
        if (shiftVariantButton != null) {
            shiftVariantButton.setText(shiftVariantButtonText());
        }
        applyWatchAlarmButtonState();
        statusView.setText(statusText());
    }

    /**
     * 由電腦 pull /export-all 重新匯入（import 掣同 adb 測試入口共用）：
     * 成功就重載＋toast「{successPrefix}N 個鬧鐘」，失敗就顯示原因＋清空表。
     */
    void importFromPc(String busyText, String successPrefix, String failPrefix) {
        statusView.setText(busyText);
        new Thread(() -> {
            ScheduleGridAutoImporter.ImportResult result;
            try {
                result = ScheduleGridAutoImporter.importFromPc(activity);
            } catch (Exception e) {
                result = new ScheduleGridAutoImporter.ImportResult(false, 0, "", "", e.getMessage());
            }
            ScheduleGridAutoImporter.ImportResult finalResult = result;
            activity.runOnUiThread(() -> {
                if (finalResult.ok) {
                    shiftEmptyMessage = "";
                    loadFromStore();
                    render();
                    String extra = finalResult.variantCount > 1
                            ? "，已載入 " + finalResult.variantCount + " 個更碼"
                            : "";
                    Toast.makeText(
                            activity,
                            successPrefix + finalResult.alarmCount + " 個鬧鐘" + extra,
                            Toast.LENGTH_LONG
                    ).show();
                } else {
                    showScheduleGridImportFailure(finalResult, failPrefix);
                }
            });
        }).start();
    }

    // ---------------------------------------------------------------- UI 骨架

    private void buildUi(LinearLayout shiftSection) {
        LinearLayout shiftHeaderBar = new LinearLayout(activity);
        shiftHeaderBar.setOrientation(LinearLayout.HORIZONTAL);
        shiftHeaderBar.setGravity(Gravity.CENTER_VERTICAL);
        shiftHeaderBar.setPadding(dp(4), dp(1), dp(4), dp(2));
        shiftHeaderBar.setBackgroundColor(0xFFFFFFFF);

        headerView = new TextView(activity);
        headerView.setTextSize(15);
        headerView.setTextColor(0xFF000000);
        headerView.setPadding(dp(4), dp(1), dp(6), dp(2));
        headerView.setBackgroundColor(0xFFFFFFFF);
        shiftHeaderBar.addView(headerView, weightedParams(1f));

        shiftVariantButton = ui.bottomButton("更碼");
        shiftVariantButton.setTextSize(11);
        shiftVariantButton.setOnClickListener(v -> showShiftVariantDialog(shouldApplyShiftVariantAsToday()));
        shiftHeaderBar.addView(shiftVariantButton, new LinearLayout.LayoutParams(dp(92), dp(34)));

        shiftSection.addView(shiftHeaderBar, fullWidthWrapHeight());

        tableView = new LinearLayout(activity);
        tableView.setOrientation(LinearLayout.VERTICAL);
        shiftSection.addView(tableView, fullWidthWrapHeight());

        LinearLayout bottom = new LinearLayout(activity);
        bottom.setOrientation(LinearLayout.VERTICAL);
        bottom.setPadding(0, dp(1), 0, 0);
        bottom.setBackgroundColor(0xFFFFFFFF);

        LinearLayout bottomTop = new LinearLayout(activity);
        bottomTop.setOrientation(LinearLayout.HORIZONTAL);
        bottomTop.setPadding(0, 0, 0, dp(1));

        Button importXmlButton = ui.bottomButton("import");
        importXmlButton.setOnClickListener(v -> launchImportScheduleGridXml());
        bottomTop.addView(importXmlButton, weightedParams(1f));

        Button pushToPc = ui.bottomButton("to Computer");
        pushToPc.setOnClickListener(v -> pushCurrentScheduleGridToPc());
        bottomTop.addView(pushToPc, weightedParams(1f));

        bottom.addView(bottomTop, fullWidthWrapHeight());

        LinearLayout bottomSecond = new LinearLayout(activity);
        bottomSecond.setOrientation(LinearLayout.HORIZONTAL);
        bottomSecond.setPadding(0, 0, 0, 0);

        Button append = ui.bottomButton("Append");
        append.setOnClickListener(v -> appendAlarm());
        bottomSecond.addView(append, weightedParams(1f));

        Button appendToday = ui.bottomButton("今日+");
        appendToday.setOnClickListener(v -> appendTodayAlarm());
        bottomSecond.addView(appendToday, weightedParams(1f));

        watchAlarmToggleButton = ui.bottomButton(watchAlarmButtonText());
        watchAlarmToggleButton.setOnClickListener(v -> toggleWatchAlarm());
        applyWatchAlarmButtonState();
        bottomSecond.addView(watchAlarmToggleButton, weightedParams(1f));

        bottom.addView(bottomSecond, fullWidthWrapHeight());

        shiftSection.addView(bottom, fullWidthWrapHeight());

        statusView = new TextView(activity);
        statusView.setTextSize(9);
        statusView.setTextColor(0xFF475569);
        statusView.setGravity(Gravity.CENTER);
        statusView.setPadding(dp(8), dp(2), dp(8), dp(4));
        shiftSection.addView(statusView, fullWidthWrapHeight());
    }

    private String watchAlarmButtonText() {
        return AlarmStore.isWatchAlarmEnabled(activity) ? "手錶ON" : "手錶OFF";
    }

    private void applyWatchAlarmButtonState() {
        if (watchAlarmToggleButton == null) {
            return;
        }
        boolean enabled = AlarmStore.isWatchAlarmEnabled(activity);
        watchAlarmToggleButton.setText(watchAlarmButtonText());
        watchAlarmToggleButton.setAlpha(enabled ? 1f : 0.42f);
    }

    /**
     * 手錶 ON/OFF：切換之後即刻推一次 tile state——ON 推成張行位表上錶，
     * OFF 推空表（手錶按空表排鬧鐘＝真係唔會響）。以前 OFF 淨係唔轉發 dismiss，
     * 手錶照響，個 toast「手錶鬧鐘已關」係誤導。
     */
    private void toggleWatchAlarm() {
        boolean enabled = !AlarmStore.isWatchAlarmEnabled(activity);
        AlarmStore.setWatchAlarmEnabled(activity, enabled);
        applyWatchAlarmButtonState();
        WatchBridge.sendTileState(activity);
        Toast.makeText(
                activity,
                enabled ? "手錶鬧鐘已開：行位表已推上手錶" : "手錶鬧鐘已關：已清走手錶行位表，手錶唔會響",
                Toast.LENGTH_SHORT
        ).show();
    }

    // ---------------------------------------------------------------- import / push

    private void launchImportScheduleGridXml() {
        if (!AlarmScheduler.canScheduleExactAlarm(activity)) {
            Toast.makeText(activity, "請先允許精準鬧鐘權限，再匯入", Toast.LENGTH_LONG).show();
            AlarmScheduler.requestExactAlarmPermission(activity);
            return;
        }
        importFromPc("從電腦匯入全部更碼中...", "已從電腦匯入 ", "匯入失敗");
    }

    private void pushCurrentScheduleGridToPc() {
        statusView.setText("推送行位表到電腦中...");
        new Thread(() -> {
            PushResult result;
            try {
                result = postCurrentScheduleGrid();
            } catch (Exception e) {
                result = new PushResult(false, 0, 0, e.getMessage());
            }
            PushResult finalResult = result;
            activity.runOnUiThread(() -> {
                if (finalResult.ok) {
                    String message = "已推送行位表到電腦：" + finalResult.importedRows + " 行";
                    if (finalResult.replacedRows >= 0) {
                        message += "，取代 " + finalResult.replacedRows + " 行";
                    }
                    statusView.setText(statusText());
                    Toast.makeText(activity, message, Toast.LENGTH_LONG).show();
                } else {
                    String message = finalResult.message == null || finalResult.message.isEmpty()
                            ? "推送失敗"
                            : finalResult.message;
                    statusView.setText("推送失敗：" + message);
                    Toast.makeText(activity, "推送失敗：" + message, Toast.LENGTH_LONG).show();
                }
            });
        }).start();
    }

    private PushResult postCurrentScheduleGrid() throws Exception {
        String response = ApiClient.request(
                activity,
                "POST",
                "/api/maint/sheets/schedule_grid/import-phone-push",
                buildScheduleGridPushPayload().toString(),
                HTTP_READ_TIMEOUT_MS
        );
        JSONObject json = new JSONObject(response);
        return new PushResult(
                json.optBoolean("ok", false),
                json.optInt("imported_row_count", 0),
                json.optInt("replaced_row_count", -1),
                json.optString("detail", json.optString("message", ""))
        );
    }

    private static final class PushResult {
        final boolean ok;
        final int importedRows;
        final int replacedRows;
        final String message;

        PushResult(boolean ok, int importedRows, int replacedRows, String message) {
            this.ok = ok;
            this.importedRows = importedRows;
            this.replacedRows = replacedRows;
            this.message = message == null ? "" : message;
        }
    }

    /** 推去電腦嘅 payload：{effective_date, roster_code, alarms:[{time,label}]}。 */
    private JSONObject buildScheduleGridPushPayload() throws JSONException {
        String exportDate = parseDateTextToIso(draftDate == null ? "" : draftDate);
        if (exportDate.isEmpty()) {
            exportDate = Clock30.todayIso();
        }
        JSONArray alarms = new JSONArray();
        for (int i = 0; i < draftAlarms.length(); i++) {
            JSONObject alarm = draftAlarms.optJSONObject(i);
            if (alarm == null) {
                continue;
            }
            String time = clockOnly(alarm.optLong("trigger_at_epoch_ms"));
            String label = alarm.optString("label", "").trim();
            if (time.isEmpty() || label.isEmpty()) {
                continue;
            }
            JSONObject item = new JSONObject();
            item.put("time", time);
            item.put("label", label);
            item.put("disabled", alarm.optBoolean("disabled", false));
            alarms.put(item);
        }
        JSONObject payload = new JSONObject();
        payload.put("effective_date", exportDate);
        payload.put("roster_code", draftRosterCode == null ? "" : draftRosterCode.trim());
        payload.put("alarms", alarms);
        return payload;
    }

    private String parseDateTextToIso(String raw) {
        if (raw == null) {
            return "";
        }
        String text = raw.trim();
        if (text.isEmpty()) {
            return "";
        }
        if (SCHEDULE_GRID_DATE_RE.matcher(text).matches()) {
            Matcher ymd = Pattern.compile("^(\\d{4})-(\\d{2})-(\\d{2})$").matcher(text);
            if (ymd.matches()) {
                return text;
            }
            Matcher dmy = Pattern.compile("^(\\d{1,2})/(\\d{1,2})/(\\d{4})$").matcher(text);
            if (dmy.matches()) {
                int day = Integer.parseInt(dmy.group(1));
                int month = Integer.parseInt(dmy.group(2));
                int year = Integer.parseInt(dmy.group(3));
                return String.format(Locale.getDefault(), "%04d-%02d-%02d", year, month, day);
            }
        }
        return "";
    }

    private JSONArray copyJsonArray(JSONArray source) {
        try {
            return new JSONArray(source == null ? "[]" : source.toString());
        } catch (JSONException e) {
            return new JSONArray();
        }
    }

    private void showScheduleGridImportFailure(
            ScheduleGridAutoImporter.ImportResult result,
            String statusPrefix
    ) {
        String message = result == null ? "" : result.message;
        if (message == null || message.trim().isEmpty()) {
            message = "搵唔到當日更碼行位表";
        }
        String planDate = result == null ? "" : result.planDate;
        String rosterCode = result == null ? "" : result.rosterCode;
        draftAlarms = new JSONArray();
        draftDate = planDate == null ? "" : planDate;
        draftRosterCode = rosterCode == null ? "" : rosterCode;
        int cachedCount = AlarmStore.getScheduleGridVariants(activity).length();
        shiftEmptyMessage = cachedCount > 0
                ? message + "\n可按更碼選擇電話已下載行位表作今日行位"
                : message;
        AlarmScheduler.schedulePlan(activity, draftAlarms, draftDate, draftRosterCode);
        loadFromStore();
        render();
        statusView.setText(statusPrefix + "：" + message);
    }

    private LinearLayout.LayoutParams shiftEmptyMessageParams() {
        return new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(180)
        );
    }

    private TextView shiftEmptyMessageView(String message) {
        TextView view = new TextView(activity);
        view.setText(message == null ? "" : message);
        view.setTextSize(16);
        view.setGravity(Gravity.CENTER);
        view.setTextColor(0xFFB91C1C);
        view.setBackgroundColor(0xFFFFFFFF);
        view.setPadding(dp(12), dp(18), dp(12), dp(18));
        return view;
    }

    // ---------------------------------------------------------------- 更碼 variants

    private String shiftVariantButtonText() {
        int count = AlarmStore.getScheduleGridVariants(activity).length();
        if (count > 1) {
            return "更碼(" + count + ")";
        }
        return "更碼";
    }

    private boolean shouldApplyShiftVariantAsToday() {
        return !shiftEmptyMessage.trim().isEmpty()
                || draftAlarms.length() == 0
                || !Clock30.todayIso().equals(draftDate);
    }

    private void showShiftVariantDialog(boolean applyAsToday) {
        final ActivePlanSnapshot editBase = draftBaseSnapshot;
        JSONArray variants = AlarmStore.getScheduleGridVariants(activity);
        if (variants.length() == 0) {
            Toast.makeText(activity, "電話未有已匯入更碼", Toast.LENGTH_LONG).show();
            return;
        }
        String[] labels = new String[variants.length()];
        for (int i = 0; i < variants.length(); i++) {
            JSONObject variant = variants.optJSONObject(i);
            String date = variant == null ? "" : Clock30.formatPlanDate(variant.optString("plan_date", ""));
            String code = variant == null ? "" : variant.optString("roster_code", "");
            int count = variant == null ? 0 : variant.optInt("alarm_count", 0);
            String marker = code.equals(draftRosterCode) ? "✓ " : "";
            labels[i] = marker + code + "｜" + date + "｜" + count + " 個鬧鐘";
        }
        new AlertDialog.Builder(activity)
                .setTitle(applyAsToday ? "匯入失敗：選擇今日更碼" : "選擇更碼")
                .setItems(labels, (dialog, which) -> {
                    if (requireCurrentDraft(editBase)) {
                        applyShiftVariant(variants.optJSONObject(which), applyAsToday);
                    }
                })
                .show();
    }

    private void applyShiftVariant(JSONObject variant, boolean applyAsToday) {
        if (variant == null) {
            return;
        }
        JSONArray alarms = variant.optJSONArray("alarms");
        if (alarms == null || alarms.length() == 0) {
            Toast.makeText(activity, "呢個更碼冇鬧鐘", Toast.LENGTH_LONG).show();
            return;
        }
        shiftEmptyMessage = "";
        String planDate = applyAsToday ? Clock30.todayIso() : variant.optString("plan_date", draftDate);
        draftAlarms = applyAsToday ? copyAlarmsForDate(alarms, planDate) : copyJsonArray(alarms);
        draftDate = planDate;
        draftRosterCode = variant.optString("roster_code", draftRosterCode);
        if (!saveDraftAlarms()) {
            return;
        }
        Toast.makeText(
                activity,
                applyAsToday
                        ? "已用快取更碼 " + draftRosterCode + " 作今日行位"
                        : "已套用更碼 " + draftRosterCode,
                Toast.LENGTH_LONG
        ).show();
    }

    /**
     * 快取更碼嘅鬧鐘照抄落目標日：時分照舊。
     * 30 小時制：source 喺凌晨 00–05 時（即 24:00–29:59 行位）係「翌日凌晨」，
     * 抄落目標日要 +1 日——以前直接落目標日凌晨，早咗一日。
     */
    private JSONArray copyAlarmsForDate(JSONArray alarms, String dateIso) {
        JSONArray copied = new JSONArray();
        int[] dateParts = parseIsoDateParts(dateIso);
        for (int i = 0; i < alarms.length(); i++) {
            JSONObject source = alarms.optJSONObject(i);
            if (source == null) {
                continue;
            }
            long sourceAt = source.optLong("trigger_at_epoch_ms", 0L);
            Calendar sourceCal = Calendar.getInstance();
            sourceCal.setTimeInMillis(sourceAt > 0L ? sourceAt : System.currentTimeMillis());

            Calendar targetCal = Calendar.getInstance();
            targetCal.set(Calendar.YEAR, dateParts[0]);
            targetCal.set(Calendar.MONTH, dateParts[1] - 1);
            targetCal.set(Calendar.DAY_OF_MONTH, dateParts[2]);
            targetCal.set(Calendar.HOUR_OF_DAY, sourceCal.get(Calendar.HOUR_OF_DAY));
            targetCal.set(Calendar.MINUTE, sourceCal.get(Calendar.MINUTE));
            targetCal.set(Calendar.SECOND, 0);
            targetCal.set(Calendar.MILLISECOND, 0);
            if (sourceCal.get(Calendar.HOUR_OF_DAY) < 6) {
                targetCal.add(Calendar.DAY_OF_MONTH, 1);
            }

            JSONObject target = new JSONObject();
            try {
                target.put("id", "cached-" + dateIso + "-" + i + "-" + targetCal.getTimeInMillis());
                target.put("label", source.optString("label", "鬧鐘"));
                target.put("trigger_at_epoch_ms", targetCal.getTimeInMillis());
                target.put("trigger_at", formatIso(targetCal.getTimeInMillis()));
                // 停用咗嘅行位要跟住過去，否則用快取更碼作今日行位會令佢哋變返啟用。
                target.put("disabled", source.optBoolean("disabled", false));
            } catch (JSONException ignored) {
            }
            copied.put(target);
        }
        return copied;
    }

    private int[] parseIsoDateParts(String dateIso) {
        String value = dateIso == null ? "" : dateIso.trim();
        if (value.matches("\\d{4}-\\d{2}-\\d{2}")) {
            try {
                return new int[]{
                        Integer.parseInt(value.substring(0, 4)),
                        Integer.parseInt(value.substring(5, 7)),
                        Integer.parseInt(value.substring(8, 10))
                };
            } catch (NumberFormatException ignored) {
            }
        }
        Calendar now = Calendar.getInstance();
        return new int[]{
                now.get(Calendar.YEAR),
                now.get(Calendar.MONTH) + 1,
                now.get(Calendar.DAY_OF_MONTH)
        };
    }

    private String formatHeader() {
        String datePart = Clock30.formatPlanDate(draftDate);
        String code = draftRosterCode == null ? "" : draftRosterCode.trim();
        if (!datePart.isEmpty() && !code.isEmpty()) {
            return datePart + " " + code;
        }
        if (!datePart.isEmpty()) {
            return datePart;
        }
        if (!code.isEmpty()) {
            return code;
        }
        return "未同步行位表";
    }

    private String statusText() {
        StringBuilder text = new StringBuilder();
        text.append("已自動更新：");
        text.append(draftAlarms.length()).append(" 個鬧鐘");
        text.append("｜餐單：").append(mealPlanStatus.isConnected() ? "已連線" : "未連線");
        text.append("\nLast import: ").append(formatLastImportAt());
        return text.toString();
    }

    private String formatLastImportAt() {
        long lastImportAt = AlarmStore.getLastImportAt(activity);
        if (lastImportAt <= 0L) {
            return "--";
        }
        return Clock30.formatDateTime(lastImportAt);
    }

    // ---------------------------------------------------------------- 表格

    private LinearLayout headerRow() {
        LinearLayout row = baseRow(0xFF8ED3EA);
        row.addView(iconCell(0xFF8ED3EA));
        row.addView(cell("時間", 13, Gravity.CENTER, 0.78f, 0xFF000000, 0xFF8ED3EA));
        row.addView(cell("內容", 13, Gravity.CENTER, 2.17f, 0xFF000000, 0xFF8ED3EA));
        row.addView(cell("操作", 13, Gravity.CENTER, 0.55f, 0xFF000000, 0xFF8ED3EA));
        return row;
    }

    private LinearLayout alarmRow(int index, JSONObject alarm) {
        LinearLayout row = baseRow(0xFFFFFFFF);
        boolean disabled = alarm.optBoolean("disabled", false);
        boolean dimmed = disabled || shouldDimAlarm(alarm);
        row.setAlpha(dimmed ? 0.45f : 1f);
        // 插入／刪除搬咗入 long-press menu，唔再佔住成行位置。
        // 每個 cell 各自有 click listener，會食咗 touch，所以要逐個都掛埋 long-click。
        android.view.View.OnLongClickListener longPress = v -> {
            showRowMenu(index);
            return true;
        };
        row.setOnLongClickListener(longPress);

        ImageView icon = alarmIconCell();
        icon.setOnClickListener(v -> editTime(index));
        icon.setOnLongClickListener(longPress);
        row.addView(icon);

        TextView time = cell(
                clockOnly(alarm.optLong("trigger_at_epoch_ms")),
                13,
                Gravity.RIGHT | Gravity.CENTER_VERTICAL,
                0.78f,
                0xFF000000,
                0xFFFFFFFF
        );
        time.setOnClickListener(v -> editTime(index));
        time.setOnLongClickListener(longPress);
        row.addView(time);

        TextView label = cell(
                alarm.optString("label", "鬧鐘"),
                13,
                Gravity.LEFT | Gravity.CENTER_VERTICAL,
                2.17f,
                0xFF000000,
                0xFFFFFFFF
        );
        label.setOnClickListener(v -> editLabel(index));
        label.setOnLongClickListener(longPress);
        row.addView(label);

        LinearLayout actions = new LinearLayout(activity);
        actions.setOrientation(LinearLayout.HORIZONTAL);
        actions.setGravity(Gravity.CENTER);
        actions.setBackgroundColor(0xFFFFFFFF);
        actions.setPadding(dp(2), dp(3), dp(2), dp(3));
        actions.setOnLongClickListener(longPress);
        actions.addView(statePill(!disabled, () -> toggleAlarmDisabled(index), longPress));
        row.addView(actions, weightedParams(0.55f));
        return row;
    }

    private void addBlankRows(int count) {
        for (int i = 0; i < count; i++) {
            LinearLayout row = baseRow(0xFFFFFFFF);
            row.addView(iconCell(0xFFFFFFFF));
            row.addView(cell("", 13, Gravity.CENTER, 0.78f, 0xFF000000, 0xFFFFFFFF));
            row.addView(cell("", 13, Gravity.CENTER, 2.17f, 0xFF000000, 0xFFFFFFFF));
            row.addView(cell("", 13, Gravity.CENTER, 0.55f, 0xFF000000, 0xFFFFFFFF));
            tableView.addView(row, fullWidthWrapHeight());
        }
    }

    private LinearLayout baseRow(int backgroundColor) {
        LinearLayout row = new LinearLayout(activity);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setBackgroundColor(backgroundColor);
        return row;
    }

    private ImageView iconCell(int backgroundColor) {
        ImageView view = new ImageView(activity);
        view.setBackgroundColor(backgroundColor);
        view.setPadding(dp(5), dp(5), dp(2), dp(5));
        view.setLayoutParams(iconCellParams());
        return view;
    }

    private ImageView alarmIconCell() {
        ImageView view = new ImageView(activity);
        view.setImageResource(android.R.drawable.ic_lock_idle_alarm);
        view.setColorFilter(0xFF0F172A);
        view.setBackgroundColor(0xFFFFFFFF);
        view.setPadding(dp(5), dp(5), dp(2), dp(5));
        view.setLayoutParams(iconCellParams());
        return view;
    }

    private LinearLayout.LayoutParams iconCellParams() {
        return new LinearLayout.LayoutParams(dp(26), dp(28));
    }

    private TextView cell(String text, int size, int gravity, float weight, int color, int background) {
        TextView view = new TextView(activity);
        view.setText(text);
        view.setTextSize(size);
        view.setGravity(gravity);
        view.setTextColor(color);
        view.setBackgroundColor(background);
        view.setSingleLine(false);
        view.setPadding(dp(3), dp(1), dp(3), dp(1));
        view.setMinHeight(dp(28));
        view.setLayoutParams(weightedParams(weight));
        return view;
    }

    /** 行位啟用狀態掣：ON＝淺藍、OFF＝淺灰，撳一下 toggle（唔用系統灰方掣，成張表清爽啲）。 */
    private TextView statePill(
            boolean enabled,
            Runnable action,
            android.view.View.OnLongClickListener longPress
    ) {
        TextView pill = new TextView(activity);
        pill.setText(enabled ? "ON" : "OFF");
        pill.setTextSize(10);
        pill.setGravity(Gravity.CENTER);
        pill.setTextColor(enabled ? 0xFF0C447C : 0xFF5F5E5A);
        pill.setBackground(roundedBg(enabled ? 0xFFE6F1FB : 0xFFF1EFE8, 11, 0, 0));
        pill.setPadding(dp(10), dp(3), dp(10), dp(3));
        pill.setOnClickListener(v -> action.run());
        pill.setOnLongClickListener(longPress);
        return pill;
    }

    private boolean shouldDimAlarm(JSONObject alarm) {
        if (alarm == null) {
            return false;
        }
        return alarm.optLong("fired_at_epoch_ms", 0L) > 0L
                || alarm.optLong("trigger_at_epoch_ms", Long.MAX_VALUE) <= System.currentTimeMillis();
    }

    // ---------------------------------------------------------------- 編輯

    /**
     * 改時間（30 小時制）：表格顯示 27:00，輸入亦收 0–29 時。
     * 凌晨 00–05 嘅鬧鐘先退一日做「更日」基準，再按輸入 24–29 → 翌日 00–05 計返。
     */
    private void editTime(int index) {
        final ActivePlanSnapshot editBase = draftBaseSnapshot;
        JSONObject alarm = draftAlarms.optJSONObject(index);
        if (alarm == null) {
            return;
        }
        Calendar cal = Calendar.getInstance();
        cal.setTimeInMillis(alarm.optLong("trigger_at_epoch_ms"));
        int hour30 = cal.get(Calendar.HOUR_OF_DAY);
        if (hour30 < 6) {
            cal.add(Calendar.DAY_OF_MONTH, -1);
            hour30 += 24;
        }
        ui.showTimeDialog("Select time", hour30, cal.get(Calendar.MINUTE), null, null, (hour, minute) -> {
            if (!requireCurrentDraft(editBase)) {
                return;
            }
            int dayOffset = hour >= 24 ? 1 : 0;
            cal.add(Calendar.DAY_OF_MONTH, dayOffset);
            cal.set(Calendar.HOUR_OF_DAY, hour - dayOffset * 24);
            cal.set(Calendar.MINUTE, minute);
            cal.set(Calendar.SECOND, 0);
            cal.set(Calendar.MILLISECOND, 0);
            setAlarmTime(index, cal.getTimeInMillis());
        });
    }

    private void editLabel(int index) {
        final ActivePlanSnapshot editBase = draftBaseSnapshot;
        JSONObject alarm = draftAlarms.optJSONObject(index);
        if (alarm == null) {
            return;
        }
        EditText input = new EditText(activity);
        input.setSingleLine(false);
        input.setMinLines(1);
        input.setText(alarm.optString("label", "鬧鐘"));
        new AlertDialog.Builder(activity)
                .setTitle("內容")
                .setView(input)
                .setNegativeButton("Cancel", null)
                .setPositiveButton("OK", (dialog, which) -> {
                    if (!requireCurrentDraft(editBase)) {
                        return;
                    }
                    String label = input.getText() == null ? "" : input.getText().toString().trim();
                    setAlarmLabel(index, label.isEmpty() ? "鬧鐘" : label);
                })
                .show();
    }

    private void setAlarmTime(int index, long millis) {
        JSONObject alarm = draftAlarms.optJSONObject(index);
        if (alarm == null) {
            return;
        }
        try {
            alarm.put("trigger_at_epoch_ms", millis);
            alarm.put("trigger_at", formatIso(millis));
            alarm.remove("fired_at_epoch_ms");
            sortDraftAlarms();
            saveDraftAlarms();
        } catch (JSONException e) {
            Toast.makeText(activity, "更新時間失敗", Toast.LENGTH_SHORT).show();
        }
    }

    /** Long-press 一行出 menu：插入／刪除。 */
    private void showRowMenu(int index) {
        final ActivePlanSnapshot editBase = draftBaseSnapshot;
        JSONObject alarm = draftAlarms.optJSONObject(index);
        if (alarm == null) {
            return;
        }
        String title = clockOnly(alarm.optLong("trigger_at_epoch_ms")) + "  " + alarm.optString("label", "");
        new AlertDialog.Builder(activity)
                .setTitle(title)
                .setItems(new CharSequence[]{"插入一行", "刪除呢行"}, (dialog, which) -> {
                    if (!requireCurrentDraft(editBase)) {
                        return;
                    }
                    if (which == 0) {
                        insertAlarm(index);
                    } else {
                        deleteDraftAlarm(index);
                    }
                })
                .setNegativeButton("Cancel", null)
                .show();
    }

    /** 停用／啟用一格行位：唔會響鬧鐘、唔佔時長，但留喺表入面撳得返。 */
    private void toggleAlarmDisabled(int index) {
        JSONObject alarm = draftAlarms.optJSONObject(index);
        if (alarm == null) {
            return;
        }
        try {
            alarm.put("disabled", !alarm.optBoolean("disabled", false));
            saveDraftAlarms();
        } catch (JSONException e) {
            Toast.makeText(activity, "更新停用狀態失敗", Toast.LENGTH_SHORT).show();
        }
    }

    /**
     * 重算時長：一格嘅時長 ＝ 去下一個「佔時間」行嘅距離。
     * `-` 開頭嘅 marker 行同停用行都唔佔時間，前一格跨過佢哋。
     * `*` 開頭嘅星號行照佔時間，但 label 係人手打嘅（尾數＝固定時長），停用與否都唔改。
     * 插入／刪除／停用／改時間之後行一次，成張表啲數跟住啱返。
     */
    private void recomputeDraftDurations() {
        java.util.List<JSONObject> live = new java.util.ArrayList<>();
        for (int i = 0; i < draftAlarms.length(); i++) {
            JSONObject alarm = draftAlarms.optJSONObject(i);
            if (alarm == null) {
                continue;
            }
            String label = alarm.optString("label", "");
            String content = splitLabelContent(label);
            if (alarm.optBoolean("disabled", false) || content.startsWith("-")) {
                if (!isStarLabel(label)) {
                    setLabelDuration(alarm, content, -1);
                }
                continue;
            }
            live.add(alarm);
        }
        for (int i = 0; i < live.size(); i++) {
            JSONObject alarm = live.get(i);
            String label = alarm.optString("label", "");
            if (isStarLabel(label)) {
                continue;
            }
            String content = splitLabelContent(label);
            if (i + 1 >= live.size()) {
                setLabelDuration(alarm, content, -1);
                continue;
            }
            long gap = live.get(i + 1).optLong("trigger_at_epoch_ms", 0L)
                    - alarm.optLong("trigger_at_epoch_ms", 0L);
            setLabelDuration(alarm, content, gap > 0 ? (int) (gap / 60000L) : -1);
        }
    }

    /**
     * 星號行推下一行時間（同網頁 applyScheduleGridStarRows 一樣）：由星號行向下搵
     * 第一個唔係 `-`／`*` 開頭嘅行（停用與否唔理），時間改做「星號行時間 + 尾數」。
     * 要喺 sort 之前行——咁「向下」先係改時間之前嘅行序。
     */
    private void pushRowsAfterStarRows() {
        for (int i = 0; i < draftAlarms.length(); i++) {
            JSONObject star = draftAlarms.optJSONObject(i);
            if (star == null) {
                continue;
            }
            int minutes = starMinutes(star.optString("label", ""));
            long start = star.optLong("trigger_at_epoch_ms", 0L);
            if (minutes < 0 || start <= 0L) {
                continue;
            }
            long next = start + minutes * 60000L;
            for (int j = i + 1; j < draftAlarms.length(); j++) {
                JSONObject candidate = draftAlarms.optJSONObject(j);
                if (candidate == null) {
                    continue;
                }
                String label = candidate.optString("label", "").trim();
                if (label.startsWith("-") || label.startsWith("*")) {
                    continue;
                }
                if (candidate.optLong("trigger_at_epoch_ms", 0L) != next) {
                    try {
                        candidate.put("trigger_at_epoch_ms", next);
                        candidate.put("trigger_at", formatIso(next));
                    } catch (JSONException ignored) {
                    }
                }
                break;
            }
        }
    }

    private static boolean isStarLabel(String label) {
        return label != null && label.trim().startsWith("*");
    }

    /** 「* 飯 55」→ 55；唔係星號行或者冇尾數 → -1（當普通行計）。 */
    private static int starMinutes(String label) {
        Matcher matcher = STAR_DURATION_RE.matcher(label == null ? "" : label.trim());
        return matcher.matches() ? Integer.parseInt(matcher.group(1)) : -1;
    }

    /** 「M 75」→「M」；冇尾數就原樣。 */
    private static String splitLabelContent(String label) {
        String text = label == null ? "" : label.trim();
        Matcher matcher = Pattern.compile("\\s+\\d{1,3}$").matcher(text);
        if (!matcher.find()) {
            return text;
        }
        String content = text.substring(0, matcher.start()).trim();
        return content.isEmpty() ? text : content;
    }

    private void setLabelDuration(JSONObject alarm, String content, int minutes) {
        try {
            alarm.put("label", minutes > 0 ? content + " " + minutes : content);
        } catch (JSONException ignored) {
        }
    }

    private void setAlarmLabel(int index, String label) {
        JSONObject alarm = draftAlarms.optJSONObject(index);
        if (alarm == null) {
            return;
        }
        try {
            alarm.put("label", label);
            saveDraftAlarms();
        } catch (JSONException e) {
            Toast.makeText(activity, "更新內容失敗", Toast.LENGTH_SHORT).show();
        }
    }

    private void insertAlarm(int index) {
        JSONObject source = draftAlarms.optJSONObject(index);
        long baseTime = source == null ? nextDefaultTime() : source.optLong("trigger_at_epoch_ms", nextDefaultTime());
        JSONObject created = newAlarm(baseTime - 5 * 60 * 1000L, "新鬧鐘");
        JSONArray next = new JSONArray();
        for (int i = 0; i < draftAlarms.length(); i++) {
            if (i == index) {
                next.put(created);
            }
            JSONObject alarm = draftAlarms.optJSONObject(i);
            if (alarm != null) {
                next.put(alarm);
            }
        }
        draftAlarms = next;
        sortDraftAlarms();
        saveDraftAlarms();
    }

    private void appendAlarm() {
        long base = nextDefaultTime();
        if (draftAlarms.length() > 0) {
            JSONObject last = draftAlarms.optJSONObject(draftAlarms.length() - 1);
            if (last != null) {
                long lastTriggerAt = last.optLong("trigger_at_epoch_ms", 0L);
                if (lastTriggerAt > System.currentTimeMillis() && Clock30.todayIso().equals(draftDate)) {
                    base = lastTriggerAt + 5 * 60 * 1000L;
                }
            }
        }
        draftAlarms.put(newAlarm(base, "新鬧鐘"));
        sortDraftAlarms();
        saveDraftAlarms();
    }

    private void appendTodayAlarm() {
        draftAlarms.put(newAlarm(nextDefaultTime(), "新鬧鐘"));
        sortDraftAlarms();
        saveDraftAlarms();
    }

    private JSONObject newAlarm(long millis, String label) {
        JSONObject alarm = new JSONObject();
        try {
            alarm.put("id", "edit-" + millis + "-" + System.currentTimeMillis());
            alarm.put("label", label);
            alarm.put("trigger_at_epoch_ms", millis);
            alarm.put("trigger_at", formatIso(millis));
        } catch (JSONException ignored) {
        }
        return alarm;
    }

    private long nextDefaultTime() {
        Calendar cal = Calendar.getInstance();
        cal.add(Calendar.MINUTE, 1);
        cal.set(Calendar.SECOND, 0);
        cal.set(Calendar.MILLISECOND, 0);
        return cal.getTimeInMillis();
    }

    private void deleteDraftAlarm(int index) {
        JSONArray next = new JSONArray();
        for (int i = 0; i < draftAlarms.length(); i++) {
            JSONObject alarm = draftAlarms.optJSONObject(i);
            if (alarm != null && i != index) {
                next.put(alarm);
            }
        }
        draftAlarms = next;
        saveDraftAlarms();
    }

    private boolean saveDraftAlarms() {
        if (!requireCurrentDraft(draftBaseSnapshot)) {
            return false;
        }
        if (!AlarmScheduler.canScheduleExactAlarm(activity)) {
            Toast.makeText(activity, "請先允許精準鬧鐘權限", Toast.LENGTH_LONG).show();
            AlarmScheduler.requestExactAlarmPermission(activity);
            render();
            return false;
        }
        shiftEmptyMessage = "";
        pushRowsAfterStarRows();
        sortDraftAlarms();
        recomputeDraftDurations();
        synchronized (AlarmStore.class) {
            // 同背景 importer 共用同步區，核對後不可插入另一份新 plan 再被舊 draft 蓋掉。
            if (!requireCurrentDraft(draftBaseSnapshot)) {
                return false;
            }
            if (draftAlarms.length() == 0) {
                AlarmScheduler.cancelAll(activity);
            } else {
                AlarmScheduler.schedulePlan(activity, draftAlarms, draftDate, draftRosterCode);
            }
        }
        loadFromStore();
        render();
        return true;
    }

    private void sortDraftAlarms() {
        ArrayList<JSONObject> items = new ArrayList<>();
        for (int i = 0; i < draftAlarms.length(); i++) {
            JSONObject alarm = draftAlarms.optJSONObject(i);
            if (alarm != null) {
                items.add(alarm);
            }
        }
        items.sort(Comparator.comparingLong(a -> a.optLong("trigger_at_epoch_ms", 0L)));
        JSONArray sorted = new JSONArray();
        for (JSONObject item : items) {
            sorted.put(item);
        }
        draftAlarms = sorted;
    }

    private String clockOnly(long millis) {
        return Clock30.format(millis);
    }

    private String formatIso(long millis) {
        return new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ssZ", Locale.getDefault()).format(millis);
    }

    // ---- 共用 UI 工廠：薄 delegate 落 PanelUi ----

    private int dp(int value) {
        return ui.dp(value);
    }

    private android.graphics.drawable.GradientDrawable roundedBg(int fillColor, int radiusDp, int strokeColor, int strokeDp) {
        return ui.roundedBg(fillColor, radiusDp, strokeColor, strokeDp);
    }

    private LinearLayout.LayoutParams fullWidthWrapHeight() {
        return ui.fullWidth();
    }

    private LinearLayout.LayoutParams weightedParams(float weight) {
        return ui.weighted(weight);
    }
}
