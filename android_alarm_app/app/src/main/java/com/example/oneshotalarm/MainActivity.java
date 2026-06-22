package com.example.oneshotalarm;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.app.NotificationManager;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.text.Editable;
import android.text.InputFilter;
import android.text.InputType;
import android.text.TextWatcher;
import android.util.Log;
import android.view.Gravity;
import android.view.View;
import android.view.Window;
import android.view.WindowInsets;
import android.view.inputmethod.InputMethodManager;
import android.widget.Button;
import android.widget.EditText;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.Node;
import org.w3c.dom.NodeList;
import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Calendar;
import java.util.Comparator;
import java.util.HashSet;
import java.util.Locale;
import java.util.TimeZone;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import javax.xml.parsers.DocumentBuilderFactory;

public class MainActivity extends Activity {
    private static final String TAG = "OneShotAlarm";
    private static final String EXPORT_FILE_NAME = "export.xml";
    private static final int HTTP_CONNECT_TIMEOUT_MS = 4000;
    private static final int HTTP_READ_TIMEOUT_MS = 7000;
    private static final int PAGE_MEAL = 0;
    private static final int PAGE_SHIFT = 1;
    private static final String ACTION_TEST_DAILY_IMPORT = "com.example.oneshotalarm.ACTION_TEST_DAILY_IMPORT";
    private static final Pattern TIME_RE = Pattern.compile("^\\d{1,2}:\\d{2}$");
    private static final Pattern SCHEDULE_GRID_HEADER_RE = Pattern.compile(
            "^\\s*(\\d{4}-\\d{2}-\\d{2}|(\\d{1,2})/(\\d{1,2})/(\\d{4}))\\s+(.+)\\s*$"
    );
    private static final Pattern SCHEDULE_GRID_DATE_RE = Pattern.compile(
            "^\\s*(\\d{4}-\\d{2}-\\d{2}|(\\d{1,2})/(\\d{1,2})/(\\d{4}))\\s*$"
    );
    private static final HashSet<String> XML_NOISE_TEXTS = new HashSet<>();

    static {
        XML_NOISE_TEXTS.add("時間");
        XML_NOISE_TEXTS.add("內容");
        XML_NOISE_TEXTS.add("操作");
        XML_NOISE_TEXTS.add("插入");
        XML_NOISE_TEXTS.add("刪除");
        XML_NOISE_TEXTS.add("刪除全部");
        XML_NOISE_TEXTS.add("append");
        XML_NOISE_TEXTS.add("append all");
        XML_NOISE_TEXTS.add("insert");
        XML_NOISE_TEXTS.add("delete");
        XML_NOISE_TEXTS.add("delete all");
        XML_NOISE_TEXTS.add("sync");
        XML_NOISE_TEXTS.add("synchronize");
    }

    private TextView headerView;
    private TextView statusView;
    private TextView mealPlanView;
    private TextView mealDateView;
    private LinearLayout tableView;
    private LinearLayout mealSection;
    private LinearLayout mealSummaryView;
    private LinearLayout mealCardsView;
    private LinearLayout shiftSection;
    private Button mealTabButton;
    private Button shiftTabButton;
    private Button importXmlButton;
    private Button shiftVariantButton;
    private Button watchAlarmToggleButton;
    private Button aodToggleButton;
    private TextView mealLastUpdateTitleView;
    private TextView mealLastUpdateStatusView;
    private JSONArray draftAlarms = new JSONArray();
    private String draftDate = "";
    private String draftRosterCode = "";
    private String shiftEmptyMessage = "";
    private String mealPlanText = "";
    private JSONObject mealPlanJson;
    private String mealPlanJsonDate = "";
    private String mealPlanJsonVersion = "";
    private String mealSelectedDate = "";
    private String mealKnownLastDate = "";
    private String mealExpandedKey = "";
    private String mealFetchErrorText = "";
    private long mealLastFetchAtMs = 0L;
    private boolean mealFetchInFlight = false;
    private int currentPage = PAGE_MEAL;
    private float mealSwipeDownX = 0f;
    private float mealSwipeDownY = 0f;
    private android.graphics.Typeface mealRegularTypeface;
    private android.graphics.Typeface mealMediumTypeface;
    private boolean kitchenModeEnabled = false;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        configureSystemBars();
        PhoneScheduleGridHttpServer.start(this);
        buildUi();
        applyAodState(false);
        loadDraftFromStore();
        render();
        handleTestDailyImportIntent(getIntent());
        NextAlarmWidgetProvider.updateAll(this);
        requestNotificationPermissionIfNeeded();
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        loadDraftFromStore();
        render();
        handleTestDailyImportIntent(intent);
    }

    @Override
    protected void onResume() {
        super.onResume();
        loadDraftFromStore();
        render();
        NextAlarmWidgetProvider.updateAll(this);
        if (currentPage == PAGE_MEAL) {
            fetchMealPlanForSelectedDate();
        }
    }

    @Override
    public boolean dispatchTouchEvent(android.view.MotionEvent ev) {
        if (currentPage == PAGE_MEAL) {
            if (ev.getAction() == android.view.MotionEvent.ACTION_DOWN) {
                mealSwipeDownX = ev.getX();
                mealSwipeDownY = ev.getY();
            } else if (ev.getAction() == android.view.MotionEvent.ACTION_UP) {
                float dx = ev.getX() - mealSwipeDownX;
                float dy = ev.getY() - mealSwipeDownY;
                float threshold = dp(72);
                if (Math.abs(dx) > threshold && Math.abs(dx) > Math.abs(dy) * 1.8f) {
                    shiftMealDate(dx < 0 ? 1 : -1);
                    return true;
                }
            }
        }
        return super.dispatchTouchEvent(ev);
    }

    private void buildUi() {
        ScrollView scrollView = new ScrollView(this);
        scrollView.setFillViewport(true);
        scrollView.setClipToPadding(false);
        scrollView.setVerticalScrollBarEnabled(true);
        scrollView.setScrollbarFadingEnabled(false);
        scrollView.setBackgroundColor(0xFFFFFFFF);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(0, 0, 0, 0);
        root.setBackgroundColor(0xFFFFFFFF);

        TextView title = new TextView(this);
        title.setText("門前直樹");
        title.setTextSize(15);
        title.setTextColor(0xFF053B24);
        title.setTypeface(mealBoldTypeface());
        title.setGravity(Gravity.CENTER);
        title.setPadding(dp(6), dp(0), dp(6), dp(1));
        root.addView(title, fullWidthWrapHeight());

        TextView versionTag = new TextView(this);
        versionTag.setText("");
        versionTag.setTextSize(1);
        versionTag.setTextColor(0xFF64748B);
        versionTag.setTypeface(mealTypeface());
        versionTag.setGravity(Gravity.CENTER);
        versionTag.setPadding(dp(6), 0, dp(6), dp(3));
        root.addView(versionTag, fullWidthWrapHeight());

        LinearLayout tabRow = new LinearLayout(this);
        tabRow.setOrientation(LinearLayout.HORIZONTAL);
        tabRow.setPadding(dp(8), 0, dp(8), dp(1));
        tabRow.setBackgroundColor(0xFFFBF8EF);

        mealTabButton = buildTopTabButton("餐單");
        shiftTabButton = buildTopTabButton("行位表");
        mealTabButton.setOnClickListener(v -> switchPage(PAGE_MEAL));
        shiftTabButton.setOnClickListener(v -> switchPage(PAGE_SHIFT));
        tabRow.addView(mealTabButton, weightedParams(1f));
        tabRow.addView(shiftTabButton, weightedParams(1f));
        root.addView(tabRow, fullWidthWrapHeight());

        mealSection = new LinearLayout(this);
        mealSection.setOrientation(LinearLayout.VERTICAL);
        mealSection.setPadding(dp(10), 0, dp(10), dp(10));
        mealSection.setBackgroundColor(0xFFFBF8EF);

        LinearLayout mealDateBar = new LinearLayout(this);
        mealDateBar.setOrientation(LinearLayout.HORIZONTAL);
        mealDateBar.setGravity(Gravity.CENTER_VERTICAL);
        mealDateBar.setPadding(0, 0, 0, 0);

        mealDateView = new TextView(this);
        mealDateView.setTextSize(17);
        mealDateView.setGravity(Gravity.START | Gravity.CENTER_VERTICAL);
        mealDateView.setTextColor(0xFF064E2D);
        mealDateView.setTypeface(mealBoldTypeface());
        mealDateView.setIncludeFontPadding(false);
        mealDateView.setSingleLine(true);
        mealDateView.setPadding(dp(6), 0, dp(6), 0);
        mealDateView.setLayoutParams(weightedParams(1.8f));
        mealDateBar.addView(mealDateView);

        Button mealTodayButton = bottomButton("今日");
        mealTodayButton.setTextColor(0xFF0B3D5A);
        mealTodayButton.setTypeface(mealBoldTypeface());
        mealTodayButton.setBackground(roundedBg(0xFFFFFFFF, 14, 0xFF7FB9D6, 1));
        mealTodayButton.setOnClickListener(v -> setMealDate(todayIso(), true));
        LinearLayout.LayoutParams todayParams = new LinearLayout.LayoutParams(dp(64), dp(34));
        todayParams.setMargins(dp(8), 0, 0, 0);
        mealDateBar.addView(mealTodayButton, todayParams);

        mealSection.addView(mealDateBar, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(40)
        ));

        mealPlanView = new TextView(this);
        mealPlanView.setTextSize(10);
        mealPlanView.setTextColor(0xFF526D7A);
        mealPlanView.setTypeface(mealTypeface());
        mealPlanView.setLineSpacing(1.3f, 1.2f);
        mealPlanView.setSingleLine(false);
        mealPlanView.setPadding(dp(4), 0, dp(4), dp(3));
        mealPlanView.setVisibility(View.GONE);
        mealSection.addView(mealPlanView, fullWidthWrapHeight());

        mealSummaryView = new LinearLayout(this);
        mealSummaryView.setOrientation(LinearLayout.VERTICAL);
        mealSummaryView.setPadding(0, 0, 0, dp(3));
        mealSection.addView(mealSummaryView, fullWidthWrapHeight());

        mealCardsView = new LinearLayout(this);
        mealCardsView.setOrientation(LinearLayout.VERTICAL);
        mealSection.addView(mealCardsView, fullWidthWrapHeight());

        LinearLayout mealActionBar = new LinearLayout(this);
        mealActionBar.setOrientation(LinearLayout.HORIZONTAL);
        mealActionBar.setGravity(Gravity.CENTER_VERTICAL);
        mealActionBar.setPadding(0, 0, 0, 0);
        aodToggleButton = bottomButton("AOD OFF");
        aodToggleButton.setTextSize(15);
        aodToggleButton.setTypeface(mealBoldTypeface());
        aodToggleButton.setOnClickListener(v -> toggleKitchenMode());
        mealActionBar.addView(aodToggleButton, new LinearLayout.LayoutParams(0, dp(38), 0.85f));

        LinearLayout lastUpdateColumn = new LinearLayout(this);
        lastUpdateColumn.setOrientation(LinearLayout.VERTICAL);
        lastUpdateColumn.setGravity(Gravity.CENTER_VERTICAL);
        lastUpdateColumn.setPadding(dp(10), 0, 0, 0);
        mealLastUpdateTitleView = new TextView(this);
        mealLastUpdateTitleView.setText("Last update");
        mealLastUpdateTitleView.setTextSize(10);
        mealLastUpdateTitleView.setTextColor(0xFF36505D);
        mealLastUpdateTitleView.setTypeface(mealTypeface());
        mealLastUpdateTitleView.setIncludeFontPadding(false);
        mealLastUpdateTitleView.setGravity(Gravity.LEFT);
        lastUpdateColumn.addView(mealLastUpdateTitleView, fullWidthWrapHeight());
        mealLastUpdateStatusView = new TextView(this);
        mealLastUpdateStatusView.setTextSize(10);
        mealLastUpdateStatusView.setTextColor(0xFF36505D);
        mealLastUpdateStatusView.setTypeface(mealTypeface());
        mealLastUpdateStatusView.setGravity(Gravity.LEFT);
        mealLastUpdateStatusView.setIncludeFontPadding(false);
        mealLastUpdateStatusView.setSingleLine(true);
        mealLastUpdateStatusView.setLineSpacing(0f, 1.0f);
        lastUpdateColumn.addView(mealLastUpdateStatusView, fullWidthWrapHeight());
        LinearLayout.LayoutParams updateParams = new LinearLayout.LayoutParams(0, dp(38), 1.15f);
        updateParams.setMargins(dp(8), 0, 0, 0);
        mealActionBar.addView(lastUpdateColumn, updateParams);
        LinearLayout.LayoutParams actionParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(38)
        );
        mealSection.addView(mealActionBar, actionParams);

        root.addView(mealSection, fullWidthWrapHeight());

        shiftSection = new LinearLayout(this);
        shiftSection.setOrientation(LinearLayout.VERTICAL);
        shiftSection.setPadding(0, 0, 0, 0);
        shiftSection.setBackgroundColor(0xFFFFFFFF);

        LinearLayout shiftHeaderBar = new LinearLayout(this);
        shiftHeaderBar.setOrientation(LinearLayout.HORIZONTAL);
        shiftHeaderBar.setGravity(Gravity.CENTER_VERTICAL);
        shiftHeaderBar.setPadding(dp(4), dp(1), dp(4), dp(2));
        shiftHeaderBar.setBackgroundColor(0xFFFFFFFF);

        headerView = new TextView(this);
        headerView.setTextSize(15);
        headerView.setTextColor(0xFF000000);
        headerView.setPadding(dp(4), dp(1), dp(6), dp(2));
        headerView.setBackgroundColor(0xFFFFFFFF);
        shiftHeaderBar.addView(headerView, weightedParams(1f));

        shiftVariantButton = bottomButton("更碼");
        shiftVariantButton.setTextSize(11);
        shiftVariantButton.setOnClickListener(v -> showShiftVariantDialog(shouldApplyShiftVariantAsToday()));
        shiftHeaderBar.addView(shiftVariantButton, new LinearLayout.LayoutParams(dp(92), dp(34)));

        shiftSection.addView(shiftHeaderBar, fullWidthWrapHeight());

        tableView = new LinearLayout(this);
        tableView.setOrientation(LinearLayout.VERTICAL);
        shiftSection.addView(tableView, fullWidthWrapHeight());

        LinearLayout bottom = new LinearLayout(this);
        bottom.setOrientation(LinearLayout.VERTICAL);
        bottom.setPadding(0, dp(1), 0, 0);
        bottom.setBackgroundColor(0xFFFFFFFF);

        LinearLayout bottomTop = new LinearLayout(this);
        bottomTop.setOrientation(LinearLayout.HORIZONTAL);
        bottomTop.setPadding(0, 0, 0, dp(1));

        importXmlButton = bottomButton("import");
        importXmlButton.setOnClickListener(v -> launchImportScheduleGridXml());
        bottomTop.addView(importXmlButton, weightedParams(1f));

        Button pushToPc = bottomButton("to Computer");
        pushToPc.setOnClickListener(v -> pushCurrentScheduleGridToPc());
        bottomTop.addView(pushToPc, weightedParams(1f));

        bottom.addView(bottomTop, fullWidthWrapHeight());

        LinearLayout bottomSecond = new LinearLayout(this);
        bottomSecond.setOrientation(LinearLayout.HORIZONTAL);
        bottomSecond.setPadding(0, 0, 0, 0);

        Button append = bottomButton("Append");
        append.setOnClickListener(v -> appendAlarm());
        bottomSecond.addView(append, weightedParams(1f));

        Button appendToday = bottomButton("今日+");
        appendToday.setOnClickListener(v -> appendTodayAlarm());
        bottomSecond.addView(appendToday, weightedParams(1f));

        watchAlarmToggleButton = bottomButton(watchAlarmButtonText());
        watchAlarmToggleButton.setOnClickListener(v -> toggleWatchAlarm());
        applyWatchAlarmButtonState();
        bottomSecond.addView(watchAlarmToggleButton, weightedParams(1f));

        bottom.addView(bottomSecond, fullWidthWrapHeight());

        shiftSection.addView(bottom, fullWidthWrapHeight());

        statusView = new TextView(this);
        statusView.setTextSize(9);
        statusView.setTextColor(0xFF475569);
        statusView.setGravity(Gravity.CENTER);
        statusView.setPadding(dp(8), dp(2), dp(8), dp(4));
        shiftSection.addView(statusView, fullWidthWrapHeight());

        root.addView(shiftSection, fullWidthWrapHeight());

        scrollView.addView(
                root,
                new ScrollView.LayoutParams(
                    ScrollView.LayoutParams.MATCH_PARENT,
                    ScrollView.LayoutParams.WRAP_CONTENT
                )
        );
        applySafeAreaPadding(scrollView);
        setContentView(scrollView);
        switchPage(currentPage);
    }

    private Button buildTopTabButton(String text) {
        Button button = new Button(this);
        button.setText(text);
        button.setAllCaps(false);
        button.setTextSize(13);
        button.setTypeface(mealBoldTypeface());
        button.setMinHeight(dp(34));
        button.setMinimumHeight(dp(34));
        button.setPadding(dp(8), 0, dp(8), 0);
        return button;
    }

    private String watchAlarmButtonText() {
        return AlarmStore.isWatchAlarmEnabled(this) ? "手錶ON" : "手錶OFF";
    }

    private void applyWatchAlarmButtonState() {
        if (watchAlarmToggleButton == null) {
            return;
        }
        boolean enabled = AlarmStore.isWatchAlarmEnabled(this);
        watchAlarmToggleButton.setText(watchAlarmButtonText());
        watchAlarmToggleButton.setAlpha(enabled ? 1f : 0.42f);
    }

    private void toggleWatchAlarm() {
        boolean enabled = !AlarmStore.isWatchAlarmEnabled(this);
        AlarmStore.setWatchAlarmEnabled(this, enabled);
        applyWatchAlarmButtonState();
        Toast.makeText(
                this,
                enabled ? "手錶鬧鐘已開" : "手錶鬧鐘已關",
                Toast.LENGTH_SHORT
        ).show();
    }

    private void switchPage(int page) {
        boolean wasMeal = currentPage == PAGE_MEAL;
        currentPage = page == PAGE_MEAL ? PAGE_MEAL : PAGE_SHIFT;
        updatePageVisibility();
        render();
        if (currentPage == PAGE_MEAL && !wasMeal) {
            fetchMealPlanForSelectedDate();
        }
    }

    private void updatePageVisibility() {
        if (mealSection == null || shiftSection == null
                || mealTabButton == null || shiftTabButton == null) {
            return;
        }
        boolean isMeal = currentPage == PAGE_MEAL;
        mealSection.setVisibility(isMeal ? View.VISIBLE : View.GONE);
        shiftSection.setVisibility(isMeal ? View.GONE : View.VISIBLE);

        mealTabButton.setBackgroundColor(isMeal ? 0xFF0B1026 : 0xFFDDEBF5);
        mealTabButton.setTextColor(isMeal ? 0xFFFFFFFF : 0xFF334155);
        shiftTabButton.setBackgroundColor(!isMeal ? 0xFF0B1026 : 0xFFDDEBF5);
        shiftTabButton.setTextColor(!isMeal ? 0xFFFFFFFF : 0xFF334155);
    }

    private void launchImportScheduleGridXml() {
        if (!AlarmScheduler.canScheduleExactAlarm(this)) {
            Toast.makeText(this, "請先允許精準鬧鐘權限，再匯入", Toast.LENGTH_LONG).show();
            AlarmScheduler.requestExactAlarmPermission(this);
            return;
        }
        statusView.setText("從電腦匯入全部更碼中...");
        new Thread(() -> {
            ScheduleGridAutoImporter.ImportResult result;
            try {
                result = ScheduleGridAutoImporter.importFromPc(this);
            } catch (Exception e) {
                result = new ScheduleGridAutoImporter.ImportResult(false, 0, "", "", e.getMessage());
            }
            ScheduleGridAutoImporter.ImportResult finalResult = result;
            runOnUiThread(() -> {
                if (finalResult.ok) {
                    shiftEmptyMessage = "";
                    loadDraftFromStore();
                    render();
                    String extra = finalResult.variantCount > 1
                            ? "，已載入 " + finalResult.variantCount + " 個更碼"
                            : "";
                    String message = "已從電腦匯入 " + finalResult.alarmCount + " 個鬧鐘" + extra;
                    statusView.setText(statusText());
                    Toast.makeText(this, message, Toast.LENGTH_LONG).show();
                } else {
                    showScheduleGridImportFailure(finalResult, "匯入失敗");
                }
            });
        }).start();
    }

    private void pushCurrentScheduleGridToPc() {
        String server = AlarmStore.getAutoSyncServerUrl(this);
        if (server == null || server.trim().isEmpty()) {
            Toast.makeText(this, "未設定電腦 server", Toast.LENGTH_LONG).show();
            return;
        }
        statusView.setText("推送行位表到電腦中...");
        new Thread(() -> {
            PushResult result;
            try {
                result = postCurrentScheduleGrid(server.trim());
            } catch (Exception e) {
                result = new PushResult(false, 0, 0, e.getMessage());
            }
            PushResult finalResult = result;
            runOnUiThread(() -> {
                if (finalResult.ok) {
                    String message = "已推送行位表到電腦：" + finalResult.importedRows + " 行";
                    if (finalResult.replacedRows >= 0) {
                        message += "，取代 " + finalResult.replacedRows + " 行";
                    }
                    statusView.setText(statusText());
                    Toast.makeText(this, message, Toast.LENGTH_LONG).show();
                } else {
                    String message = finalResult.message == null || finalResult.message.isEmpty()
                            ? "推送失敗"
                            : finalResult.message;
                    statusView.setText("推送失敗：" + message);
                    Toast.makeText(this, "推送失敗：" + message, Toast.LENGTH_LONG).show();
                }
            });
        }).start();
    }

    private PushResult postCurrentScheduleGrid(String rawServer) throws Exception {
        String server = rawServer;
        if (server.endsWith("/")) {
            server = server.substring(0, server.length() - 1);
        }
        if (!server.startsWith("http://") && !server.startsWith("https://")) {
            throw new IOException("電腦 server URL 無效");
        }
        byte[] body = buildScheduleGridXml().getBytes("UTF-8");
        HttpURLConnection conn = null;
        try {
            URL url = new URL(server + "/api/maint/sheets/schedule_grid/import-phone-push");
            conn = (HttpURLConnection) url.openConnection();
            conn.setRequestMethod("POST");
            conn.setConnectTimeout(HTTP_CONNECT_TIMEOUT_MS);
            conn.setReadTimeout(HTTP_READ_TIMEOUT_MS);
            conn.setDoOutput(true);
            conn.setRequestProperty("Content-Type", "application/xml; charset=utf-8");
            conn.setRequestProperty("Content-Length", String.valueOf(body.length));
            try (DataOutputStream out = new DataOutputStream(conn.getOutputStream())) {
                out.write(body);
                out.flush();
            }
            int code = conn.getResponseCode();
            InputStream stream = code >= 200 && code < 300 ? conn.getInputStream() : conn.getErrorStream();
            String response = stream == null ? "" : readInputStreamText(stream);
            if (code < 200 || code >= 300) {
                throw new IOException("HTTP " + code + " " + response);
            }
            JSONObject json = new JSONObject(response);
            return new PushResult(
                    json.optBoolean("ok", false),
                    json.optInt("imported_row_count", 0),
                    json.optInt("replaced_row_count", -1),
                    json.optString("detail", json.optString("message", ""))
            );
        } finally {
            if (conn != null) {
                conn.disconnect();
            }
        }
    }

    private String[] getAutoServerCandidates(String preferredServer) {
        String preferred = preferredServer == null ? "" : preferredServer.trim();
        if (preferred.endsWith("/")) {
            preferred = preferred.substring(0, preferred.length() - 1);
        }
        if (!preferred.isEmpty()
                && (preferred.startsWith("http://") || preferred.startsWith("https://"))) {
            return new String[]{preferred};
        }

        String[] candidates = AlarmStore.getAutoSyncServerCandidates(this);
        if (candidates != null && candidates.length > 0) {
            return candidates;
        }

        return new String[]{AlarmStore.DEFAULT_AUTO_SYNC_SERVER};
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

    private String todayIso() {
        return new SimpleDateFormat("yyyy-MM-dd", Locale.getDefault()).format(System.currentTimeMillis());
    }

    private String readInputStreamText(InputStream inputStream) throws IOException {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        byte[] buffer = new byte[2048];
        int read;
        while (true) {
            read = inputStream.read(buffer);
            if (read < 0) {
                break;
            }
            out.write(buffer, 0, read);
        }
        return out.toString("UTF-8");
    }

    private String buildScheduleGridXml() {
        String exportDate = parseDateTextToIso(draftDate == null ? "" : draftDate);
        if (exportDate.isEmpty()) {
            exportDate = todayIso();
        }
        StringBuilder builder = new StringBuilder();
        builder.append("<?xml version='1.0' encoding='UTF-8' standalone='yes'?>").append('\n');
        String code = draftRosterCode == null ? "" : draftRosterCode.trim();
        builder.append("<schedule_grid effective_date=\"").append(escapeXml(exportDate))
                .append("\" roster_code=\"").append(escapeXml(code)).append("\">").append('\n');
        String header = exportDate.trim();
        if (!header.isEmpty()) {
            String headerLine = header + (code.isEmpty() ? "" : " " + code);
            builder.append("  <section>").append(escapeXml(headerLine)).append("</section>").append('\n');
        }
        for (int i = 0; i < draftAlarms.length(); i++) {
            JSONObject alarm = draftAlarms.optJSONObject(i);
            if (alarm == null) {
                continue;
            }
            String trigger = clockOnly(alarm.optLong("trigger_at_epoch_ms"));
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

    private String escapeXml(String value) {
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

    private ParsedScheduleGridImport parseScheduleGridXml(String xml) throws Exception {
        String rootEffectiveDate = parseScheduleGridRootEffectiveDate(xml);
        ArrayList<String> tokens = extractXmlTexts(xml);
        ArrayList<String> cleaned = new ArrayList<>();
        for (String token : tokens) {
            String v = token == null ? "" : token.trim();
            if (!v.isEmpty()) {
                cleaned.add(v);
            }
        }
        JSONArray alarms = new JSONArray();
        String planDate = "";
        String rosterCode = "";
        String currentDate = "";
        String currentCode = rosterCode;
        int i = 0;
        while (i < cleaned.size()) {
            String token = cleaned.get(i).trim();
            if (token.isEmpty()) {
                i += 1;
                continue;
            }
            String lowered = token.toLowerCase(Locale.getDefault());
            if (XML_NOISE_TEXTS.contains(lowered)) {
                i += 1;
                continue;
            }
            Matcher headerMatch = SCHEDULE_GRID_HEADER_RE.matcher(token);
            if (headerMatch.matches()) {
                currentDate = parseHeaderDateIso(
                        headerMatch.group(1),
                        headerMatch.group(2),
                        headerMatch.group(3),
                        headerMatch.group(4)
                );
                currentCode = headerMatch.group(5) == null ? currentCode : headerMatch.group(5).trim();
                if (!currentDate.isEmpty() && planDate.isEmpty()) {
                    planDate = currentDate;
                }
                if (!currentCode.isEmpty()) {
                    rosterCode = currentCode;
                }
                i++;
                continue;
            }

            if (TIME_RE.matcher(token).matches()) {
                String content = null;
                int j = i + 1;
                while (j < cleaned.size()) {
                    String next = cleaned.get(j).trim();
                    if (next.isEmpty()) {
                        j++;
                        continue;
                    }
                    if (XML_NOISE_TEXTS.contains(next.toLowerCase(Locale.getDefault()))) {
                        j++;
                        continue;
                    }
                    if (TIME_RE.matcher(next).matches()
                            || SCHEDULE_GRID_DATE_RE.matcher(next).matches()
                            || SCHEDULE_GRID_HEADER_RE.matcher(next).matches()) {
                        break;
                    }
                    content = next;
                    j++;
                    break;
                }
                if (content == null) {
                    i++;
                    continue;
                }
                if ((currentDate == null || currentDate.isEmpty()) && !planDate.isEmpty()) {
                    currentDate = planDate;
                }
                if ((currentDate == null || currentDate.isEmpty()) && !draftDate.isEmpty()) {
                    currentDate = draftDate;
                }
                if (currentDate == null || currentDate.isEmpty()) {
                    currentDate = todayIso();
                }
                long triggerAt = parseAlarmTimeOnDate(currentDate, token);
                JSONObject alarm = new JSONObject();
                alarm.put("id", "xml-" + System.currentTimeMillis() + "-" + i);
                alarm.put("label", content);
                alarm.put("trigger_at_epoch_ms", triggerAt);
                alarm.put("trigger_at", formatIso(triggerAt));
                alarms.put(alarm);
                i = j;
                continue;
            }
            i++;
        }
        if (planDate.isEmpty() && !rootEffectiveDate.isEmpty()) {
            planDate = rootEffectiveDate;
        }
        if (planDate.isEmpty() && !draftDate.isEmpty()) {
            planDate = draftDate;
        }
        if (rosterCode.isEmpty()) {
            rosterCode = draftRosterCode == null ? "" : draftRosterCode;
        }
        return new ParsedScheduleGridImport(alarms, planDate, rosterCode);
    }

    private String parseHeaderDateIso(String rawDate, String dayPart, String monthPart, String yearPart) {
        String normalized = parseDateTextToIso(rawDate);
        if (!normalized.isEmpty()) {
            return normalized;
        }
        if (dayPart == null || monthPart == null || yearPart == null) {
            return "";
        }
        try {
            int day = Integer.parseInt(dayPart);
            int month = Integer.parseInt(monthPart);
            int year = Integer.parseInt(yearPart);
            return String.format(Locale.getDefault(), "%04d-%02d-%02d", year, month, day);
        } catch (NumberFormatException e) {
            return "";
        }
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

    private String parseScheduleGridRootEffectiveDate(String xml) {
        if (xml == null || xml.trim().isEmpty()) {
            return "";
        }
        try {
            Document document = parseXmlDocument(xml);
            Node rootNode = document == null ? null : document.getDocumentElement();
            if (!(rootNode instanceof Element)) {
                return "";
            }
            Element root = (Element) rootNode;
            String value = root.getAttribute("effective_date");
            if (value == null || value.trim().isEmpty()) {
                value = root.getAttribute("version");
            }
            return parseDateTextToIso(value == null ? "" : value);
        } catch (Exception e) {
            return "";
        }
    }

    private long parseAlarmTimeOnDate(String dateIso, String timeText) {
        try {
            String[] dateParts = dateIso.split("-");
            String[] timeParts = timeText.split(":");
            if (dateParts.length != 3 || timeParts.length != 2) {
                return 0L;
            }
            int year = Integer.parseInt(dateParts[0]);
            int month = Integer.parseInt(dateParts[1]);
            int day = Integer.parseInt(dateParts[2]);
            int hour = Integer.parseInt(timeParts[0]);
            int minute = Integer.parseInt(timeParts[1]);
            Calendar cal = Calendar.getInstance();
            cal.set(Calendar.YEAR, year);
            cal.set(Calendar.MONTH, month - 1);
            cal.set(Calendar.DAY_OF_MONTH, day);
            cal.set(Calendar.HOUR_OF_DAY, hour);
            cal.set(Calendar.MINUTE, minute);
            cal.set(Calendar.SECOND, 0);
            cal.set(Calendar.MILLISECOND, 0);
            return cal.getTimeInMillis();
        } catch (Exception e) {
            return 0L;
        }
    }

    private ArrayList<String> extractXmlTexts(String xml) throws Exception {
        ArrayList<String> texts = new ArrayList<>();
        Document document = parseXmlDocument(xml);
        collectXmlTextNodes(document, texts);
        return texts;
    }

    private Document parseXmlDocument(String xml) throws Exception {
        DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
        return factory.newDocumentBuilder().parse(new ByteArrayInputStream(xml.getBytes("UTF-8")));
    }

    private void collectXmlTextNodes(Node node, ArrayList<String> texts) {
        if (node == null) {
            return;
        }
        if (node.getNodeType() == Node.TEXT_NODE) {
            String value = node.getNodeValue();
            if (value != null) {
                String trimmed = value.trim();
                if (!trimmed.isEmpty()) {
                    texts.add(trimmed);
                }
            }
        }
        NodeList children = node.getChildNodes();
        for (int i = 0; i < children.getLength(); i++) {
            collectXmlTextNodes(children.item(i), texts);
        }
    }

    private static final class ParsedScheduleGridImport {
        final JSONArray alarms;
        final String planDate;
        final String rosterCode;

        ParsedScheduleGridImport(JSONArray alarms, String planDate, String rosterCode) {
            this.alarms = alarms == null ? new JSONArray() : alarms;
            this.planDate = planDate == null ? "" : planDate;
            this.rosterCode = rosterCode == null ? "" : rosterCode;
        }
    }

    private void configureSystemBars() {
        Window window = getWindow();
        window.setStatusBarColor(0xFFFFFFFF);
        window.setNavigationBarColor(0xFFFFFFFF);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            int flags = View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR;
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                flags |= View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR;
            }
            window.getDecorView().setSystemUiVisibility(flags);
        }
    }

    private void applySafeAreaPadding(ScrollView scrollView) {
        scrollView.setOnApplyWindowInsetsListener((view, insets) -> {
            int top = Math.max(insets.getSystemWindowInsetTop(), systemBarHeight("status_bar_height"));
            int bottom = Math.max(insets.getSystemWindowInsetBottom(), systemBarHeight("navigation_bar_height"));
            view.setPadding(0, top + dp(6), 0, bottom + dp(8));
            return insets;
        });
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.KITKAT_WATCH) {
            scrollView.requestApplyInsets();
        }
    }

    private Button bottomButton(String text) {
        Button button = new Button(this);
        button.setText(text);
        button.setTextSize(10);
        button.setTypeface(mealBoldTypeface());
        button.setGravity(Gravity.CENTER);
        button.setAllCaps(false);
        button.setMinHeight(dp(28));
        button.setMinimumHeight(dp(28));
        return button;
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    private android.graphics.drawable.GradientDrawable roundedBg(
            int fillColor,
            int radiusDp,
            int strokeColor,
            int strokeDp
    ) {
        android.graphics.drawable.GradientDrawable drawable = new android.graphics.drawable.GradientDrawable();
        drawable.setColor(fillColor);
        drawable.setCornerRadius(dp(radiusDp));
        if (strokeDp > 0) {
            drawable.setStroke(dp(strokeDp), strokeColor);
        }
        return drawable;
    }

    private android.graphics.Typeface mealTypeface() {
        if (mealRegularTypeface == null) {
            try {
                mealRegularTypeface = android.graphics.Typeface.createFromAsset(getAssets(), "fonts/msjh.ttc");
            } catch (RuntimeException e) {
                mealRegularTypeface = android.graphics.Typeface.create("sans-serif", android.graphics.Typeface.NORMAL);
            }
        }
        return mealRegularTypeface;
    }

    private android.graphics.Typeface mealBoldTypeface() {
        if (mealMediumTypeface == null) {
            try {
                mealMediumTypeface = android.graphics.Typeface.createFromAsset(getAssets(), "fonts/msjhbd.ttc");
            } catch (RuntimeException e) {
                mealMediumTypeface = android.graphics.Typeface.create("sans-serif-medium", android.graphics.Typeface.NORMAL);
            }
        }
        return mealMediumTypeface;
    }

    private String mealIcon(String meal) {
        if ("早餐".equals(meal)) {
            return "☀";
        }
        if ("午餐".equals(meal)) {
            return "🍱";
        }
        if ("小食".equals(meal) || "加餐".equals(meal)) {
            return "⏱";
        }
        if ("晚餐".equals(meal)) {
            return "☾";
        }
        return "🍽";
    }

    private int iconColorForMeal(String meal) {
        if ("早餐".equals(meal)) {
            return 0xFFF59E0B;
        }
        if ("午餐".equals(meal)) {
            return 0xFF15803D;
        }
        if ("小食".equals(meal) || "加餐".equals(meal)) {
            return 0xFFD97706;
        }
        if ("晚餐".equals(meal)) {
            return 0xFF0369A1;
        }
        return 0xFF064E2D;
    }

    private String foodIcon(String name) {
        String text = name == null ? "" : name;
        if (text.contains("飯") || text.contains("米") || text.contains("燕麥")) {
            return "🍚";
        }
        if (text.contains("奶") || text.contains("豆奶") || text.contains("乳酪") || text.contains("乳")) {
            return "🥛";
        }
        if (text.contains("蛋")) {
            return "🥚";
        }
        if (text.contains("籽") || text.contains("亞麻") || text.contains("奇亞")) {
            return "🌱";
        }
        if (text.contains("粉") || text.contains("膠原")) {
            return "🥄";
        }
        if (text.contains("香蕉")) {
            return "🍌";
        }
        if (text.contains("雞胸") || text.contains("雞")) {
            return "🍗";
        }
        if (text.contains("西蘭花") || text.contains("菜") || text.contains("心")) {
            return "🥦";
        }
        if (text.contains("油")) {
            return "🫒";
        }
        if (text.contains("魚")) {
            return "🐟";
        }
        if (text.contains("薯")) {
            return "🍠";
        }
        if (text.contains("藍莓")) {
            return "🫐";
        }
        return "🍽";
    }

    private int systemBarHeight(String key) {
        int id = getResources().getIdentifier(key, "dimen", "android");
        return id > 0 ? getResources().getDimensionPixelSize(id) : 0;
    }

    private LinearLayout.LayoutParams fullWidthWrapHeight() {
        return new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
        );
    }

    private LinearLayout.LayoutParams weightedParams(float weight) {
        return new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, weight);
    }

    private void loadDraftFromStore() {
        draftAlarms = copyJsonArray(AlarmStore.getAlarms(this));
        draftDate = AlarmStore.getPlanDate(this);
        draftRosterCode = AlarmStore.getRosterCode(this);
        if (draftAlarms.length() > 0) {
            shiftEmptyMessage = "";
        }
        mealPlanText = AlarmStore.getMealPlanText(this);
        mealPlanJsonDate = AlarmStore.getMealPlanJsonDate(this);
        mealPlanJsonVersion = AlarmStore.getMealPlanJsonVersion(this);
        if (mealSelectedDate == null || mealSelectedDate.trim().isEmpty()) {
            mealSelectedDate = todayIso();
        }
        loadMealPlanJsonForSelectedDateFromStore();
    }

    private void loadMealPlanJsonForSelectedDateFromStore() {
        String selectedDate = mealSelectedDate == null ? "" : mealSelectedDate.trim();
        String raw = AlarmStore.getMealPlanJsonForDate(this, selectedDate);
        String version = AlarmStore.getMealPlanJsonVersionForDate(this, selectedDate);
        if ((raw == null || raw.trim().isEmpty()) && selectedDate.equals(AlarmStore.getMealPlanJsonDate(this))) {
            raw = AlarmStore.getMealPlanJson(this);
            version = AlarmStore.getMealPlanJsonVersion(this);
        }
        mealPlanJson = null;
        mealPlanJsonDate = "";
        mealPlanJsonVersion = "";
        if (raw != null && !raw.trim().isEmpty()) {
            try {
                mealPlanJson = new JSONObject(raw);
                mealPlanJsonDate = selectedDate;
                mealPlanJsonVersion = version == null ? "" : version;
            } catch (JSONException ignored) {
                mealPlanJson = null;
            }
        }
    }

    private JSONArray copyJsonArray(JSONArray source) {
        try {
            return new JSONArray(source == null ? "[]" : source.toString());
        } catch (JSONException e) {
            return new JSONArray();
        }
    }

    private void render() {
        updatePageVisibility();
        headerView.setText(formatHeader());
        renderMealPage();
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
        int cachedCount = AlarmStore.getScheduleGridVariants(this).length();
        shiftEmptyMessage = cachedCount > 0
                ? message + "\n可按更碼選擇電話已下載行位表作今日行位"
                : message;
        AlarmScheduler.schedulePlan(this, draftAlarms, 0L, draftDate, draftRosterCode);
        loadDraftFromStore();
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
        TextView view = new TextView(this);
        view.setText(message == null ? "" : message);
        view.setTextSize(16);
        view.setGravity(Gravity.CENTER);
        view.setTextColor(0xFFB91C1C);
        view.setBackgroundColor(0xFFFFFFFF);
        view.setPadding(dp(12), dp(18), dp(12), dp(18));
        return view;
    }

    private String shiftVariantButtonText() {
        int count = AlarmStore.getScheduleGridVariants(this).length();
        if (count > 1) {
            return "更碼(" + count + ")";
        }
        return "更碼";
    }

    private boolean shouldApplyShiftVariantAsToday() {
        return !shiftEmptyMessage.trim().isEmpty()
                || draftAlarms.length() == 0
                || !todayIso().equals(draftDate);
    }

    private void showShiftVariantDialog(boolean applyAsToday) {
        JSONArray variants = AlarmStore.getScheduleGridVariants(this);
        if (variants.length() == 0) {
            Toast.makeText(this, "電話未有已匯入更碼", Toast.LENGTH_LONG).show();
            return;
        }
        String[] labels = new String[variants.length()];
        for (int i = 0; i < variants.length(); i++) {
            JSONObject variant = variants.optJSONObject(i);
            String date = variant == null ? "" : formatPlanDate(variant.optString("plan_date", ""));
            String code = variant == null ? "" : variant.optString("roster_code", "");
            int count = variant == null ? 0 : variant.optInt("alarm_count", 0);
            String marker = code.equals(draftRosterCode) ? "✓ " : "";
            labels[i] = marker + code + "｜" + date + "｜" + count + " 個鬧鐘";
        }
        new AlertDialog.Builder(this)
                .setTitle(applyAsToday ? "匯入失敗：選擇今日更碼" : "選擇更碼")
                .setItems(labels, (dialog, which) -> applyShiftVariant(variants.optJSONObject(which), applyAsToday))
                .show();
    }

    private void applyShiftVariant(JSONObject variant, boolean applyAsToday) {
        if (variant == null) {
            return;
        }
        JSONArray alarms = variant.optJSONArray("alarms");
        if (alarms == null || alarms.length() == 0) {
            Toast.makeText(this, "呢個更碼冇鬧鐘", Toast.LENGTH_LONG).show();
            return;
        }
        shiftEmptyMessage = "";
        String planDate = applyAsToday ? todayIso() : variant.optString("plan_date", draftDate);
        draftAlarms = applyAsToday ? copyAlarmsForDate(alarms, planDate) : copyJsonArray(alarms);
        draftDate = planDate;
        draftRosterCode = variant.optString("roster_code", draftRosterCode);
        saveDraftAlarms();
        Toast.makeText(
                this,
                applyAsToday
                        ? "已用快取更碼 " + draftRosterCode + " 作今日行位"
                        : "已套用更碼 " + draftRosterCode,
                Toast.LENGTH_LONG
        ).show();
    }

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

            JSONObject target = new JSONObject();
            try {
                target.put("id", "cached-" + dateIso + "-" + i + "-" + targetCal.getTimeInMillis());
                target.put("label", source.optString("label", "鬧鐘"));
                target.put("trigger_at_epoch_ms", targetCal.getTimeInMillis());
                target.put("trigger_at", formatIso(targetCal.getTimeInMillis()));
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
        String datePart = formatPlanDate(draftDate);
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

    private String formatPlanDate(String iso) {
        if (iso == null || iso.trim().isEmpty()) {
            return "";
        }
        String[] parts = iso.split("-");
        if (parts.length != 3) {
            return iso;
        }
        try {
            int year = Integer.parseInt(parts[0]);
            int month = Integer.parseInt(parts[1]);
            int day = Integer.parseInt(parts[2]);
            Calendar calendar = Calendar.getInstance();
            calendar.set(year, month - 1, day, 0, 0, 0);
            calendar.set(Calendar.MILLISECOND, 0);
            String weekday = new SimpleDateFormat("EEE", Locale.getDefault()).format(calendar.getTime());
            return parts[2] + "/" + parts[1] + "/" + parts[0] + " " + weekday;
        } catch (RuntimeException ex) {
            return parts[2] + "/" + parts[1] + "/" + parts[0];
        }
    }

    private String formatPlanDateWithRoster(String iso, JSONObject day) {
        String text = formatPlanDate(iso);
        String roster = day == null ? "" : day.optString("roster_code", "").trim();
        if (!roster.isEmpty()) {
            text = (text + " " + roster).trim();
        }
        return text;
    }

    private String statusText() {
        StringBuilder text = new StringBuilder();
        text.append("已自動更新：");
        text.append(draftAlarms.length()).append(" 個鬧鐘");
        text.append("｜餐單：").append(mealPlanJson == null ? "未連線" : "已連線");
        text.append("\nLast import: ").append(formatLastImportAt());
        return text.toString();
    }

    private String formatLastImportAt() {
        long lastImportAt = AlarmStore.getLastImportAt(this);
        if (lastImportAt <= 0L) {
            return "--";
        }
        return new SimpleDateFormat("yyyy-MM-dd HH:mm", Locale.getDefault()).format(lastImportAt);
    }

    private String mealPlanTextDisplay() {
        String plan = mealPlanText == null ? "" : mealPlanText.trim();
        if (plan.isEmpty()) {
            return "未有餐單資料（等你電腦同步後會顯示）";
        }
        return plan;
    }

    private void renderMealPage() {
        if (mealDateView == null || mealSummaryView == null || mealCardsView == null) {
            return;
        }
        if (mealSelectedDate == null || mealSelectedDate.trim().isEmpty()) {
            mealSelectedDate = todayIso();
        }
        mealDateView.setText(formatPlanDate(mealSelectedDate));
        mealSummaryView.removeAllViews();
        mealCardsView.removeAllViews();

        JSONObject day = mealPlanJson == null ? null : mealPlanJson.optJSONObject("day");
        if (day == null) {
            setMealPlanStatusText(mealFetchInFlight ? "連線電腦餐單中..." : mealPlanTextDisplay(), true);
            updateMealLastUpdateStatus();
            return;
        }
        mealDateView.setText(formatPlanDateWithRoster(mealSelectedDate, day));

        if (mealFetchInFlight) {
            setMealPlanStatusText("更新中...", true);
        } else if (mealFetchErrorText != null && !mealFetchErrorText.trim().isEmpty()) {
            setMealPlanStatusText(mealFetchErrorText.trim(), true);
        } else {
            setMealPlanStatusText("", false);
        }
        updateMealLastUpdateStatus();
        renderMealSummary(day);
        renderMealCards(day);
    }

    private void setMealPlanStatusText(String text, boolean visible) {
        if (mealPlanView == null) {
            return;
        }
        String value = text == null ? "" : text.trim();
        mealPlanView.setText(value);
        mealPlanView.setVisibility(visible && !value.isEmpty() ? View.VISIBLE : View.GONE);
    }

    private void renderMealSummary(JSONObject day) {
        JSONObject mealPlan = day.optJSONObject("meal_plan");
        JSONObject summary = mealPlan == null ? null : mealPlan.optJSONObject("summary");
        JSONObject indicators = day.optJSONObject("nutrient_indicators");
        JSONArray totals = summary == null ? null : summary.optJSONArray("totals");
        JSONArray errors = summary == null ? null : summary.optJSONArray("errors");
        JSONArray totalRedFlags = summary == null ? null : summary.optJSONArray("total_red_flags");
        JSONArray errorRedFlags = summary == null ? null : summary.optJSONArray("error_red_flags");
        LinearLayout wrap = new LinearLayout(this);
        wrap.setOrientation(LinearLayout.HORIZONTAL);
        wrap.setPadding(dp(3), dp(2), dp(3), dp(2));
        wrap.setBackground(roundedBg(0xFFFFFEFA, 14, 0xFFE5DCCB, 1));
        LinearLayout.LayoutParams wrapParams = fullWidthWrapHeight();
        wrapParams.setMargins(0, 0, 0, dp(8));
        mealSummaryView.addView(wrap, wrapParams);

        String[] keys = new String[]{"kcal", "protein_g", "carb_g", "fat_total_g"};
        String[] labels = new String[]{"🔥 熱量", "💪 蛋白質", "🍚 碳水", "💧 脂肪"};
        for (int i = 0; i < keys.length; i++) {
            String key = keys[i];
            int keyIdx = keyIndex(key);
            double value = arrayDoubleAt(totals, keyIndex(key));
            double delta = arrayDoubleAt(errors, keyIndex(key));
            JSONObject indicator = indicators == null ? null : indicators.optJSONObject(key);
            LinearLayout card = summaryCard(
                    labels[i],
                    formatMetricValue(key, value),
                    formatTargetRule(key, indicator, arrayDoubleAt(totals, keyIndex("kcal"))),
                    formatDelta(key, delta),
                    boolArrayAt(totalRedFlags, keyIdx),
                    boolArrayAt(errorRedFlags, keyIdx)
            );
            wrap.addView(card, weightedParams(1f));
        }

        LinearLayout side = new LinearLayout(this);
        side.setOrientation(LinearLayout.VERTICAL);
        side.setPadding(dp(3), 0, 0, 0);
        wrap.addView(side, weightedParams(0.92f));
        addSummarySmallCell(side, "鈉", "sodium_mg", totals, errors, indicators, totalRedFlags, errorRedFlags);
        addSummarySmallCell(side, "鈣質", "calcium_mg", totals, errors, indicators, totalRedFlags, errorRedFlags);
    }

    private void renderMealCards(JSONObject day) {
        JSONObject mealPlan = day.optJSONObject("meal_plan");
        if (mealPlan == null) {
            return;
        }
        JSONObject resolved = mealPlan.optJSONObject("meal_times_resolved");
        if (resolved == null) {
            resolved = new JSONObject();
        }
        String[] meals = new String[]{"早餐", "午餐", "小食", "晚餐"};
        String defaultExpanded = defaultExpandedMeal(mealPlan, resolved);
        if (mealExpandedKey == null || mealExpandedKey.trim().isEmpty() || resolved.optString(mealExpandedKey, "").trim().isEmpty()) {
            mealExpandedKey = defaultExpanded;
        }
        boolean hasVisibleMeal = false;
        for (String meal : meals) {
            String timeText = cleanMealText(resolved.optString(meal, ""));
            if (timeText.isEmpty()) {
                continue;
            }
            if (!mealHasContent(mealPlan, meal)) {
                continue;
            }
            hasVisibleMeal = true;
            mealCardsView.addView(mealCard(mealPlan, meal, timeText, meal.equals(mealExpandedKey)), fullWidthWrapHeight());
        }
        if (!hasVisibleMeal) {
            TextView empty = new TextView(this);
            empty.setText("當日未有餐單內容");
            empty.setTextSize(12);
            empty.setTextColor(0xFF64748B);
            empty.setPadding(dp(8), dp(12), dp(8), dp(12));
            empty.setBackground(roundedBg(0xFFFFFDF8, 14, 0xFFE7DDCA, 1));
            mealCardsView.addView(empty, fullWidthWrapHeight());
        }
        addRiceNoteCard(mealPlan);
    }

    private LinearLayout summaryCard(String label, String value, String target, String delta, boolean totalRed, boolean errorRed) {
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setPadding(dp(3), dp(3), dp(3), dp(3));
        LinearLayout.LayoutParams params = weightedParams(1f);
        params.setMargins(0, 0, dp(2), 0);
        box.setLayoutParams(params);

        TextView title = new TextView(this);
        title.setText(label);
        title.setTextSize(7);
        title.setTextColor(0xFF0F172A);
        title.setTypeface(mealBoldTypeface());
        title.setSingleLine(true);
        box.addView(title, fullWidthWrapHeight());

        String mainText = value;
        if ((mainText == null || mainText.trim().isEmpty()) && !target.isEmpty()) {
            mainText = target;
        }
        if ((mainText == null || mainText.trim().isEmpty())) {
            mainText = "—";
        }
        String targetText = target == null ? "" : target.trim();
        String deltaText = errorRed ? delta : "OK";

        TextView main = new TextView(this);
        main.setText(mainText);
        main.setTextSize(11);
        main.setTextColor(totalRed ? 0xFFB91C1C : 0xFF064E2D);
        main.setTypeface(mealBoldTypeface());
        main.setSingleLine(true);
        main.setPadding(0, dp(2), 0, dp(1));
        box.addView(main, fullWidthWrapHeight());

        TextView targetView = new TextView(this);
        targetView.setText(targetText.isEmpty() ? " " : "目標 " + targetText);
        targetView.setTextSize(6);
        targetView.setTextColor(0xFF6B7280);
        targetView.setTypeface(mealTypeface());
        targetView.setSingleLine(true);
        box.addView(targetView, fullWidthWrapHeight());

        TextView deltaView = new TextView(this);
        deltaView.setText(deltaText);
        deltaView.setTextSize(7);
        deltaView.setTextColor(errorRed ? 0xFFEA580C : 0xFF064E2D);
        deltaView.setTypeface(mealBoldTypeface());
        deltaView.setSingleLine(true);
        deltaView.setPadding(0, dp(1), 0, 0);
        box.addView(deltaView, fullWidthWrapHeight());

        LinearLayout bar = progressBar(progressRatioForTarget(target, parseLeadingNumber(value)));
        LinearLayout.LayoutParams barParams = fullWidthWrapHeight();
        barParams.setMargins(0, dp(4), 0, 0);
        box.addView(bar, barParams);
        return box;
    }

    private void addSummarySmallCell(
            LinearLayout side,
            String label,
            String key,
            JSONArray totals,
            JSONArray errors,
            JSONObject indicators,
            JSONArray totalRedFlags,
            JSONArray errorRedFlags
    ) {
        int keyIdx = keyIndex(key);
        double value = arrayDoubleAt(totals, keyIdx);
        double delta = arrayDoubleAt(errors, keyIdx);
        JSONObject indicator = indicators == null ? null : indicators.optJSONObject(key);
        String target = formatTargetRule(key, indicator, arrayDoubleAt(totals, keyIndex("kcal")));
        boolean totalRed = boolArrayAt(totalRedFlags, keyIdx);
        boolean errorRed = boolArrayAt(errorRedFlags, keyIdx);

        TextView cell = new TextView(this);
        cell.setText(label + "\n" + formatMetricValue(key, value) + "\n/ " + target + "\n" + (errorRed ? formatDelta(key, delta) : "OK"));
        cell.setTextSize(6);
        cell.setTextColor(totalRed || errorRed ? 0xFFB91C1C : 0xFF0F172A);
        cell.setTypeface(mealBoldTypeface());
        cell.setPadding(dp(4), dp(2), dp(4), dp(2));
        cell.setBackground(roundedBg(0xFFFFFEFA, 10, 0xFFE5DCCB, 1));
        LinearLayout.LayoutParams params = fullWidthWrapHeight();
        params.setMargins(0, 0, 0, dp(4));
        side.addView(cell, params);
    }

    private LinearLayout progressBar(double ratio) {
        LinearLayout outer = new LinearLayout(this);
        outer.setOrientation(LinearLayout.HORIZONTAL);
        outer.setBackground(roundedBg(0xFFD7DDC9, 4, 0xFFD7DDC9, 0));
        outer.setMinimumHeight(dp(5));
        int filled = Math.max(1, Math.min(100, (int) Math.round(ratio * 100.0d)));
        View green = new View(this);
        green.setBackground(roundedBg(0xFF065F46, 4, 0xFF065F46, 0));
        outer.addView(green, new LinearLayout.LayoutParams(0, dp(5), filled));
        View rest = new View(this);
        outer.addView(rest, new LinearLayout.LayoutParams(0, dp(5), 100 - filled));
        return outer;
    }

    private double progressRatioForTarget(String target, double value) {
        String text = target == null ? "" : target;
        Matcher matcher = Pattern.compile("(\\d+(?:\\.\\d+)?)").matcher(text);
        double last = 0.0d;
        while (matcher.find()) {
            try {
                last = Double.parseDouble(matcher.group(1));
            } catch (NumberFormatException ignored) {
            }
        }
        if (last <= 0.0d) {
            return 0.85d;
        }
        return Math.max(0.0d, Math.min(1.0d, value / last));
    }

    private double parseLeadingNumber(String value) {
        Matcher matcher = Pattern.compile("(\\d+(?:\\.\\d+)?)").matcher(value == null ? "" : value);
        if (!matcher.find()) {
            return 0.0d;
        }
        try {
            return Double.parseDouble(matcher.group(1));
        } catch (NumberFormatException e) {
            return 0.0d;
        }
    }

    private LinearLayout mealCard(JSONObject mealPlan, String meal, String timeText, boolean expanded) {
        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setBackground(roundedBg(0xFFFFFEFA, 14, expanded ? 0xFF065F46 : 0xFFE5DCCB, expanded ? 2 : 1));
        LinearLayout.LayoutParams params = fullWidthWrapHeight();
        params.setMargins(0, 0, 0, dp(2));
        card.setLayoutParams(params);
        card.setPadding(0, 0, 0, 0);
        card.setOnClickListener(v -> {
            mealExpandedKey = meal.equals(mealExpandedKey) ? "" : meal;
            renderMealPage();
        });

        if (!expanded) {
            card.setOrientation(LinearLayout.HORIZONTAL);
            card.setGravity(Gravity.CENTER_VERTICAL);
            card.setPadding(dp(8), dp(4), dp(8), dp(4));

            TextView compactIcon = new TextView(this);
            compactIcon.setText(mealIcon(meal));
            compactIcon.setTextSize(13);
            compactIcon.setTextColor(iconColorForMeal(meal));
            compactIcon.setGravity(Gravity.CENTER);
            compactIcon.setTypeface(mealBoldTypeface());
            card.addView(compactIcon, new LinearLayout.LayoutParams(dp(34), LinearLayout.LayoutParams.WRAP_CONTENT));

            TextView compactText = new TextView(this);
            compactText.setText(timeText + "  " + meal);
            compactText.setTextSize(13);
            compactText.setTextColor(0xFF0F172A);
            compactText.setTypeface(mealBoldTypeface());
            compactText.setSingleLine(true);
            card.addView(compactText, weightedParams(1f));

            TextView compactChevron = new TextView(this);
            compactChevron.setText("﹀");
            compactChevron.setTextSize(16);
            compactChevron.setTextColor(0xFF0F172A);
            compactChevron.setGravity(Gravity.CENTER);
            card.addView(compactChevron, new LinearLayout.LayoutParams(dp(34), LinearLayout.LayoutParams.WRAP_CONTENT));
            return card;
        }

        LinearLayout body = new LinearLayout(this);
        body.setOrientation(LinearLayout.HORIZONTAL);
        body.setBaselineAligned(false);
        body.setPadding(0, 0, 0, 0);
        body.setMinimumHeight(dp(150));
        card.addView(body, fullWidthWrapHeight());

        LinearLayout side = new LinearLayout(this);
        side.setOrientation(LinearLayout.VERTICAL);
        side.setGravity(Gravity.CENTER_HORIZONTAL);
        side.setPadding(dp(5), dp(5), dp(5), dp(4));
        side.setBackground(roundedBg(0xFFF3F8EE, 14, 0x00000000, 0));
        LinearLayout.LayoutParams sideParams = new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.MATCH_PARENT, 0.78f);
        sideParams.setMargins(dp(3), dp(3), dp(3), dp(3));
        body.addView(side, sideParams);

        TextView icon = new TextView(this);
        icon.setText(mealIcon(meal));
        icon.setTextSize(13);
        icon.setGravity(Gravity.CENTER);
        icon.setTextColor(iconColorForMeal(meal));
        icon.setTypeface(mealBoldTypeface());
        side.addView(icon, fullWidthWrapHeight());

        TextView timeTag = new TextView(this);
        timeTag.setText(timeText);
        timeTag.setTextSize(13);
        timeTag.setTextColor(0xFF0F172A);
        timeTag.setTypeface(mealBoldTypeface());
        timeTag.setGravity(Gravity.CENTER);
        timeTag.setPadding(0, dp(2), 0, 0);
        side.addView(timeTag, fullWidthWrapHeight());

        TextView title = new TextView(this);
        title.setText(meal);
        title.setTextSize(15);
        title.setTextColor(0xFF0F172A);
        title.setTypeface(mealBoldTypeface());
        title.setGravity(Gravity.CENTER);
        title.setPadding(0, dp(1), 0, dp(2));
        side.addView(title, fullWidthWrapHeight());

        android.view.View sideSpacer = new android.view.View(this);
        side.addView(sideSpacer, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                0,
                1f
        ));

        String macroText = mealMacroLine(mealPlan, meal);
        TextView macro = new TextView(this);
        macro.setText(formatMealMacroForSide(macroText));
        macro.setTextSize(8);
        macro.setTextColor(0xFF064E2D);
        macro.setTypeface(mealBoldTypeface());
        macro.setGravity(Gravity.CENTER);
        macro.setSingleLine(false);
        macro.setPadding(0, dp(2), 0, 0);
        side.addView(macro, fullWidthWrapHeight());

        LinearLayout content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        content.setPadding(dp(6), dp(3), dp(4), dp(3));
        body.addView(content, weightedParams(2.05f));

        TextView chevron = new TextView(this);
        chevron.setText(expanded ? "︿" : "﹀");
        chevron.setTextSize(15);
        chevron.setTextColor(0xFF0F172A);
        chevron.setTypeface(mealTypeface());
        chevron.setGravity(Gravity.CENTER);
        body.addView(chevron, new LinearLayout.LayoutParams(dp(24), LinearLayout.LayoutParams.MATCH_PARENT));

        addMealRows(content, mealPlan, meal, Integer.MAX_VALUE);
        return card;
    }

    private LinearLayout mealItemRow(JSONObject item) {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setPadding(0, dp(1), 0, dp(1));

        TextView icon = new TextView(this);
        icon.setText(foodIcon(item.optString("name", "")));
        icon.setTextSize(15);
        icon.setGravity(Gravity.CENTER);
        row.addView(icon, new LinearLayout.LayoutParams(dp(24), LinearLayout.LayoutParams.WRAP_CONTENT));

        TextView name = new TextView(this);
        name.setText(cleanMealText(item.optString("name", "")));
        name.setTextSize(13);
        name.setTextColor(0xFF0F172A);
        name.setTypeface(mealBoldTypeface());
        name.setSingleLine(true);
        name.setLayoutParams(weightedParams(1f));
        row.addView(name);

        TextView amount = new TextView(this);
        amount.setText(formatItemAmount(item.opt("grams")));
        amount.setTextSize(13);
        amount.setTextColor(0xFF0F172A);
        amount.setTypeface(mealBoldTypeface());
        amount.setSingleLine(true);
        amount.setGravity(Gravity.END);
        row.addView(amount, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
        ));
        return row;
    }

    private boolean mealHasContent(JSONObject mealPlan, String meal) {
        JSONObject mealItems = mealPlan == null ? null : mealPlan.optJSONObject("meal_items");
        JSONArray items = mealItems == null ? null : mealItems.optJSONArray(meal);
        if (items != null && items.length() > 0) {
            for (int i = 0; i < items.length(); i++) {
                JSONObject item = items.optJSONObject(i);
                if (item != null
                        && !cleanMealText(item.optString("name", "")).isEmpty()
                        && itemHasUsefulAmount(item)) {
                    return true;
                }
            }
        }
        JSONObject mealIngredients = mealPlan == null ? null : mealPlan.optJSONObject("meal_ingredients");
        JSONArray ingredients = mealIngredients == null ? null : mealIngredients.optJSONArray(meal);
        if (ingredients != null && ingredients.length() > 0) {
            for (int i = 0; i < ingredients.length(); i++) {
                if (isMeaningfulMealIngredient(String.valueOf(ingredients.opt(i)))) {
                    return true;
                }
            }
        }
        return false;
    }

    private void addMealRows(LinearLayout target, JSONObject mealPlan, String meal, int maxRows) {
        int added = 0;
        JSONObject mealItems = mealPlan == null ? null : mealPlan.optJSONObject("meal_items");
        JSONArray items = mealItems == null ? null : mealItems.optJSONArray(meal);
        if (items != null && items.length() > 0) {
            for (int i = 0; i < items.length() && added < maxRows; i++) {
                JSONObject item = items.optJSONObject(i);
                if (item == null || cleanMealText(item.optString("name", "")).isEmpty()) {
                    continue;
                }
                target.addView(mealItemRow(item), fullWidthWrapHeight());
                added++;
            }
            return;
        }

        JSONObject mealIngredients = mealPlan == null ? null : mealPlan.optJSONObject("meal_ingredients");
        JSONArray ingredients = mealIngredients == null ? null : mealIngredients.optJSONArray(meal);
        if (ingredients == null) {
            return;
        }
        for (int i = 0; i < ingredients.length() && added < maxRows; i++) {
            String text = String.valueOf(ingredients.opt(i)).trim();
            if (!isMeaningfulMealIngredient(text)) {
                continue;
            }
            TextView line = new TextView(this);
            line.setText(text);
            line.setTextSize(11);
            line.setTextColor(0xFF0F172A);
            line.setTypeface(mealBoldTypeface());
            line.setSingleLine(false);
            line.setMaxLines(2);
            line.setPadding(0, dp(2), 0, dp(2));
            target.addView(line, fullWidthWrapHeight());
            added++;
        }
    }

    private boolean itemHasUsefulAmount(JSONObject item) {
        if (item == null || !item.has("grams")) {
            return true;
        }
        Object raw = item.opt("grams");
        if (raw == null || JSONObject.NULL.equals(raw)) {
            return true;
        }
        if (raw instanceof Number) {
            return ((Number) raw).doubleValue() > 0.0d;
        }
        String text = String.valueOf(raw).trim();
        if (text.isEmpty()) {
            return true;
        }
        try {
            return Double.parseDouble(text) > 0.0d;
        } catch (NumberFormatException ignored) {
            return true;
        }
    }

    private boolean isMeaningfulMealIngredient(String raw) {
        String text = cleanMealText(raw);
        if (text.isEmpty()) {
            return false;
        }
        String compact = text
                .replace("—", "")
                .replace("-", "")
                .replace("－", "")
                .replace("null", "")
                .replace("NULL", "")
                .trim();
        if (compact.isEmpty()) {
            return false;
        }
        String lower = compact.toLowerCase(Locale.US);
        return !("breakfast".equals(lower)
                || "lunch".equals(lower)
                || "dinner".equals(lower)
                || "snack".equals(lower)
                || "早餐".equals(compact)
                || "午餐".equals(compact)
                || "晚餐".equals(compact)
                || "小食".equals(compact));
    }

    private String cleanMealText(String raw) {
        String text = raw == null ? "" : raw.trim();
        if (text.equalsIgnoreCase("null")
                || text.equalsIgnoreCase("none")
                || text.equalsIgnoreCase("nan")
                || text.equals("—")
                || text.equals("-")
                || text.equals("－")) {
            return "";
        }
        return text;
    }

    private void addRiceNoteCard(JSONObject mealPlan) {
        String note = mealPlan == null ? "" : mealPlan.optString("rice_note", "").trim();
        if (note.isEmpty() || note.contains("配餐後填")) {
            return;
        }
        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.HORIZONTAL);
        card.setGravity(Gravity.TOP);
        card.setPadding(dp(10), 0, dp(10), dp(3));
        card.setBackground(roundedBg(0xFFFFFEFA, 14, 0xFFE5DCCB, 1));
        LinearLayout.LayoutParams params = fullWidthWrapHeight();
        params.setMargins(0, 0, 0, dp(8));

        TextView icon = new TextView(this);
        icon.setText("🍚");
        icon.setTextSize(17);
        icon.setGravity(Gravity.CENTER);
        icon.setIncludeFontPadding(false);
        LinearLayout.LayoutParams iconParams = new LinearLayout.LayoutParams(dp(38), LinearLayout.LayoutParams.WRAP_CONTENT);
        iconParams.setMargins(0, dp(1), 0, 0);
        card.addView(icon, iconParams);

        LinearLayout textBox = new LinearLayout(this);
        textBox.setOrientation(LinearLayout.VERTICAL);
        textBox.setGravity(Gravity.TOP);
        textBox.setPadding(dp(8), 0, 0, 0);

        TextView title = riceNoteLine("米類生熟比", 10);
        textBox.addView(title, fullWidthWrapHeight());

        String[] noteLines = riceNoteLines(note);
        for (String line : noteLines) {
            textBox.addView(riceNoteLine(line, 10), fullWidthWrapHeight());
        }

        card.addView(textBox, weightedParams(1f));
        mealCardsView.addView(card, params);
    }

    private TextView riceNoteLine(String text, int sizeSp) {
        TextView view = new TextView(this);
        view.setText(text == null ? "" : text.trim());
        view.setTextSize(sizeSp);
        view.setTextColor(0xFF064E2D);
        view.setTypeface(mealBoldTypeface());
        view.setSingleLine(true);
        view.setIncludeFontPadding(false);
        view.setPadding(0, 0, 0, dp(1));
        return view;
    }

    private String[] riceNoteLines(String note) {
        String text = note == null ? "" : note.trim();
        if (text.isEmpty()) {
            return new String[0];
        }
        String[] raw = text.split("\\r?\\n");
        java.util.ArrayList<String> lines = new java.util.ArrayList<>();
        for (String line : raw) {
            String trimmed = line == null ? "" : line.trim();
            if (!trimmed.isEmpty()) {
                lines.add(trimmed);
            }
        }
        return lines.toArray(new String[0]);
    }

    private void toggleKitchenMode() {
        kitchenModeEnabled = !kitchenModeEnabled;
        applyAodState(true);
    }

    private void applyAodState(boolean showToast) {
        if (kitchenModeEnabled) {
            getWindow().addFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
            if (aodToggleButton != null) {
                aodToggleButton.setText("AOD ON");
                aodToggleButton.setTextColor(0xFFFFFFFF);
                aodToggleButton.setAlpha(1f);
                aodToggleButton.setBackground(roundedBg(0xFF065F46, 10, 0xFF065F46, 1));
            }
            if (showToast) {
                Toast.makeText(this, "AOD ON：螢幕保持開啟", Toast.LENGTH_SHORT).show();
            }
        } else {
            getWindow().clearFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
            if (aodToggleButton != null) {
                aodToggleButton.setText("AOD OFF");
                aodToggleButton.setTextColor(0xFFE5EDF1);
                aodToggleButton.setAlpha(0.68f);
                aodToggleButton.setBackground(roundedBg(0xFF263238, 10, 0xFF263238, 1));
            }
            if (showToast) {
                Toast.makeText(this, "AOD OFF", Toast.LENGTH_SHORT).show();
            }
        }
    }

    private void updateMealLastUpdateStatus() {
        if (mealLastUpdateStatusView == null) {
            return;
        }
        String value;
        int textColor;
        if (mealFetchInFlight) {
            value = "Updating...";
            textColor = 0xFF92400E;
        } else if (mealFetchErrorText != null && !mealFetchErrorText.trim().isEmpty()) {
            value = mealFetchErrorText.trim();
            textColor = 0xFF9F1239;
        } else if (mealLastFetchAtMs > 0L) {
            value = formatHongKongThirtyHourAt(mealLastFetchAtMs);
            textColor = 0xFF166534;
        } else {
            value = "--";
            textColor = 0xFF36505D;
        }
        if (mealLastUpdateTitleView != null) {
            mealLastUpdateTitleView.setTextColor(textColor);
        }
        mealLastUpdateStatusView.setText(value);
        mealLastUpdateStatusView.setTextColor(textColor);
    }

    private String formatHongKongThirtyHourAt(long millis) {
        TimeZone zone = TimeZone.getTimeZone("Asia/Hong_Kong");
        Calendar calendar = Calendar.getInstance(zone, Locale.US);
        calendar.setTimeInMillis(millis);
        int hour = calendar.get(Calendar.HOUR_OF_DAY);
        int displayHour = hour;
        if (hour < 6) {
            calendar.add(Calendar.DAY_OF_MONTH, -1);
            displayHour = hour + 24;
        }
        SimpleDateFormat dateFormat = new SimpleDateFormat("dd/MM/yyyy EEE", Locale.US);
        dateFormat.setTimeZone(zone);
        return String.format(
                Locale.US,
                "%s %02d:%02d:%02d",
                dateFormat.format(calendar.getTime()),
                displayHour,
                calendar.get(Calendar.MINUTE),
                calendar.get(Calendar.SECOND)
        );
    }

    private void showShoppingListDialog() {
        JSONObject day = mealPlanJson == null ? null : mealPlanJson.optJSONObject("day");
        JSONObject mealPlan = day == null ? null : day.optJSONObject("meal_plan");
        JSONObject mealItems = mealPlan == null ? null : mealPlan.optJSONObject("meal_items");
        if (mealItems == null) {
            Toast.makeText(this, "未有買餸清單資料", Toast.LENGTH_SHORT).show();
            return;
        }
        String[] meals = new String[]{"早餐", "午餐", "小食", "晚餐"};
        StringBuilder text = new StringBuilder();
        for (String meal : meals) {
            JSONArray items = mealItems.optJSONArray(meal);
            if (items == null || items.length() == 0) {
                continue;
            }
            if (text.length() > 0) {
                text.append("\n");
            }
            text.append(meal).append("\n");
            for (int i = 0; i < items.length(); i++) {
                JSONObject item = items.optJSONObject(i);
                if (item == null) {
                    continue;
                }
                String name = item.optString("name", "").trim();
                if (name.isEmpty()) {
                    continue;
                }
                text.append("  ").append(name);
                String amount = formatItemAmount(item.opt("grams"));
                if (!amount.trim().isEmpty()) {
                    text.append("  ").append(amount);
                }
                text.append("\n");
            }
        }
        String body = text.length() == 0 ? "未有買餸清單資料" : text.toString().trim();
        new AlertDialog.Builder(this)
                .setTitle("買餸清單")
                .setMessage(body)
                .setPositiveButton("OK", null)
                .show();
    }

    private void ensureMealPlanLoaded(boolean force) {
        if (currentPage != PAGE_MEAL || mealFetchInFlight) {
            return;
        }
        if (mealSelectedDate == null || mealSelectedDate.trim().isEmpty()) {
            mealSelectedDate = todayIso();
        }
        fetchMealPlanForDate(mealSelectedDate);
    }

    private void fetchMealPlanForSelectedDate() {
        ensureMealPlanLoaded(true);
    }

    private void fetchMealPlanMetaForDate(String dateIso) {
        String autoServer = AlarmStore.getAutoSyncServerUrl(this);
        if (autoServer == null || autoServer.trim().isEmpty() || mealFetchInFlight) {
            return;
        }
        mealFetchInFlight = true;
        updateMealLastUpdateStatus();
        new Thread(() -> {
            Exception lastError = null;
            for (String baseServer : getAutoServerCandidates(autoServer)) {
                String server = baseServer == null ? "" : baseServer.trim();
                if (server.isEmpty()) {
                    continue;
                }
                if (server.endsWith("/")) {
                    server = server.substring(0, server.length() - 1);
                }
                HttpURLConnection conn = null;
                try {
                    URL url = new URL(server + "/api/mobile-meal-plan?date_iso=" + Uri.encode(dateIso) + "&meta_only=true");
                    conn = (HttpURLConnection) url.openConnection();
                    conn.setRequestMethod("GET");
                    conn.setConnectTimeout(HTTP_CONNECT_TIMEOUT_MS);
                    conn.setReadTimeout(HTTP_READ_TIMEOUT_MS);
                    conn.connect();
                    int code = conn.getResponseCode();
                    if (code != HttpURLConnection.HTTP_OK) {
                        lastError = new IOException("HTTP " + code);
                        continue;
                    }
                    String body = readInputStreamText(conn.getInputStream());
                    JSONObject json = new JSONObject(body);
                    String serverVersion = json.optString("content_version", "").trim();
                    mealFetchInFlight = false;
                    mealLastFetchAtMs = System.currentTimeMillis();
                    String cachedVersion = AlarmStore.getMealPlanJsonVersionForDate(this, dateIso);
                    if (cachedVersion.isEmpty() && dateIso.equals(AlarmStore.getMealPlanJsonDate(this))) {
                        cachedVersion = AlarmStore.getMealPlanJsonVersion(this);
                    }
                    if (!serverVersion.isEmpty() && serverVersion.equals(cachedVersion)) {
                        mealFetchErrorText = "";
                        runOnUiThread(this::renderMealPage);
                        return;
                    }
                    runOnUiThread(() -> fetchMealPlanForDate(dateIso));
                    return;
                } catch (Exception e) {
                    lastError = e;
                } finally {
                    if (conn != null) {
                        conn.disconnect();
                    }
                }
            }
            mealFetchInFlight = false;
            mealLastFetchAtMs = System.currentTimeMillis();
            Exception finalError = lastError;
            runOnUiThread(() -> {
                mealFetchErrorText = finalError == null ? "連線電腦失敗" : "更新檢查失敗";
                renderMealPage();
            });
        }).start();
    }

    private void fetchMealPlanForDate(String dateIso) {
        fetchMealPlanForDate(dateIso, false);
    }

    private void fetchMealPlanForDate(String dateIso, boolean commitDateOnSuccess) {
        String autoServer = AlarmStore.getAutoSyncServerUrl(this);
        if (autoServer == null || autoServer.trim().isEmpty()) {
            if (commitDateOnSuccess) {
                renderMealPage();
            } else {
                setMealPlanStatusText("未設定電腦 server", true);
            }
            return;
        }
        mealFetchInFlight = true;
        setMealPlanStatusText(commitDateOnSuccess ? "檢查目標日期餐單中..." : "連線電腦餐單中...", true);
        updateMealLastUpdateStatus();
        new Thread(() -> {
            Exception lastError = null;
            for (String baseServer : getAutoServerCandidates(autoServer)) {
                String server = baseServer == null ? "" : baseServer.trim();
                if (server.isEmpty()) {
                    continue;
                }
                if (server.endsWith("/")) {
                    server = server.substring(0, server.length() - 1);
                }
                HttpURLConnection conn = null;
                try {
                    URL url = new URL(server + "/api/mobile-meal-plan?date_iso=" + Uri.encode(dateIso));
                    conn = (HttpURLConnection) url.openConnection();
                    conn.setRequestMethod("GET");
                    conn.setConnectTimeout(HTTP_CONNECT_TIMEOUT_MS);
                    conn.setReadTimeout(HTTP_READ_TIMEOUT_MS);
                    conn.connect();
                    int code = conn.getResponseCode();
                    if (code != HttpURLConnection.HTTP_OK) {
                        lastError = new IOException("HTTP " + code);
                        continue;
                    }
                    String body = readInputStreamText(conn.getInputStream());
                    JSONObject json = new JSONObject(body);
                    if (!json.optBoolean("ok", false)) {
                        lastError = new IOException("電腦未返回餐單");
                        continue;
                    }
                    String contentVersion = json.optString("content_version", "").trim();
                    AlarmStore.saveMealPlanJson(this, dateIso, json.toString(), contentVersion);
                    if (commitDateOnSuccess) {
                        mealSelectedDate = dateIso;
                        mealExpandedKey = "";
                    }
                    mealPlanJson = json;
                    mealPlanJsonDate = dateIso;
                    mealPlanJsonVersion = contentVersion;
                    mealFetchErrorText = "";
                    mealLastFetchAtMs = System.currentTimeMillis();
                    mealFetchInFlight = false;
                    prefetchNeighborMealPlans(dateIso);
                    runOnUiThread(this::renderMealPage);
                    return;
                } catch (Exception e) {
                    lastError = e;
                } finally {
                    if (conn != null) {
                        conn.disconnect();
                    }
                }
            }
            Exception finalError = lastError;
            mealFetchInFlight = false;
            mealLastFetchAtMs = System.currentTimeMillis();
            runOnUiThread(() -> {
                if (commitDateOnSuccess) {
                    mealFetchErrorText = "";
                    renderMealPage();
                } else {
                    mealFetchErrorText = finalError == null ? "連線電腦失敗" : "更新失敗";
                    renderMealPage();
                }
            });
        }).start();
    }

    private void shiftMealDate(int deltaDays) {
        String base = mealSelectedDate == null || mealSelectedDate.trim().isEmpty() ? todayIso() : mealSelectedDate.trim();
        try {
            String[] parts = base.split("-");
            Calendar cal = Calendar.getInstance();
            cal.set(Calendar.YEAR, Integer.parseInt(parts[0]));
            cal.set(Calendar.MONTH, Integer.parseInt(parts[1]) - 1);
            cal.set(Calendar.DAY_OF_MONTH, Integer.parseInt(parts[2]));
            cal.add(Calendar.DAY_OF_MONTH, deltaDays);
            String targetDate = new SimpleDateFormat("yyyy-MM-dd", Locale.getDefault()).format(cal.getTime());
            String today = todayIso();
            String earliestDate = offsetDateIso(today, -1);
            if (earliestDate.isEmpty()) {
                earliestDate = today;
            }
            if (compareIsoDate(targetDate, earliestDate) < 0) {
                targetDate = earliestDate;
            }
            if (!mealKnownLastDate.isEmpty() && compareIsoDate(targetDate, mealKnownLastDate) > 0) {
                targetDate = mealKnownLastDate;
            }
            mealSelectedDate = targetDate;
            mealExpandedKey = "";
            loadMealPlanJsonForSelectedDateFromStore();
            mealFetchErrorText = "";
            renderMealPage();
            refreshMealPlansFromTodayToEnd(targetDate);
        } catch (Exception ignored) {
            setMealDate(todayIso(), true);
        }
    }

    private int compareIsoDate(String left, String right) {
        String a = left == null ? "" : left.trim();
        String b = right == null ? "" : right.trim();
        if (!a.matches("\\d{4}-\\d{2}-\\d{2}") || !b.matches("\\d{4}-\\d{2}-\\d{2}")) {
            return a.compareTo(b);
        }
        return a.compareTo(b);
    }

    private void prefetchNeighborMealPlans(String dateIso) {
        String previous = offsetDateIso(dateIso, -1);
        String next = offsetDateIso(dateIso, 1);
        if (!previous.isEmpty()) {
            prefetchMealPlanCacheOnly(previous);
        }
        if (!next.isEmpty()) {
            prefetchMealPlanCacheOnly(next);
        }
    }

    private void prefetchMealPlanCacheOnly(String dateIso) {
        if (dateIso == null || dateIso.trim().isEmpty()) {
            return;
        }
        if (!AlarmStore.getMealPlanJsonForDate(this, dateIso).trim().isEmpty()) {
            return;
        }
        String autoServer = AlarmStore.getAutoSyncServerUrl(this);
        if (autoServer == null || autoServer.trim().isEmpty()) {
            return;
        }
        new Thread(() -> {
            for (String baseServer : getAutoServerCandidates(autoServer)) {
                String server = baseServer == null ? "" : baseServer.trim();
                if (server.isEmpty()) {
                    continue;
                }
                if (server.endsWith("/")) {
                    server = server.substring(0, server.length() - 1);
                }
                HttpURLConnection conn = null;
                try {
                    URL url = new URL(server + "/api/mobile-meal-plan?date_iso=" + Uri.encode(dateIso));
                    conn = (HttpURLConnection) url.openConnection();
                    conn.setRequestMethod("GET");
                    conn.setConnectTimeout(HTTP_CONNECT_TIMEOUT_MS);
                    conn.setReadTimeout(HTTP_READ_TIMEOUT_MS);
                    conn.connect();
                    if (conn.getResponseCode() != HttpURLConnection.HTTP_OK) {
                        continue;
                    }
                    String body = readInputStreamText(conn.getInputStream());
                    JSONObject json = new JSONObject(body);
                    if (!json.optBoolean("ok", false)) {
                        continue;
                    }
                    AlarmStore.saveMealPlanJson(
                            this,
                            dateIso,
                            json.toString(),
                            json.optString("content_version", "").trim()
                    );
                    return;
                } catch (Exception ignored) {
                } finally {
                    if (conn != null) {
                        conn.disconnect();
                    }
                }
            }
        }).start();
    }

    private void refreshMealPlansFromTodayToEnd(String displayDateIso) {
        String autoServer = AlarmStore.getAutoSyncServerUrl(this);
        if (autoServer == null || autoServer.trim().isEmpty()) {
            return;
        }
        mealFetchInFlight = true;
        updateMealLastUpdateStatus();
        new Thread(() -> {
            String today = todayIso();
            String cursor = offsetDateIso(today, -1);
            if (cursor.isEmpty()) {
                cursor = today;
            }
            int loaded = 0;
            String lastLoadedDate = "";
            boolean displayedDateLoaded = false;
            Exception lastError = null;
            for (int day = 0; day < 45; day++) {
                boolean dateLoaded = false;
                for (String baseServer : getAutoServerCandidates(autoServer)) {
                    String server = baseServer == null ? "" : baseServer.trim();
                    if (server.isEmpty()) {
                        continue;
                    }
                    if (server.endsWith("/")) {
                        server = server.substring(0, server.length() - 1);
                    }
                    HttpURLConnection conn = null;
                    try {
                        URL url = new URL(server + "/api/mobile-meal-plan?date_iso=" + Uri.encode(cursor));
                        conn = (HttpURLConnection) url.openConnection();
                        conn.setRequestMethod("GET");
                        conn.setConnectTimeout(HTTP_CONNECT_TIMEOUT_MS);
                        conn.setReadTimeout(HTTP_READ_TIMEOUT_MS);
                        conn.connect();
                        if (conn.getResponseCode() != HttpURLConnection.HTTP_OK) {
                            continue;
                        }
                        String body = readInputStreamText(conn.getInputStream());
                        JSONObject json = new JSONObject(body);
                        if (!json.optBoolean("ok", false)) {
                            continue;
                        }
                        AlarmStore.saveMealPlanJson(
                                this,
                                cursor,
                                json.toString(),
                                json.optString("content_version", "").trim()
                        );
                        loaded++;
                        lastLoadedDate = cursor;
                        dateLoaded = true;
                        if (cursor.equals(displayDateIso)) {
                            displayedDateLoaded = true;
                            JSONObject displayJson = json;
                            String displayVersion = json.optString("content_version", "").trim();
                            runOnUiThread(() -> {
                                if (!displayDateIso.equals(mealSelectedDate)) {
                                    return;
                                }
                                mealPlanJson = displayJson;
                                mealPlanJsonDate = displayDateIso;
                                mealPlanJsonVersion = displayVersion;
                                mealFetchErrorText = "";
                                renderMealPage();
                            });
                        }
                        break;
                    } catch (Exception e) {
                        lastError = e;
                    } finally {
                        if (conn != null) {
                            conn.disconnect();
                        }
                    }
                }
                if (!dateLoaded) {
                    break;
                }
                String next = offsetDateIso(cursor, 1);
                if (next.isEmpty()) {
                    break;
                }
                cursor = next;
            }
            Exception finalError = lastError;
            boolean finalDisplayedDateLoaded = displayedDateLoaded;
            int finalLoaded = loaded;
            String finalLastLoadedDate = lastLoadedDate;
            mealFetchInFlight = false;
            mealLastFetchAtMs = System.currentTimeMillis();
            runOnUiThread(() -> {
                if (!finalLastLoadedDate.isEmpty()) {
                    mealKnownLastDate = finalLastLoadedDate;
                }
                if (!finalLastLoadedDate.isEmpty()
                        && compareIsoDate(mealSelectedDate, finalLastLoadedDate) > 0) {
                    mealSelectedDate = finalLastLoadedDate;
                    mealExpandedKey = "";
                    loadMealPlanJsonForSelectedDateFromStore();
                    mealFetchErrorText = "";
                    renderMealPage();
                    return;
                }
                if (!displayDateIso.equals(mealSelectedDate)) {
                    return;
                }
                if (!finalDisplayedDateLoaded) {
                    loadMealPlanJsonForSelectedDateFromStore();
                }
                mealFetchErrorText = finalLoaded == 0 && finalError != null ? "連線電腦失敗" : "";
                renderMealPage();
            });
        }).start();
    }

    private String offsetDateIso(String dateIso, int deltaDays) {
        String value = dateIso == null ? "" : dateIso.trim();
        try {
            String[] parts = value.split("-");
            Calendar cal = Calendar.getInstance();
            cal.set(Calendar.YEAR, Integer.parseInt(parts[0]));
            cal.set(Calendar.MONTH, Integer.parseInt(parts[1]) - 1);
            cal.set(Calendar.DAY_OF_MONTH, Integer.parseInt(parts[2]));
            cal.add(Calendar.DAY_OF_MONTH, deltaDays);
            return new SimpleDateFormat("yyyy-MM-dd", Locale.getDefault()).format(cal.getTime());
        } catch (Exception ignored) {
            return "";
        }
    }

    private void setMealDate(String dateIso, boolean forceFetch) {
        mealSelectedDate = dateIso == null || dateIso.trim().isEmpty() ? todayIso() : dateIso.trim();
        mealExpandedKey = "";
        loadMealPlanJsonForSelectedDateFromStore();
        renderMealPage();
        ensureMealPlanLoaded(forceFetch);
    }

    private String defaultExpandedMeal(JSONObject mealPlan, JSONObject resolved) {
        String[] meals = new String[]{"早餐", "午餐", "小食", "晚餐"};
        ArrayList<String> visible = new ArrayList<>();
        ArrayList<Integer> times = new ArrayList<>();
        for (String meal : meals) {
            String timeText = cleanMealText(resolved.optString(meal, ""));
            int minutes = firstClockMinutes(timeText);
            if (minutes < 0) {
                continue;
            }
            visible.add(meal);
            times.add(minutes);
        }
        if (visible.isEmpty()) {
            return "";
        }
        if (!todayIso().equals(mealSelectedDate)) {
            return visible.get(0);
        }
        Calendar now = Calendar.getInstance();
        int nowMinutes = now.get(Calendar.HOUR_OF_DAY) * 60 + now.get(Calendar.MINUTE);
        for (int i = 0; i < visible.size(); i++) {
            if (nowMinutes < times.get(i) + 60) {
                return visible.get(i);
            }
        }
        return visible.get(visible.size() - 1);
    }

    private String mealMacroLine(JSONObject mealPlan, String meal) {
        JSONObject mealNutrients = mealPlan.optJSONObject("meal_nutrients");
        JSONObject nutrients = mealNutrients == null ? null : mealNutrients.optJSONObject(meal);
        if (nutrients == null) {
            return "";
        }
        return formatMetricValue("kcal", nutrients.optDouble("kcal", 0.0))
                + " kcal  P" + formatNumber(nutrients.optDouble("protein_g", 0.0))
                + "  C" + formatNumber(nutrients.optDouble("carb_g", 0.0))
                + "  F" + formatNumber(nutrients.optDouble("fat_total_g", 0.0));
    }

    private String formatMealMacroForSide(String macroText) {
        String text = macroText == null ? "" : macroText.trim();
        if (text.isEmpty()) {
            return " ";
        }
        int proteinIndex = text.indexOf("  P");
        if (proteinIndex < 0) {
            proteinIndex = text.indexOf(" P");
        }
        if (proteinIndex > 0) {
            String kcal = text.substring(0, proteinIndex).trim();
            String macros = text.substring(proteinIndex).trim().replace("  ", " ");
            return kcal + "\n" + macros;
        }
        return text;
    }

    private String formatItemAmount(Object grams) {
        if (grams instanceof Number) {
            return formatNumber(((Number) grams).doubleValue()) + "g";
        }
        return "";
    }

    private int keyIndex(String key) {
        if ("kcal".equals(key)) return 0;
        if ("protein_g".equals(key)) return 1;
        if ("carb_g".equals(key)) return 2;
        if ("sugar_g".equals(key)) return 3;
        if ("cholesterol_mg".equals(key)) return 4;
        if ("sodium_mg".equals(key)) return 5;
        if ("calcium_mg".equals(key)) return 6;
        if ("fat_total_g".equals(key)) return 7;
        if ("fat_sat_g".equals(key)) return 8;
        if ("fat_trans_g".equals(key)) return 9;
        return -1;
    }

    private double arrayDoubleAt(JSONArray array, int index) {
        if (array == null || index < 0 || index >= array.length()) {
            return 0.0;
        }
        return array.optDouble(index, 0.0);
    }

    private boolean boolArrayAt(JSONArray array, int index) {
        if (array == null || index < 0 || index >= array.length()) {
            return false;
        }
        return array.optBoolean(index, false);
    }

    private String formatMetricValue(String key, double value) {
        if ("kcal".equals(key)) {
            return formatNumber(value);
        }
        if ("sodium_mg".equals(key) || "calcium_mg".equals(key)) {
            return formatNumber(value) + "mg";
        }
        return formatNumber(value) + "g";
    }

    private String formatTargetRule(String key, JSONObject indicator, double kcalTotal) {
        if (indicator == null) {
            return "";
        }
        String kind = indicator.optString("kind", "");
        if (("fat_total_g".equals(key) || "fat_sat_g".equals(key) || "fat_trans_g".equals(key))
                && "fat_pct".equals(kind)) {
            double pct = indicator.optDouble("fat_pct", 0.0);
            if (pct > 0.0 && kcalTotal > 0.0) {
                return "<" + formatNumber(kcalTotal * pct / 9.0) + "g";
            }
        }
        return indicator.optString("raw", "").trim();
    }

    private String formatDelta(String key, double delta) {
        if (Math.abs(delta) < 0.05d) {
            return "OK";
        }
        String sign = delta > 0 ? "+" : "";
        if ("kcal".equals(key)) {
            return sign + formatNumber(delta) + " kcal";
        }
        if ("sodium_mg".equals(key) || "calcium_mg".equals(key)) {
            return sign + formatNumber(delta) + "mg";
        }
        return sign + formatNumber(delta) + "g";
    }

    private String formatNumber(double value) {
        if (Math.abs(value - Math.rint(value)) < 0.05d) {
            return String.valueOf((int) Math.rint(value));
        }
        return String.format(Locale.getDefault(), "%.1f", value);
    }

    private int firstClockMinutes(String text) {
        if (text == null) {
            return -1;
        }
        Matcher matcher = Pattern.compile("(\\d{1,2}):(\\d{2})").matcher(text);
        if (!matcher.find()) {
            return -1;
        }
        try {
            int hour = Integer.parseInt(matcher.group(1));
            int minute = Integer.parseInt(matcher.group(2));
            return hour * 60 + minute;
        } catch (NumberFormatException e) {
            return -1;
        }
    }

    private void pollLatestAlarms() {
        statusView.setText("同步中...");
        AlarmAutoSyncReceiver.pollNow(this, result -> runOnUiThread(() -> {
            if (result != null && result.ok && result.updated) {
                loadDraftFromStore();
                render();
                Toast.makeText(this, result.message, Toast.LENGTH_LONG).show();
                return;
            }
            String message = result == null ? "同步失敗" : result.message;
            statusView.setText(message == null || message.isEmpty() ? statusText() : message);
            Toast.makeText(this, message == null || message.isEmpty() ? "同步完成" : message, Toast.LENGTH_SHORT).show();
        }));
    }

    private LinearLayout headerRow() {
        LinearLayout row = baseRow(0xFF8ED3EA);
        row.addView(iconCell(0xFF8ED3EA));
        row.addView(cell("時間", 13, Gravity.CENTER, 0.78f, 0xFF000000, 0xFF8ED3EA));
        row.addView(cell("內容", 13, Gravity.CENTER, 1.48f, 0xFF000000, 0xFF8ED3EA));
        row.addView(cell("操作", 13, Gravity.CENTER, 1.24f, 0xFF000000, 0xFF8ED3EA));
        return row;
    }

    private LinearLayout alarmRow(int index, JSONObject alarm) {
        LinearLayout row = baseRow(0xFFFFFFFF);
        boolean dimmed = shouldDimAlarm(alarm);
        row.setAlpha(dimmed ? 0.45f : 1f);

        ImageView icon = alarmIconCell();
        icon.setOnClickListener(v -> editTime(index));
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
        row.addView(time);

        TextView label = cell(
                alarm.optString("label", "鬧鐘"),
                13,
                Gravity.LEFT | Gravity.CENTER_VERTICAL,
                1.48f,
                0xFF000000,
                0xFFFFFFFF
        );
        label.setOnClickListener(v -> editLabel(index));
        row.addView(label);

        LinearLayout actions = new LinearLayout(this);
        actions.setOrientation(LinearLayout.HORIZONTAL);
        actions.setGravity(Gravity.CENTER);
        actions.setBackgroundColor(0xFFFFFFFF);
        actions.setPadding(dp(2), dp(1), dp(2), dp(1));
        actions.addView(actionButton("插入", () -> insertAlarm(index)));
        actions.addView(actionButton("刪除", () -> deleteDraftAlarm(index)));
        row.addView(actions, weightedParams(1.24f));
        return row;
    }

    private void addBlankRows(int count) {
        for (int i = 0; i < count; i++) {
            LinearLayout row = baseRow(0xFFFFFFFF);
            row.addView(iconCell(0xFFFFFFFF));
            row.addView(cell("", 13, Gravity.CENTER, 0.78f, 0xFF000000, 0xFFFFFFFF));
            row.addView(cell("", 13, Gravity.CENTER, 1.48f, 0xFF000000, 0xFFFFFFFF));
            row.addView(cell("", 13, Gravity.CENTER, 1.24f, 0xFF000000, 0xFFFFFFFF));
            tableView.addView(row, fullWidthWrapHeight());
        }
    }

    private LinearLayout baseRow(int backgroundColor) {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setBackgroundColor(backgroundColor);
        return row;
    }

    private ImageView iconCell(int backgroundColor) {
        ImageView view = new ImageView(this);
        view.setBackgroundColor(backgroundColor);
        view.setPadding(dp(5), dp(5), dp(2), dp(5));
        view.setLayoutParams(iconCellParams());
        return view;
    }

    private ImageView alarmIconCell() {
        ImageView view = new ImageView(this);
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
        TextView view = new TextView(this);
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

    private Button actionButton(String text, Runnable action) {
        Button button = new Button(this);
        button.setText(text);
        button.setTextSize(9);
        button.setGravity(Gravity.CENTER);
        button.setAllCaps(false);
        button.setMinWidth(0);
        button.setMinimumWidth(0);
        button.setMinHeight(dp(24));
        button.setMinimumHeight(dp(24));
        button.setPadding(dp(2), 0, dp(2), 0);
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(0, dp(28), 1f);
        params.setMargins(dp(1), 0, dp(1), 0);
        button.setLayoutParams(params);
        button.setOnClickListener(v -> action.run());
        return button;
    }

    private boolean shouldDimAlarm(JSONObject alarm) {
        if (alarm == null) {
            return false;
        }
        return alarm.optLong("fired_at_epoch_ms", 0L) > 0L
                || alarm.optLong("trigger_at_epoch_ms", Long.MAX_VALUE) <= System.currentTimeMillis();
    }

    private void editTime(int index) {
        JSONObject alarm = draftAlarms.optJSONObject(index);
        if (alarm == null) {
            return;
        }
        Calendar cal = Calendar.getInstance();
        cal.setTimeInMillis(alarm.optLong("trigger_at_epoch_ms"));

        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setPadding(dp(18), dp(4), dp(18), 0);

        LinearLayout inputs = new LinearLayout(this);
        inputs.setOrientation(LinearLayout.HORIZONTAL);
        inputs.setGravity(Gravity.CENTER);

        EditText hourInput = timePartInput(String.format(Locale.getDefault(), "%02d", cal.get(Calendar.HOUR_OF_DAY)));
        EditText minuteInput = timePartInput(String.format(Locale.getDefault(), "%02d", cal.get(Calendar.MINUTE)));
        TextView colon = new TextView(this);
        colon.setText(":");
        colon.setTextSize(34);
        colon.setGravity(Gravity.CENTER);
        colon.setTextColor(0xFF111827);

        inputs.addView(hourInput, weightedParams(1f));
        inputs.addView(colon, new LinearLayout.LayoutParams(dp(28), LinearLayout.LayoutParams.WRAP_CONTENT));
        inputs.addView(minuteInput, weightedParams(1f));
        box.addView(inputs, fullWidthWrapHeight());

        LinearLayout labels = new LinearLayout(this);
        labels.setOrientation(LinearLayout.HORIZONTAL);
        labels.setGravity(Gravity.CENTER);
        labels.addView(timePartLabel("Hour"), weightedParams(1f));
        labels.addView(timePartLabel(""), new LinearLayout.LayoutParams(dp(28), LinearLayout.LayoutParams.WRAP_CONTENT));
        labels.addView(timePartLabel("Minute"), weightedParams(1f));
        box.addView(labels, fullWidthWrapHeight());

        hourInput.addTextChangedListener(new TextWatcher() {
            @Override public void beforeTextChanged(CharSequence s, int start, int count, int after) {}
            @Override public void onTextChanged(CharSequence s, int start, int before, int count) {
                if (digitsOnly(s).length() >= 2) {
                    minuteInput.requestFocus();
                    minuteInput.selectAll();
                }
            }
            @Override public void afterTextChanged(Editable s) {}
        });
        minuteInput.addTextChangedListener(new TextWatcher() {
            @Override public void beforeTextChanged(CharSequence s, int start, int count, int after) {}
            @Override public void onTextChanged(CharSequence s, int start, int before, int count) {
                if (digitsOnly(s).length() >= 2) {
                    hideKeyboard(minuteInput);
                }
            }
            @Override public void afterTextChanged(Editable s) {}
        });

        AlertDialog dialog = new AlertDialog.Builder(this)
                .setTitle("Select time")
                .setView(box)
                .setNegativeButton("Cancel", null)
                .setPositiveButton("OK", null)
                .create();
        dialog.setOnShowListener(d -> {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v -> {
                int hour = parseTwoDigit(hourInput, -1);
                int minute = parseTwoDigit(minuteInput, -1);
                if (hour < 0 || hour > 23 || minute < 0 || minute > 59) {
                    Toast.makeText(this, "請輸入 00:00 至 23:59", Toast.LENGTH_SHORT).show();
                    return;
                }
                cal.set(Calendar.HOUR_OF_DAY, hour);
                cal.set(Calendar.MINUTE, minute);
                cal.set(Calendar.SECOND, 0);
                cal.set(Calendar.MILLISECOND, 0);
                setAlarmTime(index, cal.getTimeInMillis());
                dialog.dismiss();
            });
            hourInput.requestFocus();
            hourInput.selectAll();
            hourInput.postDelayed(() -> {
                InputMethodManager imm = (InputMethodManager) getSystemService(INPUT_METHOD_SERVICE);
                if (imm != null) {
                    imm.showSoftInput(hourInput, InputMethodManager.SHOW_IMPLICIT);
                }
            }, 180);
        });
        dialog.show();
    }

    private EditText timePartInput(String value) {
        EditText input = new EditText(this);
        input.setText(value);
        input.setTextSize(42);
        input.setGravity(Gravity.CENTER);
        input.setSelectAllOnFocus(true);
        input.setSingleLine(true);
        input.setFilters(new InputFilter[]{new InputFilter.LengthFilter(2)});
        input.setInputType(InputType.TYPE_CLASS_NUMBER);
        input.setPadding(dp(10), dp(8), dp(10), dp(8));
        return input;
    }

    private TextView timePartLabel(String text) {
        TextView label = new TextView(this);
        label.setText(text);
        label.setTextSize(14);
        label.setTextColor(0xFF6B7280);
        label.setGravity(Gravity.CENTER);
        label.setPadding(0, dp(4), 0, 0);
        return label;
    }

    private String digitsOnly(CharSequence s) {
        return String.valueOf(s == null ? "" : s).replaceAll("\\D+", "");
    }

    private int parseTwoDigit(EditText input, int fallback) {
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
        InputMethodManager imm = (InputMethodManager) getSystemService(INPUT_METHOD_SERVICE);
        if (imm != null) {
            imm.hideSoftInputFromWindow(input.getWindowToken(), 0);
        }
    }

    private void editLabel(int index) {
        JSONObject alarm = draftAlarms.optJSONObject(index);
        if (alarm == null) {
            return;
        }
        EditText input = new EditText(this);
        input.setSingleLine(false);
        input.setMinLines(1);
        input.setText(alarm.optString("label", "鬧鐘"));
        new AlertDialog.Builder(this)
                .setTitle("內容")
                .setView(input)
                .setNegativeButton("Cancel", null)
                .setPositiveButton("OK", (dialog, which) -> {
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
            Toast.makeText(this, "更新時間失敗", Toast.LENGTH_SHORT).show();
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
            Toast.makeText(this, "更新內容失敗", Toast.LENGTH_SHORT).show();
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
                if (lastTriggerAt > System.currentTimeMillis() && todayIso().equals(draftDate)) {
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

    private void saveDraftAlarms() {
        if (!AlarmScheduler.canScheduleExactAlarm(this)) {
            Toast.makeText(this, "請先允許精準鬧鐘權限", Toast.LENGTH_LONG).show();
            AlarmScheduler.requestExactAlarmPermission(this);
            render();
            return;
        }
        shiftEmptyMessage = "";
        sortDraftAlarms();
        if (draftAlarms.length() == 0) {
            AlarmScheduler.cancelAll(this);
        } else {
            AlarmScheduler.schedulePlan(this, draftAlarms, 0L, draftDate, draftRosterCode);
        }
        loadDraftFromStore();
        render();
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
        return new SimpleDateFormat("HH:mm", Locale.getDefault()).format(millis);
    }

    private String formatTime(long millis) {
        return new SimpleDateFormat("yyyy-MM-dd HH:mm", Locale.getDefault()).format(millis);
    }

    private String formatIso(long millis) {
        return new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ssZ", Locale.getDefault()).format(millis);
    }

    private void requestNotificationPermissionIfNeeded() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU
                && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 9001);
        }
    }

    private void requestFullScreenIntentPermissionIfNeeded() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            return;
        }
        NotificationManager notificationManager =
                (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        if (notificationManager != null && !notificationManager.canUseFullScreenIntent()) {
            Toast.makeText(this, "請允許全螢幕鬧鐘通知", Toast.LENGTH_LONG).show();
            AlarmScheduler.requestFullScreenIntentPermission(this);
        }
    }

    private void requestOverlayPermissionIfNeeded() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.M || Settings.canDrawOverlays(this)) {
            return;
        }
        Toast.makeText(this, "請允許顯示喺其他 App 上面", Toast.LENGTH_LONG).show();
        Intent intent = new Intent(
                Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                Uri.parse("package:" + getPackageName())
        );
        startActivity(intent);
    }

    private void handleTestDailyImportIntent(Intent intent) {
        if (intent == null) {
            return;
        }
        boolean requested = ACTION_TEST_DAILY_IMPORT.equals(intent.getAction())
                || intent.getBooleanExtra("test_daily_import", false);
        Log.d(TAG, "Test daily import requested=" + requested + " action=" + intent.getAction());
        if (!requested) {
            return;
        }
        statusView.setText("測試自動 import 中...");
        new Thread(() -> {
            ScheduleGridAutoImporter.ImportResult result;
            try {
                result = ScheduleGridAutoImporter.importFromPc(this);
            } catch (Exception e) {
                result = new ScheduleGridAutoImporter.ImportResult(false, 0, "", "", e.getMessage());
            }
            ScheduleGridAutoImporter.ImportResult finalResult = result;
            runOnUiThread(() -> {
                if (finalResult.ok) {
                    shiftEmptyMessage = "";
                    loadDraftFromStore();
                    render();
                    String extra = finalResult.variantCount > 1
                            ? "，已載入 " + finalResult.variantCount + " 個更碼"
                            : "";
                    Toast.makeText(
                            this,
                            "測試自動 import 成功：" + finalResult.alarmCount + " 個鬧鐘" + extra,
                            Toast.LENGTH_LONG
                    ).show();
                } else {
                    showScheduleGridImportFailure(finalResult, "測試自動 import 失敗");
                }
            });
        }).start();
    }

}
