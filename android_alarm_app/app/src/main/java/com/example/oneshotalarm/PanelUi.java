package com.example.oneshotalarm;

import android.app.Activity;
import android.graphics.Typeface;
import android.view.Gravity;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

/**
 * DutyReportView / OnOffDutyView 共用嘅程式化 UI 工廠。
 * 以前兩個 view 各抄一份 byte-identical 嘅 textView/row/actionButton/…——
 * styling 常數（字級、色、padding、按鈕高度）而家得呢一份，改一次兩邊齊變。
 */
final class PanelUi {
    private final Activity activity;
    private final Typeface regularTypeface;
    private final Typeface boldTypeface;

    PanelUi(Activity activity, Typeface regular, Typeface bold) {
        this.activity = activity;
        this.regularTypeface = regular != null ? regular : Typeface.DEFAULT;
        this.boldTypeface = bold != null ? bold : Typeface.DEFAULT_BOLD;
    }

    Typeface regular() {
        return regularTypeface;
    }

    Typeface bold() {
        return boldTypeface;
    }

    TextView textView(String text, int sizeSp, int color, boolean bold) {
        TextView view = new TextView(activity);
        view.setText(text);
        view.setTextSize(sizeSp);
        view.setTextColor(color);
        view.setTypeface(bold ? boldTypeface : regularTypeface);
        view.setPadding(dp(8), dp(2), dp(8), dp(2));
        return view;
    }

    LinearLayout row() {
        LinearLayout layout = new LinearLayout(activity);
        layout.setOrientation(LinearLayout.HORIZONTAL);
        layout.setGravity(Gravity.CENTER_VERTICAL);
        return layout;
    }

    Button actionButton(String label) {
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

    LinearLayout.LayoutParams buttonParams() {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT, dp(30));
        params.setMargins(dp(3), 0, 0, 0);
        return params;
    }

    LinearLayout.LayoutParams weighted(float weight) {
        return new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, weight);
    }

    LinearLayout.LayoutParams fullWidth() {
        return new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
    }

    int dp(int value) {
        return Math.round(activity.getResources().getDisplayMetrics().density * value);
    }

    android.graphics.drawable.GradientDrawable roundedBg(
            int fillColor, int radiusDp, int strokeColor, int strokeDp) {
        android.graphics.drawable.GradientDrawable drawable =
                new android.graphics.drawable.GradientDrawable();
        drawable.setColor(fillColor);
        drawable.setCornerRadius(dp(radiusDp));
        if (strokeDp > 0) {
            drawable.setStroke(dp(strokeDp), strokeColor);
        }
        return drawable;
    }

    /** 圓角 pill（狀態 chip）：11sp 粗體，實色底。 */
    TextView chip(String text, int textColor, int bgColor) {
        TextView view = new TextView(activity);
        view.setText(text);
        view.setTextSize(11);
        view.setTextColor(textColor);
        view.setTypeface(boldTypeface);
        view.setBackground(roundedBg(bgColor, 99, bgColor, 0));
        view.setPadding(dp(8), dp(3), dp(8), dp(3));
        return view;
    }

    /** 圓角卡片（直排）。strokeDp=0 即淨色冇邊。 */
    LinearLayout card(int fillColor, int strokeColor, int strokeDp) {
        LinearLayout layout = new LinearLayout(activity);
        layout.setOrientation(LinearLayout.VERTICAL);
        layout.setBackground(roundedBg(fillColor, 10, strokeColor, strokeDp));
        layout.setPadding(dp(12), dp(10), dp(12), dp(10));
        return layout;
    }

    LinearLayout.LayoutParams cardParams() {
        LinearLayout.LayoutParams params = fullWidth();
        params.setMargins(dp(8), dp(6), dp(8), 0);
        return params;
    }

    /** 橙色警告條（轉code影響範圍嗰啲提示）。 */
    TextView noteStrip(String text) {
        TextView view = new TextView(activity);
        view.setText(text);
        view.setTextSize(10);
        view.setTextColor(0xFF9A5B00);
        view.setTypeface(boldTypeface);
        view.setBackground(roundedBg(0xFFFAEEDA, 8, 0, 0));
        view.setPadding(dp(10), dp(6), dp(10), dp(6));
        return view;
    }

    /** 白底圓角框線掣（卡入面嘅主要動作）。 */
    Button outlineButton(String label, int textColor, int strokeColor) {
        Button button = actionButton(label);
        button.setTextSize(12);
        button.setTextColor(textColor);
        button.setTypeface(boldTypeface);
        button.setBackground(roundedBg(0xFFFFFFFF, 8, strokeColor, 1));
        return button;
    }

    LinearLayout.LayoutParams chipParams() {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        params.setMargins(dp(4), 0, 0, 0);
        return params;
    }
}
