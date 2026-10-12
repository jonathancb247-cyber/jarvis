plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.jarvisos.companion"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.jarvisos.companion"
        minSdk = 26
        targetSdk = 34
        versionCode = 1
        versionName = "0.1.0"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    buildFeatures { buildConfig = true }
    flavorDimensions += "purpose"
    productFlavors {
        create("companion") {
            dimension = "purpose"
            buildConfigField("int", "LOOPBACK_PORT", "8767")
            buildConfigField("boolean", "UNDERSTANDING_LAB", "false")
            manifestPlaceholders["hostExported"] = "true"
        }
        create("understandingLab") {
            dimension = "purpose"
            applicationIdSuffix = ".understandinglab"
            buildConfigField("int", "LOOPBACK_PORT", "8769")
            buildConfigField("boolean", "UNDERSTANDING_LAB", "true")
            manifestPlaceholders["hostExported"] = "false"
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlin {
        compilerOptions {
            jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17)
        }
    }

    testOptions {
        unitTests.isReturnDefaultValues = true
    }
}

dependencies {
    // LiteRT-LM Kotlin API for Android (Google Maven). Pinned to the exact
    // version verified during Gate 2 discovery; do NOT use "latest.release" in
    // committed code. CPU backend only for Gate 2A.
    implementation("com.google.ai.edge.litertlm:litertlm-android:0.16.1")

    implementation("org.nanohttpd:nanohttpd:2.3.1")
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("com.google.android.material:material:1.12.0")
    implementation("androidx.constraintlayout:constraintlayout:2.1.4")

    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20240303")
    testImplementation("androidx.test:core:1.6.1")
}
