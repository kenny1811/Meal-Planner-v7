plugins {
    id("com.android.application")
}

android {
    namespace = "com.kenny.watchface"
    compileSdk = 36
    compileSdkMinor = 1

    defaultConfig {
        applicationId = "com.kenny.watchface"
        minSdk = 33
        targetSdk = 36
        // 版本只改 versionName 一行；versionCode 自動 = major*100 + minor（7.0 → 700）
        versionName = "7.0"
        versionCode = versionName!!.split(".").let { it[0].toInt() * 100 + it[1].toInt() }
    }

    buildTypes {
        debug {
            isMinifyEnabled = true
        }
        release {
            isMinifyEnabled = true
            isShrinkResources = false
            signingConfig = signingConfigs.getByName("debug")
        }
    }
}
