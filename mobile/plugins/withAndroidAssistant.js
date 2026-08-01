const { withAndroidManifest, withDangerousMod } = require("expo/config-plugins");
const fs = require("fs");
const path = require("path");

function getPackageName(config) {
  return config.android?.package || "com.relayapp.pro";
}

function withAndroidAssistant(config) {
  config = withAssistantManifest(config);
  config = withAssistantNativeFiles(config);
  return config;
}

function withAssistantManifest(config) {
  return withAndroidManifest(config, (config) => {
    const manifest = config.modResults;
    const app = manifest.manifest.application[0];

    const hasService = (app.service || []).some(
      (s) => s.$["android:name"] === ".ShaggothAssistService"
    );
    if (hasService) return config;

    if (!app.service) app.service = [];

    const pkg = getPackageName(config);

    app.service.push({
      $: {
        "android:name": ".ShaggothAssistService",
        "android:permission": "android.permission.BIND_VOICE_INTERACTION",
        "android:exported": "true",
      },
      "meta-data": [
        {
          $: {
            "android:name": "android.voice_interaction",
            "android:resource": "@xml/voice_interaction_service",
          },
        },
      ],
      "intent-filter": [
        {
          action: [
            {
              $: {
                "android:name":
                  "android.service.voice.VoiceInteractionService",
              },
            },
          ],
        },
      ],
    });

    app.service.push({
      $: {
        "android:name": ".ShaggothAssistSessionService",
        "android:permission": "android.permission.BIND_VOICE_INTERACTION",
        "android:exported": "false",
      },
    });

    const mainActivity = app.activity.find(
      (a) => a.$["android:name"] === ".MainActivity"
    );
    if (mainActivity) {
      if (!mainActivity["intent-filter"]) mainActivity["intent-filter"] = [];
      const hasAssist = mainActivity["intent-filter"].some((f) =>
        (f.action || []).some(
          (a) => a.$["android:name"] === "android.intent.action.ASSIST"
        )
      );
      if (!hasAssist) {
        mainActivity["intent-filter"].push({
          action: [
            { $: { "android:name": "android.intent.action.ASSIST" } },
          ],
          category: [
            { $: { "android:name": "android.intent.category.DEFAULT" } },
          ],
        });
      }
    }

    return config;
  });
}

function withAssistantNativeFiles(config) {
  return withDangerousMod(config, [
    "android",
    (config) => {
      const projectRoot = config.modRequest.projectRoot;
      const androidRoot = path.join(projectRoot, "android");
      const pkg = getPackageName(config);
      const pkgPath = pkg.replace(/\./g, "/");
      const javaDir = path.join(
        androidRoot,
        "app/src/main/java",
        pkgPath
      );
      const xmlDir = path.join(androidRoot, "app/src/main/res/xml");

      fs.mkdirSync(javaDir, { recursive: true });
      fs.mkdirSync(xmlDir, { recursive: true });

      fs.writeFileSync(
        path.join(javaDir, "ShaggothAssistService.java"),
        `package ${pkg};

import android.service.voice.VoiceInteractionService;

public class ShaggothAssistService extends VoiceInteractionService {
    @Override
    public void onReady() {
        super.onReady();
    }
}
`
      );

      fs.writeFileSync(
        path.join(javaDir, "ShaggothAssistSessionService.java"),
        `package ${pkg};

import android.os.Bundle;
import android.service.voice.VoiceInteractionSession;
import android.service.voice.VoiceInteractionSessionService;

public class ShaggothAssistSessionService extends VoiceInteractionSessionService {
    @Override
    public VoiceInteractionSession onNewSession(Bundle args) {
        return new ShaggothAssistSession(this);
    }
}
`
      );

      fs.writeFileSync(
        path.join(javaDir, "ShaggothAssistSession.java"),
        `package ${pkg};

import android.content.Context;
import android.content.Intent;
import android.os.Bundle;
import android.service.voice.VoiceInteractionSession;

public class ShaggothAssistSession extends VoiceInteractionSession {
    public ShaggothAssistSession(Context context) {
        super(context);
    }

    @Override
    public void onShow(Bundle args, int showFlags) {
        super.onShow(args, showFlags);
        Intent intent = new Intent();
        intent.setClassName(
            getContext().getPackageName(),
            getContext().getPackageName() + ".MainActivity"
        );
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        intent.putExtra("assistMode", true);
        getContext().startActivity(intent);
        hide();
    }
}
`
      );

      fs.writeFileSync(
        path.join(xmlDir, "voice_interaction_service.xml"),
        `<?xml version="1.0" encoding="utf-8"?>
<voice-interaction-service xmlns:android="http://schemas.android.com/apk/res/android"
    android:sessionService="${pkg}.ShaggothAssistSessionService"
    android:supportsAssist="true"
    android:supportsLaunchVoiceAssistFromKeyguard="true"
    android:supportsLocalInteraction="true" />
`
      );

      return config;
    },
  ]);
}

module.exports = withAndroidAssistant;
