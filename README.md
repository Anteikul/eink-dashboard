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

The installer uses `sudo` for missing packages and enables startup on boot. Leave the installation folder in place. To update a ZIP installation, rerun the same block in the same account and restart the Pi. If you cloned the repository, update and run `sh install.sh` in that checkout.

Open the address printed by the installer, such as `http://192.168.1.25/`, from a device on your local network. Light and dark themes are below the preview. Use the gear to choose English or Czech. Unlock **Device setup** with the code printed by the installer to change location, time zone, temperature units, rotation, Spotify access, or the setup code itself. To recover the current code, run `cat ~/eink-dashboard-main/.setup-code` on the Pi.

### Join a new Wi-Fi network

Run `sh install.sh --wifi-setup` to enable or update the optional Wi-Fi setup feature. This installs a system service that can configure the Pi's built-in `wlan0` interface. The dashboard account can request the two supported Wi-Fi operations through a private local socket.

When the Pi has no saved Wi-Fi connection available for about 30 seconds, it starts a temporary hotspot. The e-paper screen shows a Wi-Fi icon, the hotspot name, an eight-character password, and the address `http://10.42.0.1/`. To use the same password each time, store your own eight digits in `.hotspot-password` in the installation directory, set the file permissions to `600`, and restart the Pi.

1. On your phone, join the **EinkSetup** network shown on the display. Stay connected if the phone says the network has no internet.
2. Open `http://10.42.0.1/` and enter the name and password of the 2.4 GHz network the Pi should join. Leave the password empty for an open network.
3. The hotspot closes while the Pi tries the new network. If it connects, the Pi saves the network for future boots and displays its new address with a 15-second countdown. If it fails, reconnect to the same hotspot with the same password and try again.

While the setup hotspot is active, restart the Pi to give its saved networks another automatic try.

### Connect Spotify

1. Create an app in the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard). Select **Web API** and add `http://127.0.0.1:8765/callback` as a redirect URI. Spotify requires Premium for your own app in Development Mode.
2. Enter your **Client ID** in the dashboard and select **Prepare sign-in**. Open Spotify from the link and approve access to playback and the queue.
3. Copy the full URL from the browser's address bar after Spotify redirects you. Paste it into **Redirect URL** and select **Finish connecting**. The browser may show a connection error at 127.0.0.1. The address bar still contains the information needed to finish setup.

The clock and weather work without Spotify. Once connected, the Pi checks playback, prepares covers for upcoming tracks, and caches them on disk. You can disconnect the account in the browser. [Spotify OAuth](https://developer.spotify.com/documentation/web-api/tutorials/code-pkce-flow)

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
