# Innoverce 26 for Android

This Android app wraps the existing website in a WebView and starts its existing
Python/SQLite service inside the app. The service listens only on
`127.0.0.1:8765`; no server needs to be deployed.

Account and event-registration data is stored in the app's private files
directory. It is local to each installation and is removed when the app is
uninstalled. The workspace's `data/innoverce26.sqlite3` is deliberately not
copied into the APK.

## Build a debug APK

From this directory, run:

```powershell
.\gradlew.bat assembleDebug
```

Or open this `android` directory in Android Studio, allow Gradle to sync, then
select **Build > Build Bundle(s) / APK(s) > Build APK(s)**. The APK is created at:

`app/build/outputs/apk/debug/app-debug.apk`

The build requires Android SDK Platform 35, Android build-tools, JDK 17, and an
internet connection to download Gradle and the Chaquopy Android Python runtime.
The page's fonts and Three.js library are loaded from their existing HTTPS CDN
URLs, so those visual assets also need an internet connection.

The generated app is a debug APK for testing. A release APK intended for
distribution should be built and signed with your own Android signing key.
