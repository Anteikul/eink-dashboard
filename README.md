# E‑ink dashboard

Hodiny, počasí a právě přehrávaná skladba na černobílém Waveshare 2.13″ e‑Paper HAT V4. Raspberry Pi Zero 2 W funguje samostatně. Prohlížeč slouží k nastavení a zobrazuje poslední snímek.

## Instalace na Pi

Potřebuješ Raspberry Pi OS (ověřeno na Trixie), síť a připojený displej. Stáhni **Code → Download ZIP**, přenes ZIP na Pi a spusť tam:

```sh
python3 -m zipfile -e eink-dashboard-main.zip .
cd eink-dashboard-main
sh install.sh
```

Případně naklonuj repozitář a spusť `./install.sh` v naklonované složce. Instalátor použije `sudo` pro chybějící balíčky, spustí dashboard a nastaví automatický start po připojení Pi k síti. Složku po instalaci ponech na místě.

Otevři adresu, kterou instalátor vypíše, a v části **Nastavení zařízení** zadej vypsaný kód. Můžeš vyhledat město nebo zadat souřadnice a časové pásmo ručně. Ve webu jde také otočit obraz, vybrat °C/°F a přepnout světlý či tmavý režim. Ztracený kód najdeš ve skrytém souboru `.setup-code` v instalační složce. Web používej ve vlastní místní síti.

### Připojení Spotify

1. Vytvoř aplikaci ve [Spotify Developer Dashboard](https://developer.spotify.com/dashboard). Vyber **Web API** a přidej Redirect URI `http://127.0.0.1:8765/callback`. Spotify pro vlastní aplikaci v režimu Development Mode vyžaduje Premium.
2. Ve webovém nastavení vlož **Client ID** a připrav přihlášení. Otevři odkaz na Spotify a potvrď čtení přehrávání a fronty.
3. Zkopíruj celou adresu, na kterou tě Spotify přesměruje, do pole **Adresa po potvrzení**. Prohlížeč může na adrese 127.0.0.1 zobrazit chybu připojení. Ke zpracování stačí zkopírovaná adresa. Stiskni **Dokončit připojení**.

Hodiny a počasí fungují i bez Spotify. Po připojení účtu Pi samo sleduje přehrávání, připraví obaly ze začátku fronty a ukládá je na disk. Přístup lze ve webu odpojit. [Spotify OAuth](https://developer.spotify.com/documentation/web-api/tutorials/code-pkce-flow)

## Zapojení

HAT můžeš nasadit přímo na 40pinovou lištu. Pro samostatný osmipinový kabel použij toto zapojení s vypnutým Pi. Označení GPIO je v číslování BCM.

| Waveshare | GPIO | Fyzický pin Pi |
|---|---:|---:|
| VCC | 3,3 V | 1 |
| GND | GND | 6 |
| DIN | GPIO 10 | 19 |
| CLK | GPIO 11 | 23 |
| CS | GPIO 8 | 24 |
| DC | GPIO 25 | 22 |
| RST | GPIO 17 | 11 |
| BUSY | GPIO 24 | 18 |

Přenos používá GPIO přes `lgpio`. [Dokumentace Waveshare](https://www.waveshare.com/wiki/2.13inch_e-Paper_HAT_Manual)

## Kontrola běhu

- `tail -f dashboard.log` ukáže start a obnovy displeje.
- `crontab -l` ukáže spouštění po startu.
- `./install.sh --check` ověří dostupnost knihoven bez instalace.
- Pro ruční spuštění použij `./start.sh`. Může běžet jen jedna instance.

Ovladač `waveshare_epd/epd2in13_V4.py` pochází od Waveshare a nese původní licenční text v hlavičce. Data o počasí poskytuje [Open‑Meteo](https://open-meteo.com/).
