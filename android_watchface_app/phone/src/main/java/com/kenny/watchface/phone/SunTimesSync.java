package com.kenny.watchface.phone;

import android.content.Context;
import android.util.Log;

import com.google.android.gms.tasks.Tasks;
import com.google.android.gms.wearable.DataMap;
import com.google.android.gms.wearable.PutDataMapRequest;
import com.google.android.gms.wearable.PutDataRequest;
import com.google.android.gms.wearable.Wearable;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

import androidx.work.Constraints;
import androidx.work.ExistingPeriodicWorkPolicy;
import androidx.work.NetworkType;
import androidx.work.PeriodicWorkRequest;
import androidx.work.WorkManager;

final class SunTimesSync {
    static final String PATH = "/sun_times";
    static final String KEY_DATE = "date";
    static final String KEY_SUNRISE = "sunrise";
    static final String KEY_SUNSET = "sunset";
    static final String KEY_TRANSIT = "transit";
    static final String KEY_TIMESTAMP = "timestamp";
    static final String KEY_SOURCE = "source";
    private static final String KEY_NONCE = "nonce";
    private static final String WORK_NAME = "hko_sun_times_sync";
    private static final String TAG = "SunTimesSync";
    private static final ZoneId HK_ZONE = ZoneId.of("Asia/Hong_Kong");
    private static final LocalTime DAILY_SYNC_TIME = LocalTime.of(5, 30);
    private static final ExecutorService EXECUTOR = Executors.newSingleThreadExecutor();

    private SunTimesSync() {
    }

    static void scheduleDailyAt0530(Context context) {
        Constraints constraints = new Constraints.Builder()
                .setRequiredNetworkType(NetworkType.CONNECTED)
                .build();
        PeriodicWorkRequest request = new PeriodicWorkRequest.Builder(
                SunTimesWorker.class,
                1,
                TimeUnit.DAYS
        )
                .setConstraints(constraints)
                .setInitialDelay(delayUntilNext0530().toMillis(), TimeUnit.MILLISECONDS)
                .build();
        WorkManager.getInstance(context).enqueueUniquePeriodicWork(
                WORK_NAME,
                ExistingPeriodicWorkPolicy.UPDATE,
                request
        );
    }

    static void syncNowAsync(Context context) {
        Context appContext = context.getApplicationContext();
        EXECUTOR.execute(() -> {
            try {
                syncNowBlocking(appContext);
            } catch (Exception error) {
                Log.w(TAG, "Sun times sync failed", error);
            }
        });
    }

    static boolean syncNowBlocking(Context context) throws Exception {
        LocalDate today = LocalDate.now(HK_ZONE);
        SunTimes times = fetch(today);
        PutDataMapRequest request = PutDataMapRequest.create(PATH);
        DataMap dataMap = request.getDataMap();
        dataMap.putString(KEY_DATE, times.date);
        dataMap.putString(KEY_SUNRISE, times.sunrise);
        dataMap.putString(KEY_SUNSET, times.sunset);
        dataMap.putString(KEY_TRANSIT, times.transit);
        dataMap.putLong(KEY_TIMESTAMP, System.currentTimeMillis());
        dataMap.putString(KEY_SOURCE, "HKO SRS");
        dataMap.putLong(KEY_NONCE, System.nanoTime());

        PutDataRequest putDataRequest = request.asPutDataRequest();
        putDataRequest.setUrgent();
        Tasks.await(Wearable.getDataClient(context).putDataItem(putDataRequest), 20, TimeUnit.SECONDS);
        Log.d(TAG, "Synced HKO sun times " + times.date + " " + times.sunrise + "/" + times.sunset);
        return true;
    }

    private static Duration delayUntilNext0530() {
        ZonedDateTime now = ZonedDateTime.now(HK_ZONE);
        ZonedDateTime next = now.toLocalDate().atTime(DAILY_SYNC_TIME).atZone(HK_ZONE);
        if (!next.isAfter(now)) {
            next = next.plusDays(1);
        }
        return Duration.between(now, next);
    }

    private static SunTimes fetch(LocalDate date) throws IOException {
        String url = "https://data.weather.gov.hk/weatherAPI/opendata/opendata.php"
                + "?dataType=SRS&year=" + date.getYear() + "&rformat=csv";
        HttpURLConnection connection = (HttpURLConnection) new URL(url).openConnection();
        connection.setConnectTimeout(15000);
        connection.setReadTimeout(15000);
        connection.setRequestMethod("GET");
        connection.setRequestProperty("User-Agent", "KennyWatchFace/1.0");
        try {
            int responseCode = connection.getResponseCode();
            if (responseCode < 200 || responseCode >= 300) {
                throw new IOException("HKO SRS HTTP " + responseCode);
            }
            try (InputStream stream = connection.getInputStream();
                 BufferedReader reader = new BufferedReader(new InputStreamReader(stream, StandardCharsets.UTF_8))) {
                return parseCsv(reader, date);
            }
        } finally {
            connection.disconnect();
        }
    }

    private static SunTimes parseCsv(BufferedReader reader, LocalDate date) throws IOException {
        String target = date.toString();
        String line;
        while ((line = reader.readLine()) != null) {
            line = stripBom(line.trim());
            if (line.isEmpty() || line.startsWith("YYYY-MM-DD")) {
                continue;
            }
            String[] fields = line.split(",", -1);
            if (fields.length >= 4 && target.equals(fields[0].trim())) {
                return new SunTimes(
                        fields[0].trim(),
                        fields[1].trim(),
                        fields[2].trim(),
                        fields[3].trim()
                );
            }
        }
        throw new IOException("No HKO SRS row for " + target);
    }

    private static String stripBom(String value) {
        if (!value.isEmpty() && value.charAt(0) == '\uFEFF') {
            return value.substring(1);
        }
        return value;
    }

    private static final class SunTimes {
        final String date;
        final String sunrise;
        final String transit;
        final String sunset;

        SunTimes(String date, String sunrise, String transit, String sunset) {
            this.date = date;
            this.sunrise = sunrise;
            this.transit = transit;
            this.sunset = sunset;
        }
    }
}
