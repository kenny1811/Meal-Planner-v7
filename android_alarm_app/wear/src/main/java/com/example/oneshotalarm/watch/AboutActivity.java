package com.example.oneshotalarm.watch;

import android.app.Activity;
import android.os.Bundle;
import android.view.Gravity;
import android.widget.LinearLayout;
import android.widget.TextView;

/**
 * 錶面左邊 complication 撳落去開嘅 About 畫面：
 * 顯示鬧鐘 app 同錶面 app 嘅 versionName（runtime 查，永遠係現裝版本）。
 * 撳任何位置即閂。
 */
public class AboutActivity extends Activity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setGravity(Gravity.CENTER);
        root.setPadding(dp(16), dp(12), dp(16), dp(12));
        root.setBackgroundColor(0xFF000000);
        root.setClickable(true);
        root.setOnClickListener(v -> finish());

        TextView title = new TextView(this);
        title.setText("門前直樹");
        title.setTextColor(0xFFFFFFFF);
        title.setTextSize(20);
        title.setGravity(Gravity.CENTER);
        root.addView(title);

        TextView alarm = new TextView(this);
        alarm.setText("鬧鐘 v" + versionOf(getPackageName()));
        alarm.setTextColor(0xFFB0B0B0);
        alarm.setTextSize(16);
        alarm.setGravity(Gravity.CENTER);
        alarm.setPadding(0, dp(10), 0, 0);
        root.addView(alarm);

        TextView face = new TextView(this);
        face.setText("錶面 v" + versionOf("com.kenny.watchface"));
        face.setTextColor(0xFFB0B0B0);
        face.setTextSize(16);
        face.setGravity(Gravity.CENTER);
        face.setPadding(0, dp(4), 0, 0);
        root.addView(face);

        setContentView(root);
    }

    private String versionOf(String packageName) {
        try {
            String version = getPackageManager().getPackageInfo(packageName, 0).versionName;
            return version != null ? version : "?";
        } catch (Exception e) {
            return "未安裝";
        }
    }

    private int dp(int value) {
        return Math.round(getResources().getDisplayMetrics().density * value);
    }
}
