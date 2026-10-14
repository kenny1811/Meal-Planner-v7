package com.example.oneshotalarm;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.util.Log;
import android.view.Gravity;
import android.view.View;
import android.view.Window;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

/**
 * 四個 tab 嘅殼：標題列（版本＋server 狀態）、tab 列、四個 section。
 * 餐單頁＝MealPlanView、行位表＝ShiftTableView、報更＝DutyReportView、報開收工＝OnOffDutyView，
 * 各自收 activity + container + 回呼；呢度淨係做 lifecycle、tab 切換、滑動轉日、server 輪詢。
 */
public class MainActivity extends Activity {
    private static final String TAG = "OneShotAlarm";
    private static final int HTTP_READ_TIMEOUT_MS = 7000;
    private static final int PAGE_MEAL = 0;
    private static final int PAGE_SHIFT = 1;
    private static final int PAGE_DUTY = 2;
    private static final int PAGE_ONOFF = 3;
    private static final int SERVER_STATUS_CHECKING = 0;
    private static final int SERVER_STATUS_ONLINE = 1;
    private static final int SERVER_STATUS_OFFLINE = 2;
    private static final int SERVER_STATUS_ERROR = 3;
    private static final long SERVER_STATUS_POLL_MS = 30000L;
    private static final long DUTY_STATUS_POLL_MS = 10000L;
    /**
     * 連唔到電腦嗰陣改用呢個梯級重試（毫秒），通返就回復 SERVER_STATUS_POLL_MS。
     * 出街由 Wi-Fi 轉流動數據，NordLynx tunnel 要幾秒至十幾秒先重建好；
     * 固定 30 秒一敲門會白等成分鐘先話你知 online。
     */
    private static final long[] SERVER_STATUS_RETRY_MS = new long[]{2000L, 4000L, 8000L, 15000L};
    private static final String ACTION_TEST_DAILY_IMPORT = "com.example.oneshotalarm.ACTION_TEST_DAILY_IMPORT";

    private PanelUi ui;
    private LinearLayout mealSection;
    private MealPlanView mealPlanView;
    private LinearLayout shiftSection;
    private ShiftTableView shiftTableView;
    private LinearLayout dutySection;
    private DutyReportView dutyReportView;
    private LinearLayout onoffSection;
    private OnOffDutyView onOffDutyView;
    private Button mealTabButton;
    private Button shiftTabButton;
    private Button dutyTabButton;
    private Button onoffTabButton;
    private TextView serverStatusView;
    private boolean serverStatusCheckInFlight = false;
    /** onResume→true、onPause→false：in-flight 嗰次返嚟見到 paused 就唔好再排下一次。 */
    private boolean serverStatusPollingActive = false;
    private final android.os.Handler serverStatusHandler =
            new android.os.Handler(android.os.Looper.getMainLooper());
    private final android.os.Handler dutyStatusHandler =
            new android.os.Handler(android.os.Looper.getMainLooper());
    private boolean resumed = false;
    private boolean storedPlanDirty = false;
    private int currentPage = PAGE_MEAL;
    private SharedPreferences planPreferences;
    private final Runnable reloadStoredPlan = () -> {
        if (!resumed || !storedPlanDirty || !getWindow().getDecorView().hasWindowFocus()) {
            return; // Dialog inputs keep their draft until the dialog closes.
        }
        storedPlanDirty = false;
        shiftTableView.loadFromStore();
        shiftTableView.render();
    };
    private final SharedPreferences.OnSharedPreferenceChangeListener planStoreListener = (prefs, key) -> {
        if ("alarms_json".equals(key) || "plan_date".equals(key) || "roster_code".equals(key)) {
            storedPlanDirty = true;
            // savePlan updates three keys together; refresh once after the writer returns.
            dutyStatusHandler.removeCallbacks(reloadStoredPlan);
            dutyStatusHandler.post(reloadStoredPlan);
        }
    };
    private final Runnable pollDutyStatus = new Runnable() {
        @Override public void run() {
            if (!resumed) {
                return;
            }
            if (currentPage == PAGE_DUTY) {
                dutyReportView.refreshStatus();
            } else if (currentPage == PAGE_ONOFF) {
                onOffDutyView.refreshStatus();
            }
            dutyStatusHandler.postDelayed(this, DUTY_STATUS_POLL_MS);
        }
    };
    /** 連續失敗次數：決定用 SERVER_STATUS_RETRY_MS 邊一級。 */
    private int serverStatusFailStreak = 0;
    private float swipeDownX = 0f;
    private float swipeDownY = 0f;
    private android.graphics.Typeface regularTypeface;
    private android.graphics.Typeface boldTypeface;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        configureSystemBars();
        PhoneCaptureHttpServer.start(this);
        buildUi();
        loadFromStore();
        render();
        handleTestDailyImportIntent(getIntent());
        handleOpenTabIntent(getIntent());
        NextAlarmWidgetProvider.updateAll(this);
        requestNotificationPermissionIfNeeded();
        maybeRequestBatteryExemption();
        AppUpdater.autoCheck(this);
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        loadFromStore();
        render();
        handleTestDailyImportIntent(intent);
        handleOpenTabIntent(intent);
    }

    @Override
    protected void onResume() {
        super.onResume();
        resumed = true;
        planPreferences = getSharedPreferences(AlarmStore.PREFS, MODE_PRIVATE);
        planPreferences.registerOnSharedPreferenceChangeListener(planStoreListener);
        storedPlanDirty = false;
        loadFromStore();
        mealPlanView.resetExpanded();  // 每次返返嚟都用返當時嘅 default 餐
        render();
        NextAlarmWidgetProvider.updateAll(this);
        scheduleServerStatusChecks();
        dutyStatusHandler.removeCallbacks(pollDutyStatus);
        dutyStatusHandler.postDelayed(pollDutyStatus, DUTY_STATUS_POLL_MS);
        if (currentPage == PAGE_MEAL) {
            mealPlanView.refresh();
        } else if (currentPage == PAGE_DUTY && dutyReportView != null) {
            dutyReportView.refresh();
        } else if (currentPage == PAGE_ONOFF && onOffDutyView != null) {
            onOffDutyView.refresh();
        }
    }

    @Override
    protected void onPause() {
        super.onPause();
        resumed = false;
        if (planPreferences != null) {
            planPreferences.unregisterOnSharedPreferenceChangeListener(planStoreListener);
        }
        dutyStatusHandler.removeCallbacksAndMessages(null);
        serverStatusPollingActive = false;
        serverStatusHandler.removeCallbacksAndMessages(null);
        mealPlanView.onPause();
    }

    @Override
    public void onWindowFocusChanged(boolean hasFocus) {
        super.onWindowFocusChanged(hasFocus);
        if (hasFocus && storedPlanDirty) {
            dutyStatusHandler.removeCallbacks(reloadStoredPlan);
            dutyStatusHandler.post(reloadStoredPlan);
        }
    }

    private void scheduleServerStatusChecks() {
        serverStatusHandler.removeCallbacksAndMessages(null);
        serverStatusPollingActive = true;
        serverStatusFailStreak = 0;
        checkServerStatus();
    }

    /** 下一次幾時敲門：通嘅話 30 秒一次，唔通就 2/4/8/15 秒追住試。 */
    private void scheduleNextServerStatusCheck(boolean online) {
        serverStatusHandler.removeCallbacksAndMessages(null);
        long delay;
        if (online) {
            serverStatusFailStreak = 0;
            delay = SERVER_STATUS_POLL_MS;
        } else {
            int idx = Math.min(serverStatusFailStreak, SERVER_STATUS_RETRY_MS.length - 1);
            delay = SERVER_STATUS_RETRY_MS[idx];
            serverStatusFailStreak++;
        }
        serverStatusHandler.postDelayed(this::checkServerStatus, delay);
    }

    private void checkServerStatus() {
        if (serverStatusCheckInFlight) {
            // 上一次仲喺度等（meshnet 最長 9 秒），遲啲再嚟——唔好就咁 return，
            // 否則成條輪詢鏈斷咗，之後永遠唔會再敲門。
            serverStatusHandler.removeCallbacksAndMessages(null);
            serverStatusHandler.postDelayed(this::checkServerStatus, 1000L);
            return;
        }
        serverStatusCheckInFlight = true;
        new Thread(() -> {
            int state;
            String message;
            try {
                ApiClient.request(this, "GET", "/health", (String) null, HTTP_READ_TIMEOUT_MS);
                state = SERVER_STATUS_ONLINE;
                message = "";
            } catch (Exception e) {
                // ApiClient 已經試齊 LAN/meshnet。回到 "HTTP <code>" ＝server 有應但唔正常；
                // 其餘（connect/timeout）＝offline。
                String detail = e.getMessage() == null ? "" : e.getMessage().trim();
                boolean httpError = detail.startsWith("HTTP ");
                state = httpError ? SERVER_STATUS_ERROR : SERVER_STATUS_OFFLINE;
                message = httpError ? detail : "";
            }
            int finalState = state;
            String finalMessage = message;
            runOnUiThread(() -> {
                serverStatusCheckInFlight = false;
                applyServerStatus(finalState, finalMessage);
                // activity 已經 pause／finish：唔好再 post，否則背景每 30 秒照打 /health 直到 process 死。
                if (serverStatusPollingActive) {
                    scheduleNextServerStatusCheck(finalState == SERVER_STATUS_ONLINE);
                }
            });
        }).start();
    }

    private void applyServerStatus(int state, String message) {
        if (serverStatusView == null) {
            return;
        }
        String text;
        int color;
        if (state == SERVER_STATUS_ONLINE) {
            text = "Online";
            color = 0xFF3D9960;
        } else if (state == SERVER_STATUS_OFFLINE) {
            text = "Offline";
            color = 0xFFB91C1C;
        } else if (state == SERVER_STATUS_ERROR) {
            text = message == null || message.trim().isEmpty() ? "Error" : message.trim();
            color = 0xFFD97706;
        } else {
            text = "…";
            color = 0xFF94A3B8;
        }
        serverStatusView.setText(text);
        serverStatusView.setTextColor(color);
        serverStatusView.setBackground(ui.roundedBg(0xFFFFFFFF, 10, color, 1));
    }

    @Override
    public boolean dispatchTouchEvent(android.view.MotionEvent ev) {
        if (currentPage == PAGE_MEAL || currentPage == PAGE_DUTY || currentPage == PAGE_ONOFF) {
            if (ev.getAction() == android.view.MotionEvent.ACTION_DOWN) {
                swipeDownX = ev.getX();
                swipeDownY = ev.getY();
            } else if (ev.getAction() == android.view.MotionEvent.ACTION_UP) {
                float dx = ev.getX() - swipeDownX;
                float dy = ev.getY() - swipeDownY;
                float threshold = dp(72);
                if (Math.abs(dx) > threshold && Math.abs(dx) > Math.abs(dy) * 1.8f) {
                    if (currentPage == PAGE_MEAL) {
                        mealPlanView.shiftDate(dx < 0 ? 1 : -1);
                    } else if (currentPage == PAGE_ONOFF && onOffDutyView != null) {
                        onOffDutyView.shiftDate(dx < 0 ? 1 : -1);
                    } else if (currentPage == PAGE_DUTY && dutyReportView != null) {
                        dutyReportView.shiftDate(dx < 0 ? 1 : -1);
                    }
                    return true;
                }
            }
        }
        return super.dispatchTouchEvent(ev);
    }

    private void buildUi() {
        ui = new PanelUi(this, regularTypeface(), boldTypeface());

        ScrollView scrollView = new ScrollView(this);
        scrollView.setFillViewport(true);
        scrollView.setClipToPadding(false);
        scrollView.setVerticalScrollBarEnabled(true);
        scrollView.setScrollbarFadingEnabled(false);
        scrollView.setBackgroundColor(0xFFFFFFFF);

        // outer = 固定頂部（標題+tab）+ 下面一個 ScrollView；tab 及以上唔捲。
        LinearLayout outer = new LinearLayout(this);
        outer.setOrientation(LinearLayout.VERTICAL);
        outer.setBackgroundColor(0xFFFFFFFF);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(0, 0, 0, 0);
        root.setBackgroundColor(0xFFFFFFFF);

        TextView title = new TextView(this);
        title.setText("門前直樹v" + AppUpdater.currentVersionName(this));
        title.setTextSize(15);
        title.setTextColor(0xFF053B24);
        title.setTypeface(boldTypeface());
        title.setGravity(Gravity.CENTER);
        title.setPadding(dp(6), dp(0), dp(6), dp(1));
        // 撳標題開 in-app updater（電話自己裝 / 推手錶裝，唔靠 adb）。
        title.setOnClickListener(v -> AppUpdater.showUpdateDialog(this));

        // 標題行用 FrameLayout：status badge 疊喺右邊，唔佔額外高度。
        android.widget.FrameLayout titleBar = new android.widget.FrameLayout(this);
        titleBar.addView(title, new android.widget.FrameLayout.LayoutParams(
                android.widget.FrameLayout.LayoutParams.MATCH_PARENT,
                android.widget.FrameLayout.LayoutParams.WRAP_CONTENT
        ));
        serverStatusView = new TextView(this);
        serverStatusView.setTextSize(9);
        serverStatusView.setTypeface(boldTypeface());
        serverStatusView.setGravity(Gravity.CENTER);
        serverStatusView.setIncludeFontPadding(false);
        serverStatusView.setSingleLine(true);
        serverStatusView.setPadding(dp(8), dp(2), dp(8), dp(2));
        serverStatusView.setOnClickListener(v -> checkServerStatus());
        applyServerStatus(SERVER_STATUS_CHECKING, "");
        android.widget.FrameLayout.LayoutParams badgeParams = new android.widget.FrameLayout.LayoutParams(
                android.widget.FrameLayout.LayoutParams.WRAP_CONTENT,
                android.widget.FrameLayout.LayoutParams.WRAP_CONTENT,
                Gravity.END | Gravity.CENTER_VERTICAL
        );
        badgeParams.setMargins(0, 0, dp(10), 0);
        titleBar.addView(serverStatusView, badgeParams);
        outer.addView(titleBar, ui.fullWidth());

        LinearLayout tabRow = new LinearLayout(this);
        tabRow.setOrientation(LinearLayout.HORIZONTAL);
        tabRow.setPadding(dp(8), 0, dp(8), dp(1));
        tabRow.setBackgroundColor(0xFFFBF8EF);

        mealTabButton = buildTopTabButton("餐單");
        shiftTabButton = buildTopTabButton("行位表");
        dutyTabButton = buildTopTabButton("報平安更");
        onoffTabButton = buildTopTabButton("報開/收工");
        // 四個 tab 迫一行：呢兩個略細 + 單行先擺得落。
        dutyTabButton.setTextSize(11);
        onoffTabButton.setTextSize(11);
        dutyTabButton.setMaxLines(1);
        onoffTabButton.setMaxLines(1);
        dutyTabButton.setPadding(dp(2), 0, dp(2), 0);
        onoffTabButton.setPadding(dp(2), 0, dp(2), 0);
        mealTabButton.setOnClickListener(v -> switchPage(PAGE_MEAL));
        shiftTabButton.setOnClickListener(v -> switchPage(PAGE_SHIFT));
        dutyTabButton.setOnClickListener(v -> switchPage(PAGE_DUTY));
        onoffTabButton.setOnClickListener(v -> switchPage(PAGE_ONOFF));
        tabRow.addView(mealTabButton, ui.weighted(1f));
        tabRow.addView(shiftTabButton, ui.weighted(1f));
        tabRow.addView(dutyTabButton, ui.weighted(1f));
        tabRow.addView(onoffTabButton, ui.weighted(1f));
        outer.addView(tabRow, ui.fullWidth());

        mealSection = new LinearLayout(this);
        mealSection.setOrientation(LinearLayout.VERTICAL);
        mealSection.setPadding(dp(10), 0, dp(10), dp(10));
        mealSection.setBackgroundColor(0xFFFBF8EF);
        mealPlanView = new MealPlanView(this, mealSection, regularTypeface(), boldTypeface(),
                () -> currentPage == PAGE_MEAL);
        root.addView(mealSection, ui.fullWidth());

        shiftSection = new LinearLayout(this);
        shiftSection.setOrientation(LinearLayout.VERTICAL);
        shiftSection.setPadding(0, 0, 0, 0);
        shiftSection.setBackgroundColor(0xFFFFFFFF);
        shiftTableView = new ShiftTableView(this, shiftSection, regularTypeface(), boldTypeface(),
                () -> mealPlanView.hasPlan());
        root.addView(shiftSection, ui.fullWidth());

        dutySection = new LinearLayout(this);
        dutySection.setOrientation(LinearLayout.VERTICAL);
        dutySection.setPadding(0, dp(2), 0, dp(10));
        dutySection.setBackgroundColor(0xFFFFFFFF);
        dutyReportView = new DutyReportView(this, dutySection, regularTypeface(), boldTypeface());
        root.addView(dutySection, ui.fullWidth());

        onoffSection = new LinearLayout(this);
        onoffSection.setOrientation(LinearLayout.VERTICAL);
        onoffSection.setPadding(0, dp(2), 0, dp(10));
        onoffSection.setBackgroundColor(0xFFFFFFFF);
        onOffDutyView = new OnOffDutyView(this, onoffSection, regularTypeface(), boldTypeface());
        root.addView(onoffSection, ui.fullWidth());

        scrollView.addView(
                root,
                new ScrollView.LayoutParams(
                    ScrollView.LayoutParams.MATCH_PARENT,
                    ScrollView.LayoutParams.WRAP_CONTENT
                )
        );
        outer.addView(scrollView, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, 0, 1f));
        applySafeAreaPadding(outer, scrollView);
        setContentView(outer);
        switchPage(currentPage);
    }

    private Button buildTopTabButton(String text) {
        Button button = new Button(this);
        button.setText(text);
        button.setAllCaps(false);
        button.setTextSize(13);
        button.setTypeface(boldTypeface());
        button.setMinHeight(dp(34));
        button.setMinimumHeight(dp(34));
        button.setPadding(dp(8), 0, dp(8), 0);
        return button;
    }

    /**
     * 外面（例如門前直樹Launcher 個 W widget）撳落嚟嗰陣，可以指定一開就落邊一版。
     * 值：{@value #TAB_MEAL}／{@value #TAB_SHIFT}／{@value #TAB_DUTY}／{@value #TAB_ONOFF}。
     */
    public static final String EXTRA_OPEN_TAB = "open_tab";
    public static final String TAB_MEAL = "meal";
    public static final String TAB_SHIFT = "shift";
    public static final String TAB_DUTY = "duty";
    public static final String TAB_ONOFF = "onoff";

    private void handleOpenTabIntent(Intent intent) {
        if (intent == null) {
            return;
        }
        String tab = intent.getStringExtra(EXTRA_OPEN_TAB);
        if (tab == null || tab.isEmpty()) {
            return;
        }
        if (TAB_MEAL.equals(tab)) {
            switchPage(PAGE_MEAL);
        } else if (TAB_SHIFT.equals(tab)) {
            switchPage(PAGE_SHIFT);
        } else if (TAB_DUTY.equals(tab)) {
            switchPage(PAGE_DUTY);
        } else if (TAB_ONOFF.equals(tab)) {
            switchPage(PAGE_ONOFF);
        }
        // 用完即棄。個 activity 係 singleTop，setIntent() 會留住呢個 intent，
        // 唔清走嘅話下次轉螢幕方向重建，又會硬跳返去嗰版，蓋走你自己揀咗嘅 tab。
        intent.removeExtra(EXTRA_OPEN_TAB);
    }

    private void switchPage(int page) {
        boolean wasMeal = currentPage == PAGE_MEAL;
        boolean wasDuty = currentPage == PAGE_DUTY;
        boolean wasOnOff = currentPage == PAGE_ONOFF;
        currentPage = page == PAGE_MEAL ? PAGE_MEAL
                : page == PAGE_DUTY ? PAGE_DUTY
                : page == PAGE_ONOFF ? PAGE_ONOFF
                : PAGE_SHIFT;
        if (currentPage == PAGE_MEAL) {
            mealPlanView.resetExpanded();  // 每次撳返「餐單」都用返當時嘅 default 餐
        }
        updatePageVisibility();
        render();
        if (currentPage == PAGE_MEAL && !wasMeal) {
            mealPlanView.refresh();
        }
        if (currentPage == PAGE_DUTY && !wasDuty && dutyReportView != null) {
            dutyReportView.refresh();
        }
        if (currentPage == PAGE_ONOFF && !wasOnOff && onOffDutyView != null) {
            onOffDutyView.refresh();
        }
    }

    private void updatePageVisibility() {
        if (mealSection == null || shiftSection == null || dutySection == null || onoffSection == null
                || mealTabButton == null || shiftTabButton == null || dutyTabButton == null
                || onoffTabButton == null) {
            return;
        }
        boolean isMeal = currentPage == PAGE_MEAL;
        boolean isDuty = currentPage == PAGE_DUTY;
        boolean isOnOff = currentPage == PAGE_ONOFF;
        boolean isShift = !isMeal && !isDuty && !isOnOff;
        mealSection.setVisibility(isMeal ? View.VISIBLE : View.GONE);
        shiftSection.setVisibility(isShift ? View.VISIBLE : View.GONE);
        dutySection.setVisibility(isDuty ? View.VISIBLE : View.GONE);
        onoffSection.setVisibility(isOnOff ? View.VISIBLE : View.GONE);

        mealTabButton.setBackgroundColor(isMeal ? 0xFF0B1026 : 0xFFDDEBF5);
        mealTabButton.setTextColor(isMeal ? 0xFFFFFFFF : 0xFF334155);
        shiftTabButton.setBackgroundColor(isShift ? 0xFF0B1026 : 0xFFDDEBF5);
        shiftTabButton.setTextColor(isShift ? 0xFFFFFFFF : 0xFF334155);
        dutyTabButton.setBackgroundColor(isDuty ? 0xFF0B1026 : 0xFFDDEBF5);
        dutyTabButton.setTextColor(isDuty ? 0xFFFFFFFF : 0xFF334155);
        onoffTabButton.setBackgroundColor(isOnOff ? 0xFF0B1026 : 0xFFDDEBF5);
        onoffTabButton.setTextColor(isOnOff ? 0xFFFFFFFF : 0xFF334155);
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

    private void applySafeAreaPadding(LinearLayout outer, ScrollView scrollView) {
        // 頂 inset 落固定 header（outer），底 inset 落 ScrollView 內容。
        outer.setOnApplyWindowInsetsListener((view, insets) -> {
            int top = Math.max(insets.getSystemWindowInsetTop(), systemBarHeight("status_bar_height"));
            int bottom = Math.max(insets.getSystemWindowInsetBottom(), systemBarHeight("navigation_bar_height"));
            view.setPadding(0, top + dp(6), 0, 0);
            scrollView.setPadding(0, 0, 0, bottom + dp(8));
            return insets;
        });
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.KITKAT_WATCH) {
            outer.requestApplyInsets();
        }
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    private android.graphics.Typeface regularTypeface() {
        if (regularTypeface == null) {
            try {
                regularTypeface = android.graphics.Typeface.createFromAsset(getAssets(), "fonts/msjh.ttc");
            } catch (RuntimeException e) {
                regularTypeface = android.graphics.Typeface.create("sans-serif", android.graphics.Typeface.NORMAL);
            }
        }
        return regularTypeface;
    }

    private android.graphics.Typeface boldTypeface() {
        if (boldTypeface == null) {
            try {
                boldTypeface = android.graphics.Typeface.createFromAsset(getAssets(), "fonts/msjhbd.ttc");
            } catch (RuntimeException e) {
                boldTypeface = android.graphics.Typeface.create("sans-serif-medium", android.graphics.Typeface.NORMAL);
            }
        }
        return boldTypeface;
    }

    private int systemBarHeight(String key) {
        int id = getResources().getIdentifier(key, "dimen", "android");
        return id > 0 ? getResources().getDimensionPixelSize(id) : 0;
    }

    private void loadFromStore() {
        shiftTableView.loadFromStore();
        mealPlanView.loadFromStore();
    }

    private void render() {
        updatePageVisibility();
        mealPlanView.render();
        shiftTableView.render();
    }

    private void requestNotificationPermissionIfNeeded() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU
                && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 9001);
        }
    }

    /**
     * 唔喺電池優化白名單，Samsung 會凍結後台 process——本機 server 就收唔到電腦嘅 push
     * （例如打風改咗行位表要即刻重新匯入）。開 app 嗰陣問一次，已經豁免就唔會再煩。
     */
    private void maybeRequestBatteryExemption() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.M) {
            return;
        }
        android.os.PowerManager pm = (android.os.PowerManager) getSystemService(POWER_SERVICE);
        String pkg = getPackageName();
        if (pm == null || pm.isIgnoringBatteryOptimizations(pkg)) {
            return;
        }
        try {
            Intent intent = new Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS);
            intent.setData(Uri.parse("package:" + pkg));
            startActivity(intent);
        } catch (Exception e) {
            Log.w(TAG, "Battery optimization request failed", e);
        }
    }

    /** adb 測試入口：`am start -a com.example.oneshotalarm.ACTION_TEST_DAILY_IMPORT`，行一次每日匯入。 */
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
        shiftTableView.importFromPc("測試自動 import 中...", "測試自動 import 成功：", "測試自動 import 失敗");
    }

}
