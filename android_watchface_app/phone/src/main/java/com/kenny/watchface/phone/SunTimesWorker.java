package com.kenny.watchface.phone;

import android.content.Context;
import android.util.Log;

import androidx.annotation.NonNull;
import androidx.work.Worker;
import androidx.work.WorkerParameters;

public class SunTimesWorker extends Worker {
    private static final String TAG = "SunTimesWorker";

    public SunTimesWorker(@NonNull Context context, @NonNull WorkerParameters params) {
        super(context, params);
    }

    @NonNull
    @Override
    public Result doWork() {
        try {
            SunTimesSync.syncNowBlocking(getApplicationContext());
            return Result.success();
        } catch (Exception error) {
            Log.w(TAG, "Unable to sync HKO sun times", error);
            return Result.retry();
        }
    }
}
