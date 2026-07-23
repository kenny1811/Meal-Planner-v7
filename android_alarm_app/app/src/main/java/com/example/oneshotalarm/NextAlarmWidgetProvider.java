package com.example.oneshotalarm;

import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.util.TypedValue;
import android.view.View;
import android.widget.RemoteViews;

import org.json.JSONArray;
import org.json.JSONObject;

import java.text.SimpleDateFormat;
import java.util.Locale;

public class NextAlarmWidgetProvider extends AppWidgetProvider {
    @Override
    public void onUpdate(Context context, AppWidgetManager appWidgetManager, int[] appWidgetIds) {
        updateWidgets(context, appWidgetManager, appWidgetIds);
    }

    @Override
    public void onEnabled(Context context) {
        updateAll(context);
    }

    static void updateAll(Context context) {
        AppWidgetManager manager = AppWidgetManager.getInstance(context);
        ComponentName component = new ComponentName(context, NextAlarmWidgetProvider.class);
        int[] ids = manager.getAppWidgetIds(component);
        updateWidgets(context, manager, ids);
    }

    private static void updateWidgets(Context context, AppWidgetManager manager, int[] ids) {
        if (ids == null || ids.length == 0) {
            return;
        }
        WidgetAlarm next = findNextAlarm(context);
        for (int id : ids) {
            RemoteViews views = new RemoteViews(context.getPackageName(), R.layout.next_alarm_widget);
            if (next == null) {
                views.setTextViewText(R.id.widget_title, "NEXT SHIFT");
                views.setTextViewText(R.id.widget_date, "--/--");
                views.setTextViewText(R.id.widget_time, "--:--");
                views.setTextViewText(R.id.widget_label_line1, "未有");
                views.setTextViewText(R.id.widget_label_line2, "下一個鬧鐘");
                views.setTextViewTextSize(R.id.widget_label_line1, TypedValue.COMPLEX_UNIT_SP, 8f);
                views.setTextViewTextSize(R.id.widget_label_line2, TypedValue.COMPLEX_UNIT_SP, 8f);
                views.setViewVisibility(R.id.widget_label_line2, View.VISIBLE);
            } else {
                views.setTextViewText(R.id.widget_title, "NEXT SHIFT");
                views.setTextViewText(R.id.widget_date, next.date);
                views.setTextViewText(R.id.widget_time, next.time);
                String[] lines = smartLabelLines(next.label);
                views.setTextViewText(R.id.widget_label_line1, lines[0]);
                views.setTextViewText(R.id.widget_label_line2, lines[1]);
                if (lines[1].isEmpty()) {
                    views.setTextViewTextSize(R.id.widget_label_line1, TypedValue.COMPLEX_UNIT_SP, 12f);
                    views.setViewVisibility(R.id.widget_label_line2, View.GONE);
                } else {
                    views.setTextViewTextSize(R.id.widget_label_line1, TypedValue.COMPLEX_UNIT_SP, 8f);
                    views.setTextViewTextSize(R.id.widget_label_line2, TypedValue.COMPLEX_UNIT_SP, 8f);
                    views.setViewVisibility(R.id.widget_label_line2, View.VISIBLE);
                }
            }
            views.setOnClickPendingIntent(R.id.widget_root, openAppPendingIntent(context));
            manager.updateAppWidget(id, views);
        }
    }

    private static PendingIntent openAppPendingIntent(Context context) {
        Intent intent = new Intent(context, MainActivity.class);
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        int flags = PendingIntent.FLAG_UPDATE_CURRENT;
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.M) {
            flags |= PendingIntent.FLAG_IMMUTABLE;
        }
        return PendingIntent.getActivity(context, 9201, intent, flags);
    }

    private static WidgetAlarm findNextAlarm(Context context) {
        AlarmStore.PrevNext pair = AlarmStore.findPrevNext(context, System.currentTimeMillis());
        JSONObject best = pair.next;
        long bestAt = pair.nextAt;
        if (best == null) {
            return null;
        }
        String date = new SimpleDateFormat("dd/MM/yyyy EEE", Locale.getDefault()).format(bestAt);
        String time = new SimpleDateFormat("HH:mm", Locale.getDefault()).format(bestAt);
        String label = best.optString("label", "鬧鐘").trim();
        if (label.isEmpty()) {
            label = "鬧鐘";
        }
        return new WidgetAlarm(date, time, label);
    }

    private static String[] smartLabelLines(String label) {
        String text = label == null ? "" : label.trim();
        if (text.isEmpty()) {
            return new String[]{"鬧鐘", ""};
        }
        if (text.contains("\n")) {
            String[] parts = text.split("\\n", 2);
            return new String[]{parts[0].trim(), parts.length > 1 ? parts[1].trim() : ""};
        }
        if (displayLength(text) <= 8) {
            return new String[]{text, ""};
        }
        int split = bestSplitIndex(text);
        if (split <= 0 || split >= text.length()) {
            return new String[]{text, ""};
        }
        String first = text.substring(0, split).trim();
        String second = text.substring(split).trim();
        return new String[]{first, second};
    }

    private static int displayLength(String text) {
        int length = 0;
        int i = 0;
        while (i < text.length()) {
            int cp = text.codePointAt(i);
            if (!Character.isWhitespace(cp)) {
                length++;
            }
            i += Character.charCount(cp);
        }
        return length;
    }

    private static int bestSplitIndex(String text) {
        int target = Math.max(1, text.length() / 2);
        char[] preferred = new char[]{'，', ',', '、', '。', ' '};
        int best = -1;
        int bestDistance = Integer.MAX_VALUE;
        for (char marker : preferred) {
            int from = -1;
            while (true) {
                int found = text.indexOf(marker, from + 1);
                if (found < 0) {
                    break;
                }
                int split = found + 1;
                int distance = Math.abs(split - target);
                if (distance < bestDistance) {
                    best = split;
                    bestDistance = distance;
                }
                from = found;
            }
        }
        if (best > 0) {
            return best;
        }
        return snapToCodePointBoundary(text, target);
    }

    /** 中間切時避開 surrogate pair（emoji／擴展漢字），否則兩截都變 tofu。 */
    private static int snapToCodePointBoundary(String text, int index) {
        if (index > 0
                && index < text.length()
                && Character.isHighSurrogate(text.charAt(index - 1))
                && Character.isLowSurrogate(text.charAt(index))) {
            return index + 1;
        }
        return index;
    }

    private static final class WidgetAlarm {
        final String date;
        final String time;
        final String label;

        WidgetAlarm(String date, String time, String label) {
            this.date = date;
            this.time = time;
            this.label = label;
        }
    }
}
