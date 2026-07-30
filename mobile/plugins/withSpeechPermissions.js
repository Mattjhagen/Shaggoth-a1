const { withInfoPlist, withAndroidManifest } = require("expo/config-plugins");

function withSpeechPermissions(config) {
  config = withInfoPlist(config, (config) => {
    config.modResults.NSSpeechRecognitionUsageDescription =
      "Shaggoth uses speech recognition so you can talk to it instead of typing.";
    config.modResults.NSMicrophoneUsageDescription =
      "Shaggoth needs microphone access for voice input.";
    return config;
  });

  config = withAndroidManifest(config, (config) => {
    const manifest = config.modResults.manifest;
    if (!manifest["uses-permission"]) manifest["uses-permission"] = [];

    const perms = manifest["uses-permission"];
    const needed = ["android.permission.RECORD_AUDIO"];

    for (const p of needed) {
      if (!perms.some((e) => e.$["android:name"] === p)) {
        perms.push({ $: { "android:name": p } });
      }
    }

    return config;
  });

  return config;
}

module.exports = withSpeechPermissions;
