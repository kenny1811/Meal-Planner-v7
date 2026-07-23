package com.example.oneshotalarm.watch;

import android.app.Activity;
import android.content.pm.PackageInfo;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.text.SimpleDateFormat;
import java.util.Locale;

/**
 * 錶面左邊 complication 撳落去開嘅 About 畫面（規格表式）：
 * 錶面/鬧鐘 versionName + last update（PackageInfo.lastUpdateTime，runtime 查）。
 * 撳任何位置即閂。
 */
public class AboutActivity extends Activity {
    private static final int COLOR_TITLE = 0xFFFFFFFF;
    private static final int COLOR_LABEL = 0xFF9A9A9A;
    private static final int COLOR_VERSION = 0xFF8FC1EC;
    private static final int COLOR_SUB_LABEL = 0xFF5F5F5F;
    private static final int COLOR_SUB_VALUE = 0xFF7A7A7A;
    private static final int COLOR_DIVIDER = 0xFF3A3A3A;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setGravity(Gravity.CENTER);
        root.setBackgroundColor(0xFF000000);
        root.setClickable(true);
        root.setOnClickListener(v -> finish());

        TextView title = new TextView(this);
        title.setText("門前直樹");
        title.setTextColor(COLOR_TITLE);
        title.setTextSize(17);
        title.setGravity(Gravity.CENTER);
        root.addView(title);

        View divider = new View(this);
        divider.setBackgroundColor(COLOR_DIVIDER);
        LinearLayout.LayoutParams dividerParams = new LinearLayout.LayoutParams(dp(120), dp(1));
        dividerParams.topMargin = dp(6);
        dividerParams.bottomMargin = dp(8);
        dividerParams.gravity = Gravity.CENTER_HORIZONTAL;
        root.addView(divider, dividerParams);

        // 圓芒：下面嗰行離圓心越遠，可用弦長越窄；144dp 喺底行位置仍然入晒圓內。
        LinearLayout content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        root.addView(content, new LinearLayout.LayoutParams(dp(144), LinearLayout.LayoutParams.WRAP_CONTENT));

        addAppRows(content, "錶面", "com.kenny.watchface", false);
        addAppRows(content, "鬧鐘", getPackageName(), true);

        setContentView(root);
    }

    private void addAppRows(LinearLayout content, String label, String packageName, boolean last) {
        PackageInfo info = packageInfo(packageName);
        String version = info != null && info.versionName != null ? "v" + info.versionName : "未安裝";
        String updated = info != null
                ? new SimpleDateFormat("dd/MM/yyyy HH:mm", Locale.US).format(info.lastUpdateTime)
                : "--";
        content.addView(row(label, COLOR_LABEL, version, COLOR_VERSION, 14, 0));
        content.addView(row("更新", COLOR_SUB_LABEL, updated, COLOR_SUB_VALUE, 11, last ? 0 : 6));
    }

    private LinearLayout row(String label, int labelColor, String value, int valueColor,
            int textSizeSp, int bottomMarginDp) {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);

        TextView labelView = new TextView(this);
        labelView.setText(label);
        labelView.setTextColor(labelColor);
        labelView.setTextSize(textSizeSp);
        row.addView(labelView, new LinearLayout.LayoutParams(
                0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f));

        TextView valueView = new TextView(this);
        valueView.setText(value);
        valueView.setTextColor(valueColor);
        valueView.setTextSize(textSizeSp);
        valueView.setGravity(Gravity.END);
        row.addView(valueView);

        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        params.bottomMargin = dp(bottomMarginDp);
        row.setLayoutParams(params);
        return row;
    }

    private PackageInfo packageInfo(String packageName) {
        try {
            return getPackageManager().getPackageInfo(packageName, 0);
        } catch (Exception e) {
            return null;
        }
    }

    private int dp(int value) {
        return Math.round(getResources().getDisplayMetrics().density * value);
    }
}
