package com.example.oneshotalarm.watch;

import android.os.RemoteException;

import androidx.annotation.NonNull;
import androidx.wear.watchface.complications.data.ComplicationData;
import androidx.wear.watchface.complications.data.ComplicationType;
import androidx.wear.watchface.complications.datasource.ComplicationDataSourceService;
import androidx.wear.watchface.complications.datasource.ComplicationRequest;

public class PrevAlarmLabelLine2ComplicationDataSourceService extends ComplicationDataSourceService {
    @Override
    public void onComplicationRequest(
            @NonNull ComplicationRequest request,
            @NonNull ComplicationRequestListener listener
    ) {
        AlarmStateRefresh.requestIfAllowed(this);
        try {
            listener.onComplicationData(AlarmComplicationData.buildLabelLine(this, false, 1));
        } catch (RemoteException ignored) {
            // The system listener went away before we could respond.
        }
    }

    @Override
    public ComplicationData getPreviewData(@NonNull ComplicationType type) {
        return AlarmComplicationData.previewLabelLine(false, 1);
    }
}
