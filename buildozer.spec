[app]

# App identity
title = Modern Bulk Mailer
package.name = modernbulkmailer
package.domain = com.bulkmailer

# Entry point
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json
source.include_patterns = session.json

# Version
version = 1.0

# App requirements — ALL Python packages the app needs
requirements = python3,kivy,requests,markdown2,openssl

# Icon & splash (place icon.png / presplash.png in project root to customise)
# icon.filename = %(source.dir)s/icon.png
# presplash.filename = %(source.dir)s/presplash.png

# Orientation
orientation = portrait

# Android
android.api = 31
android.minapi = 21
android.ndk_path = 
android.sdk_path = 
android.ndk = 25b
android.arch = arm64-v8a

# Permissions
android.permissions = INTERNET,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE

# Allow cleartext traffic (needed for localhost loopback during OAuth)
android.manifest.attributes = usesCleartextTraffic:true

# Features
android.features = android.hardware.touchscreen

# Kivy boot / entry
p4a.bootstrap = sdl2

[buildozer]

# Log level: 0 = error, 1 = info, 2 = debug
log_level = 2
warn_on_root = 1
