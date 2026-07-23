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
}
