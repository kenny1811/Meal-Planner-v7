plugins {
    id("com.android.application")
}

android {
    namespace = "com.kenny.watchface.phone"
    compileSdk = 36
    compileSdkMinor = 1

    defaultConfig {
        applicationId = "com.kenny.watchface.wear"
        minSdk = 26
        targetSdk = 36
        // 版本只改 versionName 一行；versionCode 自動 = major*100 + minor（1.1 → 101）
        versionName = "1.1"
        versionCode = versionName!!.split(".").let { it[0].toInt() * 100 + it[1].toInt() }
    }
}

dependencies {
    implementation("androidx.work:work-runtime:2.9.1")
    implementation("com.google.android.gms:play-services-wearable:19.0.0")
}
