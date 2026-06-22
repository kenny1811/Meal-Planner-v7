package com.kenny.watchface.wear;

import android.os.RemoteException;

import androidx.annotation.NonNull;
import androidx.wear.watchface.complications.data.ComplicationData;
import androidx.wear.watchface.complications.data.ComplicationText;
import androidx.wear.watchface.complications.data.ComplicationType;
import androidx.wear.watchface.complications.data.PlainComplicationText;
import androidx.wear.watchface.complications.data.RangedValueComplicationData;
import androidx.wear.watchface.complications.datasource.ComplicationDataSourceService;
import androidx.wear.watchface.complications.datasource.ComplicationRequest;

public class PhoneBatteryComplicationDataSourceService extends ComplicationDataSourceService {
    @Override
    public void onComplicationRequest(
            @NonNull ComplicationRequest request,
            @NonNull ComplicationRequestListener listener
    ) {
        PhoneBatteryRequest.requestIfAllowed(this);
        int percent = PhoneBatteryStore.percent(this);
        try {
            listener.onComplicationData(buildData(percent >= 0 ? percent : 0, percent >= 0));
        } catch (RemoteException ignored) {
            // The system listener went away before we could respond.
        }
    }

    @Override
    public void onComplicationActivated(int complicationInstanceId, @NonNull ComplicationType type) {
        PhoneBatteryRequest.requestIfAllowed(this);
    }

    @Override
    public void onStartImmediateComplicationRequests(int complicationInstanceId) {
        PhoneBatteryRequest.requestIfAllowed(this);
    }

    @Override
    public ComplicationData getPreviewData(@NonNull ComplicationType type) {
        return buildData(82, true);
    }

    private ComplicationData buildData(int percent, boolean hasPhoneData) {
        String value = hasPhoneData ? percent + "%" : "--%";
        ComplicationText description = text("Phone battery " + value);
        return new RangedValueComplicationData.Builder(percent, 0f, 100f, description)
                .setTitle(text("PHONE"))
                .setText(text(value))
                .setValueType(RangedValueComplicationData.TYPE_PERCENTAGE)
                .build();
    }

    private static ComplicationText text(String value) {
        return new PlainComplicationText.Builder(value).build();
    }
}
