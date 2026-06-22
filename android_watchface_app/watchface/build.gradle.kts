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
        versionCode = 1
        versionName = "1.0.0"
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
