package com.example.oneshotalarm.watch;

import android.app.Activity;
import android.content.Context;
import android.content.SharedPreferences;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.RectF;
import android.graphics.Typeface;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.SpannableString;
import android.text.Spanned;
import android.text.TextUtils;
import android.text.style.ForegroundColorSpan;
import android.view.Gravity;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

public class ScheduleGridTileActivity extends Activity {
    private final Handler clockHandler = new Handler(Looper.getMainLooper());
    private HeaderView headerView;
    private final Runnable clockTick = new Runnable() {
        @Override
        public void run() {
            updateClock();
            long delay = 60_000L - (System.currentTimeMillis() % 60_000L);
            clockHandler.postDelayed(this, delay);
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        SharedPreferences prefs = getSharedPreferences(AlarmScheduleState.PREFS, MODE_PRIVATE);
        JSONArray rows = parseRows(prefs.getString(AlarmScheduleState.KEY_SCHEDULE_ITEMS_JSON, "[]"));
        String planDate = prefs.getString(AlarmScheduleState.KEY_PLAN_DATE, "");
        long now = System.currentTimeMillis();

        LinearLayout screen = new LinearLayout(this);
        screen.setOrientation(LinearLayout.VERTICAL);
        screen.setBackgroundColor(Color.rgb(15, 23, 42));

        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        scroll.setBackgroundColor(Color.rgb(15, 23, 42));

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(10), 0, dp(10), dp(24));
        scroll.addView(root, new ScrollView.LayoutParams(
                ScrollView.LayoutParams.MATCH_PARENT,
                ScrollView.LayoutParams.WRAP_CONTENT
        ));

        String subtitle = subtitle(
                planDate,
                prefs.getString(AlarmScheduleState.KEY_ROSTER_CODE, "")
        );
        headerView = new HeaderView(this, subtitle);
        screen.addView(headerView, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(44)
        ));
        screen.addView(scroll, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                0,
                1f
        ));

        if (rows.length() == 0) {
            TextView empty = text("等待電話行位表", 15, Color.rgb(229, 231, 235), Typeface.NORMAL);
            empty.setGravity(Gravity.CENTER_HORIZONTAL);
            root.addView(empty);
        } else {
            for (int i = 0; i < rows.length(); i++) {
                JSONObject row = rows.optJSONObject(i);
                if (row == null) {
                    continue;
                }
                addScheduleRow(
                        root,
                        row.optString("time", "--:--"),
                        row.optString("content", "沒有資料"),
                        isPastDisplayTime(row.optString("time", ""), row.optLong("at", 0L), now, planDate)
                );
            }
        }
        setContentView(screen);
        updateClock();
    }

    @Override
    protected void onResume() {
        super.onResume();
        clockTick.run();
    }

    @Override
    protected void onPause() {
        clockHandler.removeCallbacks(clockTick);
        super.onPause();
    }

    private void updateClock() {
        if (headerView != null) {
            headerView.setClock(new SimpleDateFormat("HH:mm", Locale.US).format(new Date()));
        }
    }

    private final class HeaderView extends View {
        private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG | Paint.SUBPIXEL_TEXT_FLAG);
        private final Path titlePath = new Path();
        private final String subtitle;
        private String clock = "";

        HeaderView(Context context, String subtitle) {
            super(context);
            this.subtitle = safe(subtitle, "");
            paint.setTypeface(Typeface.DEFAULT);
        }

        void setClock(String clock) {
            this.clock = safe(clock, "");
            invalidate();
        }

        @Override
        protected void onDraw(Canvas canvas) {
            super.onDraw(canvas);
            int width = getWidth();
            paint.setStyle(Paint.Style.FILL);

            titlePath.reset();
            titlePath.addArc(new RectF(dp(40), dp(16), width - dp(40), dp(154)), 222f, 96f);
            paint.setColor(Color.WHITE);
            paint.setTextSize(sp(16));
            paint.setTypeface(Typeface.DEFAULT_BOLD);
            paint.setTextAlign(Paint.Align.CENTER);
            canvas.drawTextOnPath("今日行位", titlePath, 0f, 0f, paint);

            paint.setTypeface(Typeface.DEFAULT);
            paint.setTextSize(sp(10));
            paint.setColor(Color.rgb(203, 213, 225));
            paint.setTextAlign(Paint.Align.LEFT);
            float baseline = dp(38);
            if (subtitle.isEmpty()) {
                float clockWidth = paint.measureText(clock);
                canvas.drawText(clock, (width - clockWidth) / 2f, baseline, paint);
            } else {
                float gap = dp(6);
                float subtitleWidth = paint.measureText(subtitle);
                float clockWidth = paint.measureText(clock);
                float start = (width - subtitleWidth - gap - clockWidth) / 2f;
                canvas.drawText(subtitle, start, baseline, paint);
                canvas.drawText(clock, start + subtitleWidth + gap, baseline, paint);
            }
        }
    }

    private void addScheduleRow(LinearLayout root, String time, String content, boolean past) {
        int timeColor = past ? Color.rgb(71, 85, 105) : Color.WHITE;
        int contentColor = past ? Color.rgb(100, 116, 139) : Color.rgb(229, 231, 235);
        String timeText = safe(time, "--:--");
        String contentText = safe(content, "沒有資料");
        String line = timeText + "  " + contentText;
        SpannableString styled = new SpannableString(line);
        styled.setSpan(new ForegroundColorSpan(timeColor), 0, timeText.length(), Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
        styled.setSpan(new ForegroundColorSpan(contentColor), timeText.length(), line.length(), Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);

        TextView row = text("", 14, contentColor, Typeface.NORMAL);
        row.setText(styled);
        row.setSingleLine(true);
        row.setEllipsize(TextUtils.TruncateAt.END);
        row.setGravity(Gravity.CENTER_VERTICAL);
        row.setLineSpacing(0f, 1f);
        row.setPadding(dp(40), 0, 0, 0);
        root.addView(row, fixedRowParams());
    }

    private LinearLayout.LayoutParams fullWidthParams() {
        return new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
        );
    }

    private LinearLayout.LayoutParams fixedRowParams() {
        return new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(20)
        );
    }

    private TextView text(String value, int sp, int color, int style) {
        TextView view = new TextView(this);
        view.setText(value == null ? "" : value);
        view.setTextSize(sp);
        view.setTextColor(color);
        view.setTypeface(Typeface.DEFAULT, style);
        view.setIncludeFontPadding(false);
        return view;
    }

    private void addSpacer(LinearLayout root, int dp) {
        TextView spacer = new TextView(this);
        root.addView(spacer, new LinearLayout.LayoutParams(1, dp(dp)));
    }

    private JSONArray parseRows(String raw) {
        try {
            return new JSONArray(raw == null ? "[]" : raw);
        } catch (Exception ignored) {
            return new JSONArray();
        }
    }

    private boolean isPastDisplayTime(String time, long atMillis, long nowMillis, String planDate) {
        int dateComparison = comparePlanDateToToday(planDate, nowMillis);
        if (dateComparison < 0) {
            return true;
        }
        if (dateComparison > 0) {
            return false;
        }
        String clean = safe(time, "");
        if (clean.matches("\\d{1,2}:\\d{2}")) {
            String[] parts = clean.split(":");
            int rowMinutes = Integer.parseInt(parts[0]) * 60 + Integer.parseInt(parts[1]);
            Date now = new Date(nowMillis);
            SimpleDateFormat hourFormat = new SimpleDateFormat("H", Locale.US);
            SimpleDateFormat minuteFormat = new SimpleDateFormat("m", Locale.US);
            int nowMinutes = Integer.parseInt(hourFormat.format(now)) * 60
                    + Integer.parseInt(minuteFormat.format(now));
            return rowMinutes <= nowMinutes;
        }
        return atMillis > 0L && atMillis <= nowMillis;
    }

    private int comparePlanDateToToday(String planDate, long nowMillis) {
        String value = safe(planDate, "");
        if (!value.matches("\\d{4}-\\d{2}-\\d{2}")) {
            return 0;
        }
        String today = new SimpleDateFormat("yyyy-MM-dd", Locale.US).format(new Date(nowMillis));
        return value.compareTo(today);
    }

    private String subtitle(String planDate, String rosterCode) {
        String date = safe(planDate, "");
        String roster = safe(rosterCode, "");
        if (!date.isEmpty() && !roster.isEmpty()) {
            return date + "  " + roster;
        }
        return date.isEmpty() ? roster : date;
    }

    private String safe(String value, String fallback) {
        String trimmed = value == null ? "" : value.trim();
        return trimmed.isEmpty() ? fallback : trimmed;
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    private float sp(float value) {
        return value * getResources().getDisplayMetrics().scaledDensity;
    }
}
