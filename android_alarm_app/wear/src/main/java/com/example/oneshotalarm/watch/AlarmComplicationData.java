package com.example.oneshotalarm.watch;

import android.content.Context;
import android.content.SharedPreferences;

import androidx.wear.watchface.complications.data.ComplicationData;
import androidx.wear.watchface.complications.data.ComplicationText;
import androidx.wear.watchface.complications.data.PlainComplicationText;
import androidx.wear.watchface.complications.data.ShortTextComplicationData;

final class AlarmComplicationData {
    private AlarmComplicationData() {
    }

    static ComplicationData build(Context context, boolean next) {
        SharedPreferences prefs = context.getSharedPreferences(PrevNextAlarmTileService.PREFS, Context.MODE_PRIVATE);
        String time = prefs.getString(next ? PrevNextAlarmTileService.KEY_NEXT_TIME : PrevNextAlarmTileService.KEY_PREV_TIME, "--:--");
        String label = prefs.getString(next ? PrevNextAlarmTileService.KEY_NEXT_LABEL : PrevNextAlarmTileService.KEY_PREV_LABEL, "等待電話資料");
        String title = safe(time, "--:--");
        String text = labelLine(safe(label, "沒有資料"), 0);
        return new ShortTextComplicationData.Builder(text(text), text(title))
                .setTitle(text(title))
                .build();
    }

    static ComplicationData buildLabelLine(Context context, boolean next, int lineIndex) {
        SharedPreferences prefs = context.getSharedPreferences(PrevNextAlarmTileService.PREFS, Context.MODE_PRIVATE);
        String label = prefs.getString(next ? PrevNextAlarmTileService.KEY_NEXT_LABEL : PrevNextAlarmTileService.KEY_PREV_LABEL, "等待電話資料");
        String text = labelLine(safe(label, "沒有資料"), lineIndex);
        return new ShortTextComplicationData.Builder(text(text), text(text))
                .build();
    }

    static ComplicationData preview(boolean next) {
        String title = next ? "08:30" : "22:45";
        String text = next ? "報開工平安更測試字位" : "測試中文內容十個字位";
        text = labelLine(text, 0);
        return new ShortTextComplicationData.Builder(text(text), text(title))
                .setTitle(text(title))
                .build();
    }

    static ComplicationData previewLabelLine(boolean next, int lineIndex) {
        String text = next ? "報開工平安更測試字位" : "測試中文內容十個字位";
        text = labelLine(text, lineIndex);
        return new ShortTextComplicationData.Builder(text(text), text(text))
                .build();
    }

    private static ComplicationText text(String value) {
        return new PlainComplicationText.Builder(value).build();
    }

    private static String safe(String value, String fallback) {
        String trimmed = value == null ? "" : value.trim();
        return trimmed.isEmpty() ? fallback : trimmed;
    }

    private static String labelLine(String value, int lineIndex) {
        String clean = safe(value, "沒有資料").replace('\n', ' ');
        int totalUnits = displayUnits(clean);
        if (lineIndex <= 0 && totalUnits <= 10) {
            return clean;
        }
        return displayUnitSlice(clean, Math.max(0, lineIndex) * 10, 10);
    }

    private static int displayUnits(String value) {
        int units = 0;
        for (int offset = 0; offset < value.length(); ) {
            int codePoint = value.codePointAt(offset);
            units += displayUnits(codePoint);
            offset += Character.charCount(codePoint);
        }
        return units;
    }

    private static int displayUnits(int codePoint) {
        return codePoint <= 0x7F ? 1 : 2;
    }

    private static String displayUnitSlice(String value, int startUnit, int maxUnits) {
        StringBuilder out = new StringBuilder();
        int currentUnit = 0;
        int endUnit = startUnit + maxUnits;
        for (int offset = 0; offset < value.length(); ) {
            int codePoint = value.codePointAt(offset);
            int codePointUnits = displayUnits(codePoint);
            int nextUnit = currentUnit + codePointUnits;
            if (nextUnit > startUnit && currentUnit < endUnit && nextUnit <= endUnit) {
                out.appendCodePoint(codePoint);
            }
            currentUnit = nextUnit;
            offset += Character.charCount(codePoint);
        }
        return out.toString();
    }

    private static String firstCodePoints(String value, int limit) {
        return codePointSlice(value, 0, Math.min(value.codePointCount(0, value.length()), limit));
    }

    private static String codePointSlice(String value, int startCodePoint, int endCodePoint) {
        if (startCodePoint >= endCodePoint) {
            return "";
        }
        int start = value.offsetByCodePoints(0, startCodePoint);
        int end = value.offsetByCodePoints(0, endCodePoint);
        return value.substring(start, end);
    }

    private static String shorten(String value, int limit) {
        if (value.length() <= limit) {
            return value;
        }
        return value.substring(0, Math.max(0, limit - 1)) + "...";
    }
}
