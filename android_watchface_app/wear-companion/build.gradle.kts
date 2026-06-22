plugins {
    id("com.android.application")
}

android {
    namespace = "com.kenny.watchface.wear"
    compileSdk = 36
    compileSdkMinor = 1

    defaultConfig {
        applicationId = "com.kenny.watchface.wear"
        minSdk = 33
        targetSdk = 36
        versionCode = 1
        versionName = "1.0.0"
    }
}

dependencies {
    implementation("androidx.wear.watchface:watchface-complications-data-source:1.2.1")
    implementation("com.google.android.gms:play-services-wearable:19.0.0")
}
