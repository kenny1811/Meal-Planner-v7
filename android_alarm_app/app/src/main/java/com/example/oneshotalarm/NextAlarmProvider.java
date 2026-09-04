package com.example.oneshotalarm;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.content.Context;
import android.content.SharedPreferences;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.net.Uri;

import org.json.JSONException;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/**
 * 唯讀出口：畀外面（門前直樹Launcher 個 W widget）讀到「下一個鬧鐘」。
 *
 * 點解要開呢個：Android 冇公開 API 畀你讀第二個 app 嘅鬧鐘。
 * {@code AlarmManager.getNextAlarmClock()} 只會出全機最早嗰一個，唔分邊個 app；
 * 而 widget 入面嘅內容外面亦都讀唔到。所以要由呢邊主動出。
 *
 * 只出兩個欄位（時間 + 標籤），冇任何其他數據，亦都唔支援寫入。
 *
 * <pre>content://com.example.oneshotalarm.nextalarm/next</pre>
 */
public class NextAlarmProvider extends ContentProvider {

    public static final String AUTHORITY = "com.example.oneshotalarm.nextalarm";
    private static final String PATH_NEXT = "next";
    /** 逐日更碼，畀 W 個更表輪盤用 */
    private static final String PATH_ROSTER = "roster";

    /** 觸發時間，epoch 毫秒 */
    public static final String COL_AT = "at_millis";
    /** 鬧鐘標籤，例如「埋位 2」 */
    public static final String COL_LABEL = "label";
    /** 上一個鬧鐘嘅時間，epoch 毫秒；冇就 0 */
    public static final String COL_PREV_AT = "prev_at_millis";
    /** 上一個鬧鐘嘅標籤 */
    public static final String COL_PREV_LABEL = "prev_label";
    /** 更表用：日期 yyyy-MM-dd */
    public static final String COL_DATE = "date_iso";
    /** 更表用：更碼，例如 SB、WL34、VPP */
    public static final String COL_CODE = "roster_code";

    @Override
    public boolean onCreate() {
        return true;
    }

    /**
     * 鬧鐘或者更表改咗就叫一聲：L（門前直樹Launcher）用 ContentObserver 聽住
     * /next 同 /roster，收到先重讀。冇呢句佢就要每幾分鐘 query 一次兜底，
     * 每次都會喚醒呢個 process。冇人聽都唔緊要。
     */
    public static void notifyChanged(Context context) {
        try {
            android.content.ContentResolver cr = context.getApplicationContext().getContentResolver();
            cr.notifyChange(Uri.parse("content://" + AUTHORITY + "/" + PATH_NEXT), null);
            cr.notifyChange(Uri.parse("content://" + AUTHORITY + "/" + PATH_ROSTER), null);
        } catch (Exception ignored) {
        }
    }

    @Override
    public Cursor query(Uri uri, String[] projection, String selection,
                        String[] selectionArgs, String sortOrder) {
        if (PATH_ROSTER.equals(uri.getLastPathSegment())) {
            return queryRoster();
        }
        if (!PATH_NEXT.equals(uri.getLastPathSegment())) {
            return null;
        }
        MatrixCursor cursor = new MatrixCursor(
                new String[]{COL_AT, COL_LABEL, COL_PREV_AT, COL_PREV_LABEL});
        AlarmStore.PrevNext pair = AlarmStore.findPrevNext(getContext(), System.currentTimeMillis());
        if (pair != null && (pair.next != null || pair.prev != null)) {
            long nextAt = pair.next == null ? 0L : pair.nextAt;
            String nextLabel = pair.next == null ? "" : pair.next.optString("label", "").trim();
            long prevAt = pair.prev == null ? 0L : pair.prevAt;
            String prevLabel = pair.prev == null ? "" : pair.prev.optString("label", "").trim();
            cursor.addRow(new Object[]{nextAt, nextLabel, prevAt, prevLabel});
        }
        // 冇下一個鬧鐘就出一個空 cursor，唔係 null —— 咁對面先分得清
        // 「查得到但係冇鬧鐘」同「查唔到」。
        return cursor;
    }

    /**
     * 全部存住嘅日子同更碼，由早到夜。
     *
     * 更碼本身係逐日餐單 JSON 入面嘅 {@code day.roster_code} —— 餐單同更表係
     * 同一份數據，餐單按當日返咩更去計，所以更碼一定齊。
     * 一次過出晒，對面自己揀睇邊幾日。
     */
    private Cursor queryRoster() {
        MatrixCursor cursor = new MatrixCursor(new String[]{COL_DATE, COL_CODE});
        SharedPreferences prefs = getContext()
                .getSharedPreferences("alarm_store", Context.MODE_PRIVATE);

        List<String> dates = new ArrayList<>();
        for (String key : prefs.getAll().keySet()) {
            if (key.startsWith(MEAL_PREFIX) && key.length() == MEAL_PREFIX.length() + 10) {
                dates.add(key.substring(MEAL_PREFIX.length()));
            }
        }
        Collections.sort(dates);

        for (String date : dates) {
            String raw = prefs.getString(MEAL_PREFIX + date, "");
            if (raw == null || raw.isEmpty()) {
                continue;
            }
            try {
                JSONObject day = new JSONObject(raw).optJSONObject("day");
                if (day == null) {
                    continue;
                }
                String code = day.optString("roster_code", "").trim();
                if (!code.isEmpty()) {
                    cursor.addRow(new Object[]{date, code});
                }
            } catch (JSONException ignored) {
                // 個別日子壞咗就跳過，唔好連累成個清單
            }
        }
        return cursor;
    }

    private static final String MEAL_PREFIX = "meal_plan_json_";

    @Override
    public String getType(Uri uri) {
        return "vnd.android.cursor.item/vnd.oneshotalarm.nextalarm";
    }

    @Override
    public Uri insert(Uri uri, ContentValues values) {
        throw new UnsupportedOperationException("read-only");
    }

    @Override
    public int delete(Uri uri, String selection, String[] selectionArgs) {
        throw new UnsupportedOperationException("read-only");
    }

    @Override
    public int update(Uri uri, ContentValues values, String selection, String[] selectionArgs) {
        throw new UnsupportedOperationException("read-only");
    }
}
