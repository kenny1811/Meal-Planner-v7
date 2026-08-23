package com.example.oneshotalarm;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.net.Uri;

import org.json.JSONObject;

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

    /** 觸發時間，epoch 毫秒 */
    public static final String COL_AT = "at_millis";
    /** 鬧鐘標籤，例如「埋位 2」 */
    public static final String COL_LABEL = "label";

    @Override
    public boolean onCreate() {
        return true;
    }

    @Override
    public Cursor query(Uri uri, String[] projection, String selection,
                        String[] selectionArgs, String sortOrder) {
        if (!PATH_NEXT.equals(uri.getLastPathSegment())) {
            return null;
        }
        MatrixCursor cursor = new MatrixCursor(new String[]{COL_AT, COL_LABEL});
        AlarmStore.PrevNext pair = AlarmStore.findPrevNext(getContext(), System.currentTimeMillis());
        if (pair != null && pair.next != null) {
            JSONObject next = pair.next;
            String label = next.optString("label", "").trim();
            cursor.addRow(new Object[]{pair.nextAt, label});
        }
        // 冇下一個鬧鐘就出一個空 cursor，唔係 null —— 咁對面先分得清
        // 「查得到但係冇鬧鐘」同「查唔到」。
        return cursor;
    }

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
