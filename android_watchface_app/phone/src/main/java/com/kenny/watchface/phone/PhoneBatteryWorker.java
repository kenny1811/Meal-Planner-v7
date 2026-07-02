package com.kenny.watchface.phone;

import android.content.Context;

import androidx.annotation.NonNull;
import androidx.work.Worker;
import androidx.work.WorkerParameters;

public class PhoneBatteryWorker extends Worker {
    public PhoneBatteryWorker(@NonNull Context context, @NonNull WorkerParameters params) {
        super(context, params);
    }

    @NonNull
    @Override
    public Result doWork() {
        BatterySync.syncNow(getApplicationContext());
        return Result.success();
    }
}
