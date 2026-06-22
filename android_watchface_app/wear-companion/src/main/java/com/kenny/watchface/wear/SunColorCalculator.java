package com.kenny.watchface.wear;

import android.content.Context;
import android.content.SharedPreferences;

import java.time.ZoneId;
import java.time.ZonedDateTime;

final class SunColorCalculator {
    private static final ZoneId HK_ZONE = ZoneId.of("Asia/Hong_Kong");
    private static final int FALLBACK_SUNRISE = 5 * 60 + 40;
    private static final int FALLBACK_TRANSIT = 12 * 60 + 25;
    private static final int FALLBACK_SUNSET = 19 * 60 + 10;

    private SunColorCalculator() {
    }

    static State current(Context context) {
        return current(context, ZonedDateTime.now(HK_ZONE));
    }

    static State current(Context context, ZonedDateTime now) {
        SharedPreferences prefs = SunTimesStore.prefs(context);
        int sunrise = parseMinutes(
                prefs.getString(SunTimesStore.KEY_SUNRISE, ""),
                FALLBACK_SUNRISE
        );
        int transit = parseMinutes(
                prefs.getString(SunTimesStore.KEY_TRANSIT, ""),
                FALLBACK_TRANSIT
        );
        int sunset = parseMinutes(
                prefs.getString(SunTimesStore.KEY_SUNSET, ""),
                FALLBACK_SUNSET
        );

        int preDawnStart = clamp(sunrise - 90, 0, sunrise);
        int morningOneThird = lerpMinutes(sunrise, transit, 1, 3);
        int morningTwoThirds = lerpMinutes(sunrise, transit, 2, 3);
        int noonStart = clamp(transit - 45, sunrise, sunset);
        int noonEnd = clamp(transit + 45, sunrise, sunset);
        int afternoonOneThird = lerpMinutes(transit, sunset, 1, 3);
        int afternoonTwoThirds = lerpMinutes(transit, sunset, 2, 3);
        int nightfallEnd = clamp(sunset + 90, sunset, 24 * 60);
        int minute = now.getHour() * 60 + now.getMinute();

        Bucket bucket;
        if (minute >= preDawnStart && minute < sunrise) {
            bucket = Bucket.PRE_DAWN;
        } else if (minute >= sunrise && minute < morningOneThird) {
            bucket = Bucket.DAWN;
        } else if (minute >= morningOneThird && minute < morningTwoThirds) {
            bucket = Bucket.MORNING;
        } else if (minute >= morningTwoThirds && minute < noonStart) {
            bucket = Bucket.LATE_MORNING;
        } else if (minute >= noonStart && minute < noonEnd) {
            bucket = Bucket.NOON;
        } else if (minute >= noonEnd && minute < afternoonOneThird) {
            bucket = Bucket.EARLY_AFTERNOON;
        } else if (minute >= afternoonOneThird && minute < afternoonTwoThirds) {
            bucket = Bucket.AFTERNOON;
        } else if (minute >= afternoonTwoThirds && minute < sunset) {
            bucket = Bucket.DUSK;
        } else if (minute >= sunset && minute < nightfallEnd) {
            bucket = Bucket.NIGHTFALL;
        } else {
            bucket = Bucket.NIGHT;
        }

        return new State(
                bucket,
                bucket.color,
                minute,
                sunrise,
                preDawnStart,
                morningOneThird,
                morningTwoThirds,
                noonStart,
                noonEnd,
                afternoonOneThird,
                afternoonTwoThirds,
                sunset,
                nightfallEnd
        );
    }

    private static int parseMinutes(String value, int fallback) {
        if (value == null) {
            return fallback;
        }
        String[] parts = value.trim().split(":", -1);
        if (parts.length < 2) {
            return fallback;
        }
        try {
            int hour = Integer.parseInt(parts[0]);
            int minute = Integer.parseInt(parts[1]);
            if (hour < 0 || hour > 23 || minute < 0 || minute > 59) {
                return fallback;
            }
            return hour * 60 + minute;
        } catch (NumberFormatException error) {
            return fallback;
        }
    }

    private static int clamp(int value, int min, int max) {
        return Math.max(min, Math.min(max, value));
    }

    private static int lerpMinutes(int start, int end, int numerator, int denominator) {
        return start + ((end - start) * numerator / denominator);
    }

    enum Bucket {
        NIGHT("#ff241a6b"),
        PRE_DAWN("#ff30238f"),
        DAWN("#ff4f3fbd"),
        MORNING("#ff7668dc"),
        LATE_MORNING("#ffa19aea"),
        NOON("#fff4f2ff"),
        EARLY_AFTERNOON("#ffc6c2f2"),
        AFTERNOON("#ff9288e5"),
        DUSK("#ff6654d1"),
        NIGHTFALL("#ff3a2a9e");

        final String color;

        Bucket(String color) {
            this.color = color;
        }
    }

    static final class State {
        final Bucket bucket;
        final String color;
        final int minute;
        final int sunrise;
        final int preDawnStart;
        final int morningOneThird;
        final int morningTwoThirds;
        final int noonStart;
        final int noonEnd;
        final int afternoonOneThird;
        final int afternoonTwoThirds;
        final int sunset;
        final int nightfallEnd;

        State(
                Bucket bucket,
                String color,
                int minute,
                int sunrise,
                int preDawnStart,
                int morningOneThird,
                int morningTwoThirds,
                int noonStart,
                int noonEnd,
                int afternoonOneThird,
                int afternoonTwoThirds,
                int sunset,
                int nightfallEnd
        ) {
            this.bucket = bucket;
            this.color = color;
            this.minute = minute;
            this.sunrise = sunrise;
            this.preDawnStart = preDawnStart;
            this.morningOneThird = morningOneThird;
            this.morningTwoThirds = morningTwoThirds;
            this.noonStart = noonStart;
            this.noonEnd = noonEnd;
            this.afternoonOneThird = afternoonOneThird;
            this.afternoonTwoThirds = afternoonTwoThirds;
            this.sunset = sunset;
            this.nightfallEnd = nightfallEnd;
        }
    }
}
