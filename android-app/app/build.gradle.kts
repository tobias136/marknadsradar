plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.chaquo.python")
}

android {
    namespace = "com.marknadsradar.app"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.marknadsradar.app"
        minSdk = 24
        targetSdk = 34
        versionCode = 1
        versionName = "1.0"
        // arm64-v8a: alla moderna telefoner (och en mindre fil att ladda ner).
        ndk { abiFilters += listOf("arm64-v8a") }
    }

    // Signeringsnyckeln ligger INTE i repot. Bygget läser den från miljövariabler (GitHub Secrets, se README).
    // Saknas de används Androids tillfälliga debug-nyckel: APK:n går att installera, men en senare version
    // med annan nyckel kan inte installeras över den (då måste appen avinstalleras och datan försvinner).
    // Signera med alla tre scheman (v1+v2+v3) för bredast möjliga kompatibilitet vid installation.
    signingConfigs {
        getByName("debug") {
            enableV1Signing = true
            enableV2Signing = true
            enableV3Signing = true
        }
    }
    val ksFile = System.getenv("MR_KEYSTORE_FILE")
    if (!ksFile.isNullOrEmpty() && File(ksFile).exists()) {
        signingConfigs {
            getByName("debug") {
                storeFile = File(ksFile)
                storePassword = System.getenv("MR_KEYSTORE_PASSWORD")
                keyAlias = System.getenv("MR_KEY_ALIAS")
                keyPassword = System.getenv("MR_KEY_PASSWORD")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}

chaquopy {
    defaultConfig {
        version = "3.12"
        pip {
            // Kompilerade paket kommer från Chaquopys eget index. Resten är rena Python-paket.
            install("numpy")
            install("pandas")
            // FastAPI 0.99 och pydantic 1: pydantic 2 kräver pydantic-core (Rust), som saknas för Android.
            install("fastapi==0.99.1")
            install("starlette==0.27.0")
            install("pydantic<2")
            install("uvicorn")
            install("h11")
        }
    }
}

// Programkoden bor i projektets rot. Den kopieras in här inför varje bygge, så det finns bara en version.
val appRoot = rootProject.projectDir.parentFile
val syncSources by tasks.registering {
    doLast {
        copy {
            from(File(appRoot, "app")) { exclude("**/__pycache__/**") }
            into(File(projectDir, "src/main/python/app"))
        }
        copy {
            from(File(appRoot, "static"))
            into(File(projectDir, "src/main/assets/static"))
        }
    }
}
tasks.named("preBuild") { dependsOn(syncSources) }

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
}
