package com.kenny.watchface.phone;

import android.app.Activity;
import android.graphics.Color;
import android.os.Bundle;
import android.view.Gravity;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

public class MainActivity extends Activity {
    private TextView status;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        SunTimesSync.scheduleDailyAt0530(this);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setGravity(Gravity.CENTER_HORIZONTAL);
        root.setPadding(48, 72, 48, 48);
        root.setBackgroundColor(Color.rgb(3, 4, 5));
        setContentView(root);

        TextView title = new TextView(this);
        title.setText("Kenny Battery Sync");
        title.setTextColor(Color.rgb(248, 250, 252));
        title.setTextSize(26);
        title.setGravity(Gravity.CENTER);
        root.addView(title, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT));

        status = new TextView(this);
        status.setTextColor(Color.rgb(147, 164, 181));
        status.setTextSize(16);
        status.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams statusParams = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT);
        statusParams.setMargins(0, 28, 0, 42);
        root.addView(status, statusParams);

        Button sync = new Button(this);
        sync.setText("Sync now");
        sync.setOnClickListener(v -> {
            BatterySync.syncNow(this);
            SunTimesSync.syncNowAsync(this);
            updateStatus();
        });
        root.addView(sync, buttonParams());

        updateStatus();
    }

    private LinearLayout.LayoutParams buttonParams() {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT);
        params.setMargins(0, 0, 0, 18);
        return params;
    }

    private void updateStatus() {
        int percent = BatterySync.readBatteryPercent(this);
        String percentText = percent >= 0 ? percent + "%" : "--%";
        status.setText("Phone battery " + percentText
                + "\nSunrise/sunset syncs from HKO daily at 05:30.");
    }
}
