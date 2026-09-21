package com.example.oneshotalarm;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Context;
import android.graphics.Typeface;
import android.text.Editable;
import android.text.InputFilter;
import android.text.InputType;
import android.text.TextWatcher;
import android.view.Gravity;
import android.view.inputmethod.InputMethodManager;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONObject;

/**
 * MealPlanView / ShiftTableView / DutyReportView / OnOffDutyView 共用嘅程式化 UI 工廠。
 * 以前每個 view 各抄一份 byte-identical 嘅 textView/row/actionButton/…——
 * styling 常數（字級、色、padding、按鈕高度）而家得呢一份，改一次全部齊變。
 * 大窗時間輸入 dialog 同「thread→ApiClient→runOnUiThread」都收埋喺度。
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

    /** 餐單頁／行位表頁底行嗰款細掣（10sp 粗體，28dp 高）。 */
    Button bottomButton(String text) {
        Button button = new Button(activity);
        button.setText(text);
        button.setTextSize(10);
        button.setTypeface(boldTypeface);
        button.setGravity(Gravity.CENTER);
        button.setAllCaps(false);
        button.setMinHeight(dp(28));
        button.setMinimumHeight(dp(28));
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

    // ---------------------------------------------------------------- 時間輸入 dialog

    interface TimeCallback {
        void onTime(int hour, int minute);
    }

    /**
     * 大窗時間輸入（行位表改時間、報更改時間共用）：兩個大數字格，打滿自動跳；
     * 時 0–29（30 小時制，24–29 即翌日凌晨）。neutralLabel 傳 null 就冇中間掣。
     */
    void showTimeDialog(
            String title,
            int hour,
            int minute,
            String neutralLabel,
            Runnable onNeutral,
            TimeCallback onOk
    ) {
        LinearLayout box = new LinearLayout(activity);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setPadding(dp(18), dp(4), dp(18), 0);

        LinearLayout inputs = new LinearLayout(activity);
        inputs.setOrientation(LinearLayout.HORIZONTAL);
        inputs.setGravity(Gravity.CENTER);

        EditText hourInput = timePartInput(String.format(java.util.Locale.US, "%02d", Math.max(0, hour)));
        EditText minuteInput = timePartInput(String.format(java.util.Locale.US, "%02d", Math.max(0, minute)));
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

        AlertDialog.Builder builder = new AlertDialog.Builder(activity)
                .setTitle(title)
                .setView(box)
                .setNegativeButton("Cancel", null)
                .setPositiveButton("OK", null);
        if (neutralLabel != null && !neutralLabel.isEmpty()) {
            builder.setNeutralButton(neutralLabel, (d, w) -> {
                if (onNeutral != null) {
                    onNeutral.run();
                }
            });
        }
        AlertDialog dialog = builder.create();
        dialog.setOnShowListener(d -> {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v -> {
                int pickedHour = parseTwoDigit(hourInput, -1);
                int pickedMinute = parseTwoDigit(minuteInput, -1);
                if (pickedHour < 0 || pickedHour > 29 || pickedMinute < 0 || pickedMinute > 59) {
                    Toast.makeText(activity, "00:00 - 29:59 (24-29 = next-day early morning)", Toast.LENGTH_SHORT).show();
                    return;
                }
                onOk.onTime(pickedHour, pickedMinute);
                dialog.dismiss();
            });
            hourInput.requestFocus();
            hourInput.selectAll();
            hourInput.postDelayed(() -> {
                InputMethodManager imm = (InputMethodManager) activity.getSystemService(Context.INPUT_METHOD_SERVICE);
                if (imm != null) {
                    imm.showSoftInput(hourInput, InputMethodManager.SHOW_IMPLICIT);
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
        input.setFilters(new InputFilter[]{new InputFilter.LengthFilter(2)});
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
        InputMethodManager imm = (InputMethodManager) activity.getSystemService(Context.INPUT_METHOD_SERVICE);
        if (imm != null) {
            imm.hideSoftInputFromWindow(input.getWindowToken(), 0);
        }
    }

    // ---------------------------------------------------------------- 網絡

    interface JsonCallback {
        void onResult(JSONObject json);
    }

    interface ErrorCallback {
        void onError(Exception error);
    }

    /**
     * 「開 thread → ApiClient → parse JSON → runOnUiThread」一份搞掂。
     * DutyReportView／OnOffDutyView 以前每個 post 都抄一次呢段。
     * 兩個 callback 都喺 UI thread 行；payload null＝GET／無 body。
     */
    void request(
            String method,
            String path,
            JSONObject payload,
            int readTimeoutMs,
            String threadName,
            JsonCallback onSuccess,
            ErrorCallback onError
    ) {
        String body = payload == null ? null : payload.toString();
        new Thread(() -> {
            try {
                String response = ApiClient.request(activity, method, path, body, readTimeoutMs);
                JSONObject parsed = new JSONObject(response);
                activity.runOnUiThread(() -> onSuccess.onResult(parsed));
            } catch (Exception e) {
                activity.runOnUiThread(() -> onError.onError(e));
            }
        }, threadName).start();
    }
}
