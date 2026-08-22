package dev.jarvisos.wearableprobe;

import android.app.Activity;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.Gravity;
import android.widget.TextView;

import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class MainActivity extends Activity {
    private static final String WEARABLE_ID = "pixel_watch_probe";
    private static final long HEARTBEAT_INTERVAL_MS = 5000L;

    private final Handler handler = new Handler(Looper.getMainLooper());
    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private TextView statusView;
    private boolean active;

    private final Runnable heartbeat = new Runnable() {
        @Override
        public void run() {
            if (!active) {
                return;
            }
            sendHeartbeat("connected");
            handler.postDelayed(this, HEARTBEAT_INTERVAL_MS);
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        statusView = new TextView(this);
        statusView.setGravity(Gravity.CENTER);
        statusView.setText("idle");
        setContentView(statusView);
    }

    @Override
    protected void onResume() {
        super.onResume();
        active = true;
        statusView.setText("sending");
        heartbeat.run();
    }

    @Override
    protected void onPause() {
        active = false;
        handler.removeCallbacks(heartbeat);
        sendHeartbeat("disconnected");
        super.onPause();
    }

    @Override
    protected void onDestroy() {
        active = false;
        handler.removeCallbacks(heartbeat);
        executor.shutdownNow();
        super.onDestroy();
    }

    private void sendHeartbeat(String state) {
        executor.execute(() -> {
            boolean success = postState(state);
            runOnUiThread(() -> statusView.setText(success ? state : "error"));
        });
    }

    private boolean postState(String state) {
        HttpURLConnection connection = null;
        try {
            URL url = new URL(BuildConfig.RECEIVER_URL);
            byte[] body = ("{\"state\":\"" + state + "\",\"wearable_id\":\"" + WEARABLE_ID + "\"}")
                    .getBytes(StandardCharsets.UTF_8);
            connection = (HttpURLConnection) url.openConnection();
            connection.setRequestMethod("POST");
            connection.setConnectTimeout(3000);
            connection.setReadTimeout(3000);
            connection.setDoOutput(true);
            connection.setRequestProperty("Content-Type", "application/json");
            connection.setRequestProperty("Content-Length", Integer.toString(body.length));
            try (OutputStream output = connection.getOutputStream()) {
                output.write(body);
            }
            int responseCode = connection.getResponseCode();
            return responseCode >= 200 && responseCode < 300;
        } catch (Exception ignored) {
            return false;
        } finally {
            if (connection != null) {
                connection.disconnect();
            }
        }
    }
}
