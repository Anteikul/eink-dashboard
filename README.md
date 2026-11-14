# E‑ink dashboard

A clock, weather, and the currently playing track on a black-and-white Waveshare 2.13″ e‑Paper HAT V4. The Raspberry Pi Zero 2 W runs on its own. The browser shows the latest frame and handles all dashboard settings.

## Install on a Raspberry Pi

Connect the e-paper display and boot Raspberry Pi OS with Wi-Fi and SSH configured in Imager. Sign in to the Pi over SSH, then paste this block into the Pi terminal from your regular user account.

```sh
cd "$HOME" &&
  wget -O eink-dashboard-main.zip https://github.com/Anteikul/eink-dashboard/archive/refs/heads/main.zip &&
  python3 -m zipfile -e eink-dashboard-main.zip . &&
  sh eink-dashboard-main/install.sh
```

The installer uses `sudo` for missing packages and enables startup on boot. Leave the installation folder in place. For an older installation without **Updates** in Settings, install the current version in the existing folder and restart the Pi once.

Open the address printed by the installer, such as `http://192.168.1.25/`, from a device on your local network. The page shows the last frame and connection status. The controls beside or below the preview let you choose **Automatic**, **Dashboard**, or **Playback**, and a light or dark theme. Automatic mode follows Spotify when automatic switching is enabled. Playback mode keeps the playback layout visible while Spotify is idle. The Pi remembers the selected mode after a restart.

Open **Saved layouts** below the theme controls to choose which design Dashboard and Playback each use. **Display mode** controls which screen is shown. Sign in with the device setup code if the web password is enabled.

The gear opens **Settings** at `/settings`, where you can choose English or Czech. If prompted, enter the setup code printed by the installer. Use the section links to jump to the setting you need. **Save configuration** applies the pending changes to language, display, location and weather, playback, Wi-Fi setup, and the local address together. In **Web password**, you can change the code or let anyone who can reach the web interface open the settings and editor. Turn the password requirement back on to use the current code again. To recover the code, run `cat ~/eink-dashboard-main/.setup-code` on the Pi.

Under **Display**, choose a rotation of 0°, 90°, 180°, or 270°. The canvas dimensions follow the orientation automatically. The default canvas is 250 × 122 px in landscape and 122 × 250 px in portrait.

Opening Settings checks the repository's `main` branch on GitHub. When a newer version is available, select **Update** to download it and restart the dashboard. If the new version cannot start, the Pi returns to the previous version. Device settings, Wi-Fi, Spotify credentials, and saved layouts stay in the installation folder. **Check for updates** runs the check again. Use `install.sh` for system packages and the optional Wi-Fi helper.

You can also open `http://eink.local/` on the same network. To change the name or turn it off, open **Local address** in Settings. If you change or disable the name while using it, Settings reopens at the Pi's IP address. The setup hotspot uses the address shown on the e-paper display.

### Build your own screens

Open the pencil in the dashboard header to visit the full-page editor. One sign-in with the device setup code unlocks the editor and Settings in the same browser. The **Dashboard** and **Playback** tabs have separate layouts. Drag an icon onto the canvas, or click it to add the widget. Drag a layer to move it and pull a corner to resize its visible contents. Hold **Shift** to change width and height independently. **Snap** uses the visible edges and centers of layers. The inspector shows their exact positions and sizes in display pixels.

- Choose a clock display style and time format separately. Digital clocks can show digits side by side or stacked, with 12-hour or 24-hour time, seconds, or a custom pattern such as `HH.mm.ss` or `h:mm A`. The analog face uses hands. Use brackets for literal text, as in `[Time] HH:mm`. You can also add your own text or a divider.
- Dates include localized weekday and month names, ISO, dotted and slash formats, or a custom pattern such as `[Today] dddd, D MMMM YYYY`.
- Import photos from the widget palette or drop a file onto the canvas. JPEG, PNG, HEIC/HEIF, WebP, GIF, BMP and TIFF are supported up to 16 MB. The photo appears on the canvas in black and white. Select it and click **Crop** in the center toolbar to adjust the frame. Click **Crop** again or click outside the photo to apply the crop. You can reopen it later.
- Weather can show only the icon, only the temperature, or both side by side or stacked.
- Playback can show album art, track and artist text, a progress indicator, or elapsed and remaining time.

Use **Draw** to sketch freehand with a mouse, pen, or finger. Each pen stroke creates its own layer. The eraser clears pixels from both drawings and widgets. Drag layers in the **Layers** panel to reorder them. The top row is frontmost. In **Select** mode, drag from an empty part of the canvas to select several layers, then move, align, or delete them together. Double-click custom text to edit it on the canvas. Press **Enter** to finish editing or **Shift+Enter** for a new line. Use **Ctrl+Z** and **Ctrl+Shift+Z** for undo and redo, or **⌘Z** and **⌘Shift+Z** on Mac.

The canvas uses sample data and the same widget renderer as the display. Set its width and height under **Display**. Under **Location and weather**, choose a city from the suggestions to fill its coordinates and time zone. The 250 × 122 panel scales the canvas to fit without stretching it. Saved designs retain their original canvas dimensions. Use the save icon to apply the current screen on the Pi. **Start blank** clears the current draft and **Reset to default** restores the built-in screen when applied.

The folder icon opens the layout library for the current screen. Save the canvas under a name to keep a reusable copy on the Pi. The list shows a thumbnail and the save date for each design. Click a design to see it on the canvas. The locked **Default layout** entry restores the built-in screen. Use **Apply to display** to put the current layout on the e-paper screen.

### Join a new Wi-Fi network

Run `sh install.sh --wifi-setup` to enable or update the optional Wi-Fi setup feature. This installs a system service that can configure the Pi's built-in `wlan0` interface. The dashboard account can request the two supported Wi-Fi operations through a private local socket.

When the Pi has no saved Wi-Fi connection available, it starts a temporary hotspot after the delay set under **Wi-Fi setup**. The default is 30 seconds. The e-paper screen shows a Wi-Fi icon, the hotspot name, an eight-character password, and the address `http://10.42.0.1/`. To use the same password each time, store your own eight digits in `.hotspot-password` in the installation directory, set the file permissions to `600`, and restart the Pi.

1. On your phone, join the **EinkSetup** network shown on the display. Stay connected if the phone says the network has no internet.
2. Open `http://10.42.0.1/` and enter the name and password of the 2.4 GHz network the Pi should join. Leave the password empty for an open network.
3. The hotspot closes while the Pi tries the new network. If it connects, the Pi saves the network for future boots and displays its new address with a 15-second countdown. If it fails, reconnect to the same hotspot with the same password and try again.

While the setup hotspot is active, restart the Pi to give its saved networks another automatic try.

### Connect Spotify

1. Create an app in the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard). Select **Web API** and add `http://127.0.0.1:8765/callback` as a redirect URI. Spotify requires Premium for your own app in Development Mode.
2. Enter your **Client ID** in the dashboard and select **Prepare sign-in**. Open Spotify from the link and approve access to playback and the queue.
3. Copy the full URL from the browser's address bar after Spotify redirects you. Paste it into **Redirect URL** and select **Finish connecting**. The browser may show a connection error at 127.0.0.1. The address bar still contains the information needed to finish setup.

The clock and weather work without Spotify. Once connected, the Pi checks playback, prepares covers for upcoming tracks, and caches them on disk. Settings shows a check mark next to Spotify after a successful API request. Hover over it to see **Spotify connected**. You can repeat the check or disconnect the account there. [Spotify OAuth](https://developer.spotify.com/documentation/web-api/tutorials/code-pkce-flow)

## Wiring

Fit the HAT directly onto the Pi's 40-pin header, or use the included eight-wire cable and the table below. Power off the Pi before wiring. GPIO numbers use BCM numbering.

| Waveshare | GPIO | Physical Pi pin |
|---|---:|---:|
| VCC | 3.3 V | 1 |
| GND | GND | 6 |
| DIN | GPIO 10 | 19 |
| CLK | GPIO 11 | 23 |
| CS | GPIO 8 | 24 |
| DC | GPIO 25 | 22 |
| RST | GPIO 17 | 11 |
| BUSY | GPIO 24 | 18 |

The display driver uses `lgpio`. [Waveshare documentation](https://www.waveshare.com/wiki/2.13inch_e-Paper_HAT_Manual)

## Check the dashboard

- `tail -f dashboard.log` shows startup and display updates.
- `crontab -l` shows the startup entry.
- `./install.sh --check` checks for the required tools and libraries.
- `./start.sh` launches the dashboard manually. Only one instance can use the display at a time.

The driver in `waveshare_epd/epd2in13_V4.py` comes from Waveshare and retains its license notice. Weather data comes from [Open‑Meteo](https://open-meteo.com/).
