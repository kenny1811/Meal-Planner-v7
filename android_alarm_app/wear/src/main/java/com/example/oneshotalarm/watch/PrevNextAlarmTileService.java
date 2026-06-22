package com.example.oneshotalarm.watch;

import android.content.SharedPreferences;
import android.util.Log;

import androidx.wear.protolayout.ColorBuilders;
import androidx.wear.protolayout.DimensionBuilders;
import androidx.wear.protolayout.LayoutElementBuilders;
import androidx.wear.protolayout.ModifiersBuilders;
import androidx.wear.protolayout.TimelineBuilders;
import androidx.wear.tiles.RequestBuilders;
import androidx.wear.tiles.ResourceBuilders;
import androidx.wear.tiles.TileBuilders;
import androidx.wear.tiles.TileService;

import com.google.android.gms.wearable.Node;
import com.google.android.gms.wearable.Wearable;
import com.google.common.util.concurrent.Futures;
import com.google.common.util.concurrent.ListenableFuture;

import java.text.SimpleDateFormat;
import java.util.List;
import java.util.Locale;

public class PrevNextAlarmTileService extends TileService {
    static final String PREFS = "prev_next_alarm_tile";
    static final String KEY_PREV_TIME = "prev_time";
    static final String KEY_PREV_DATE = "prev_date";
    static final String KEY_PREV_LABEL = "prev_label";
    static final String KEY_PREV_AT = "prev_at";
    static final String KEY_NEXT_TIME = "next_time";
    static final String KEY_NEXT_DATE = "next_date";
    static final String KEY_NEXT_LABEL = "next_label";
    static final String KEY_NEXT_AT = "next_at";
    static final String KEY_UPDATED_AT = "updated_at";

    private static final String TAG = "ShiftAlarmTile";
    private static final String RESOURCES_VERSION = "1";
    private static final String TILE_STATE_REQUEST_PATH = "/oneshotalarm/tile-state-request";

    @Override
    protected ListenableFuture<TileBuilders.Tile> onTileRequest(RequestBuilders.TileRequest requestParams) {
        return Futures.immediateFuture(buildTile());
    }

    @Override
    protected ListenableFuture<ResourceBuilders.Resources> onResourcesRequest(RequestBuilders.ResourcesRequest requestParams) {
        return Futures.immediateFuture(
                new ResourceBuilders.Resources.Builder()
                        .setVersion(RESOURCES_VERSION)
                        .build()
        );
    }

    private TileBuilders.Tile buildTile() {
        SharedPreferences prefs = getSharedPreferences(PREFS, MODE_PRIVATE);
        String prevTime = prefs.getString(KEY_PREV_TIME, "--:--");
        String prevDate = prefs.getString(KEY_PREV_DATE, "");
        String prevLabel = prefs.getString(KEY_PREV_LABEL, "等待電話資料");
        long prevAt = prefs.getLong(KEY_PREV_AT, 0L);
        String nextTime = prefs.getString(KEY_NEXT_TIME, "--:--");
        String nextDate = prefs.getString(KEY_NEXT_DATE, "");
        String nextLabel = prefs.getString(KEY_NEXT_LABEL, "等待電話資料");
        long nextAt = prefs.getLong(KEY_NEXT_AT, 0L);
        long updatedAt = prefs.getLong(KEY_UPDATED_AT, 0L);
        long now = System.currentTimeMillis();

        LayoutElementBuilders.Column root = new LayoutElementBuilders.Column.Builder()
                .setWidth(DimensionBuilders.expand())
                .setHeight(DimensionBuilders.expand())
                .setHorizontalAlignment(LayoutElementBuilders.HORIZONTAL_ALIGN_CENTER)
                .setModifiers(new ModifiersBuilders.Modifiers.Builder()
                        .setBackground(new ModifiersBuilders.Background.Builder()
                                .setColor(ColorBuilders.argb(0xFF0F172A))
                                .build())
                        .setPadding(new ModifiersBuilders.Padding.Builder()
                                .setAll(DimensionBuilders.dp(7))
                                .build())
                        .build())
                .addContent(titleText("門前直樹"))
                .addContent(spacer(4))
                .addContent(alarmBlock("PREV", prevDate, durationSince(prevAt, now), prevTime, prevLabel, 0xFFE5E7EB))
                .addContent(spacer(0))
                .addContent(alarmBlock("NEXT", nextDate, durationUntil(nextAt, now), nextTime, nextLabel, 0xFFF8FAFC))
                .addContent(spacer(3))
                .addContent(footerText(updatedAt))
                .build();

        return new TileBuilders.Tile.Builder()
                .setResourcesVersion(RESOURCES_VERSION)
                .setFreshnessIntervalMillis(60_000L)
                .setTileTimeline(new TimelineBuilders.Timeline.Builder()
                        .addTimelineEntry(new TimelineBuilders.TimelineEntry.Builder()
                                .setLayout(new LayoutElementBuilders.Layout.Builder()
                                        .setRoot(root)
                                        .build())
                                .build())
                        .build())
                .build();
    }

    private LayoutElementBuilders.LayoutElement alarmBlock(
            String caption,
            String date,
            String delta,
            String time,
            String label,
            int timeColor
    ) {
        return new LayoutElementBuilders.Column.Builder()
                .setWidth(DimensionBuilders.expand())
                .setHorizontalAlignment(LayoutElementBuilders.HORIZONTAL_ALIGN_CENTER)
                .setModifiers(new ModifiersBuilders.Modifiers.Builder()
                        .setBackground(new ModifiersBuilders.Background.Builder()
                                .setColor(ColorBuilders.argb(0xFF111827))
                                .setCorner(new ModifiersBuilders.Corner.Builder()
                                        .setRadius(DimensionBuilders.dp(14))
                                        .build())
                                .build())
                        .setPadding(new ModifiersBuilders.Padding.Builder()
                                .setTop(DimensionBuilders.dp(2))
                                .setBottom(DimensionBuilders.dp(2))
                                .setStart(DimensionBuilders.dp(7))
                                .setEnd(DimensionBuilders.dp(7))
                                .build())
                        .build())
                .addContent(smallText(captionText(caption, date, delta), 0xFF93A4B8))
                .addContent(timeText(time, timeColor))
                .addContent(labelText(label))
                .build();
    }

    private LayoutElementBuilders.Text titleText(String text) {
        return new LayoutElementBuilders.Text.Builder()
                .setText(text)
                .setFontStyle(new LayoutElementBuilders.FontStyle.Builder()
                        .setSize(DimensionBuilders.sp(15))
                        .setColor(ColorBuilders.argb(0xFFF8FAFC))
                        .build())
                .build();
    }

    private LayoutElementBuilders.Text timeText(String text, int color) {
        return new LayoutElementBuilders.Text.Builder()
                .setText(text == null || text.isEmpty() ? "--:--" : text)
                .setFontStyle(new LayoutElementBuilders.FontStyle.Builder()
                        .setSize(DimensionBuilders.sp(27))
                        .setColor(ColorBuilders.argb(color))
                        .build())
                .build();
    }

    private LayoutElementBuilders.Text labelText(String text) {
        return new LayoutElementBuilders.Text.Builder()
                .setText(shorten(text, 34))
                .setMaxLines(2)
                .setFontStyle(new LayoutElementBuilders.FontStyle.Builder()
                        .setSize(DimensionBuilders.sp(14))
                        .setColor(ColorBuilders.argb(0xFFE5E7EB))
                        .build())
                .build();
    }

    private LayoutElementBuilders.Text smallText(String text, int color) {
        return new LayoutElementBuilders.Text.Builder()
                .setText(text == null ? "" : text)
                .setMaxLines(1)
                .setFontStyle(new LayoutElementBuilders.FontStyle.Builder()
                        .setSize(DimensionBuilders.sp(11))
                        .setColor(ColorBuilders.argb(color))
                        .build())
                .build();
    }

    private LayoutElementBuilders.Text footerText(long updatedAt) {
        String text = updatedAt > 0L
                ? "更新 " + new SimpleDateFormat("HH:mm", Locale.getDefault()).format(updatedAt)
                : "打開 Tile 時刷新";
        return smallText(text, 0xFF64748B);
    }

    private LayoutElementBuilders.Spacer spacer(int dp) {
        return new LayoutElementBuilders.Spacer.Builder()
                .setHeight(DimensionBuilders.dp(dp))
                .build();
    }

    private String shorten(String raw, int limit) {
        String value = raw == null ? "" : raw.trim();
        if (value.isEmpty()) {
            return "沒有資料";
        }
        if (value.length() <= limit) {
            return value;
        }
        return value.substring(0, Math.max(0, limit - 1)) + "…";
    }

    private String captionText(String caption, String date, String delta) {
        StringBuilder builder = new StringBuilder(caption == null ? "" : caption);
        if (date != null && !date.isEmpty()) {
            builder.append("  ").append(date);
        }
        if (delta != null && !delta.isEmpty()) {
            builder.append("  ").append(delta);
        }
        return builder.toString();
    }

    private String durationSince(long at, long now) {
        if (at <= 0L || now < at) {
            return "";
        }
        return "(" + clockDuration(now - at) + ")";
    }

    private String durationUntil(long at, long now) {
        if (at <= 0L || at < now) {
            return "";
        }
        return "(" + clockDuration(at - now) + ")";
    }

    private String clockDuration(long millis) {
        long totalSeconds = Math.max(0L, millis / 1000L);
        long days = totalSeconds / 86400L;
        long hours = (totalSeconds % 86400L) / 3600L;
        long minutes = (totalSeconds % 3600L) / 60L;
        return String.format(Locale.US, "%dd %02d:%02d", days, hours, minutes);
    }

    private void requestFreshStateFromPhone() {
        Wearable.getNodeClient(this).getConnectedNodes()
                .addOnSuccessListener(this::sendRequestToNodes)
                .addOnFailureListener(e -> Log.e(TAG, "Get phone nodes failed", e));
    }

    private void sendRequestToNodes(List<Node> nodes) {
        if (nodes == null || nodes.isEmpty()) {
            Log.d(TAG, "No connected phone node for tile refresh");
            return;
        }
        for (Node node : nodes) {
            Wearable.getMessageClient(this)
                    .sendMessage(node.getId(), TILE_STATE_REQUEST_PATH, new byte[0])
                    .addOnSuccessListener(id -> Log.d(TAG, "Requested tile state from phone"))
                    .addOnFailureListener(e -> Log.e(TAG, "Request tile state failed", e));
        }
    }
}
