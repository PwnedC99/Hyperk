# USB-CDC / HyperSerial am ESP32-S3FH4R2

## Ursache und Umfang

Ausgangszustand: Branch `codex/development`, Commit `978950b3`, sauberer
Arbeitsbaum. Das tatsächlich vorhandene Repository liegt unter
`/Users/a21/Developer/Hyperk`; der ältere Desktop-Pfad existiert nicht mehr.

Die CDC-Hilfssektion hieß `[end:esp32-enable-cdc]`, S3 und weitere Environments
referenzierten dagegen `${env:esp32-enable-cdc.build_flags}`. PlatformIO 6.2.0
meldete dafür keinen harten Fehler, sondern übernahm erneut die allgemeinen
`[env]`-Flags. Im aufgelösten S3-/FH4R2-Profil fehlten die CDC-Flags. Die
Boarddefinition lieferte zwar bereits `ARDUINO_USB_MODE=1`, aber ohne
`ARDUINO_USB_CDC_ON_BOOT=1` verwendet Arduino `Serial0` statt `HWCDCSerial`.
Die S2-Referenz wurde mit dem Abschnittsnamen korrigiert; seine vorhandenen
`build_unflags` und die eigene TinyUSB-Behandlung bleiben erhalten.

Der Entwickler bestätigt den Tippfehler in
[HyperK-Issue #75](https://github.com/awawa-dev/Hyperk/issues/75).

Zusätzlich enthält das gepinnte Backend 0.0.5 in `serial_port.cpp.o` bereits
fest kompilierte Referenzen auf `Serial0` und sechs `HardwareSerial`-Methoden.
Es enthält dort keine `HWCDC`-Referenzen. Neue Compiler-Flags können diese
UART-Aufrufe nicht nachträglich ändern. Ohne Adapter würde die Korrektur der INI
daher die native USB-Datenverarbeitung dieses konkreten Archivs nicht reparieren.
Ein sichtbares `/dev/ttyACM0` allein beweist keinen laufenden Firmware-Empfänger:
USB Serial/JTAG ist ein festes Hardwaregerät und kann sichtbar sein, obwohl
die Anwendung UART0 verarbeitet.

Nur das eigene FH4R2-Profil aktiviert deshalb `HYPERK_USB_SERIAL_BRIDGE` und
zehn Linker-Wrapper. Sie leiten die sechs UART0-Empfangs-/Initialisierungsaufrufe
sowie vier Print-Aufrufe für Handshake/Statistik auf `HWCDCSerial` um. Andere
UART-Instanzen und andere Print-Ziele verwenden ihre ursprünglichen Funktionen.
Das Archiv selbst wird weder umgeschrieben noch ersetzt. Die generischen
Boardprofile erhalten die korrigierten CDC-Referenzen, aber keinen FH4R2-Adapter.

## Untersuchung der Kommunikation

- `setup()` lädt wie bisher die Konfiguration und ruft danach
  `SerialPort::init(Config::getSeriaPortSpeed())` vor LED- und Netzwerkstart auf.
  Im Binärcode aktiviert nur eine von null verschiedene Geschwindigkeit den
  Empfänger. Die vorhandene Einstellung unter **Settings → Network & Serial**
  muss daher weiterhin Serial/HyperSerial aktivieren.
- Das Backend startet für S3 eine eigene `serialPortAwaTask`; der sichtbare
  `loop()` verarbeitet Serial nur auf den anderen Profilen mit `SERIAL_PORT_LITE`.
  Diese Ablaufstruktur bleibt unverändert. Der Adapter wartet nicht auf WLAN.
- Die Binärprüfung zeigt einen angeforderten Empfangspuffer von 2048 Byte und
  einen 4096-Byte-Verarbeitungspuffer. Der Adapter übernimmt die angeforderte
  Empfangsgröße und den bestehenden Stream-Timeout. `readBytes()` verwendet
  den Arduino-Stream-Pfad des USB-Empfängers. Es gibt keinen neuen Frame-Parser.
- AWA-/Adalight-Erkennung, Synchronisierung, Prüfsummen, unvollständige Frames,
  RGBW-Konvertierung und LED-Scheduling bleiben im geschlossenen Backend.
  Eine vollständige Quellcodeprüfung dieser Bereiche ist nicht möglich. Die
  Backend-Symbole enthalten `processData()`, `serialPortAwaTask`, Fletcher- und
  RGB/RGBW-Ausgabeaufrufe; dies ersetzt keinen funktionalen Protokolltest.
- Das geprüfte Arduino-ESP32 3.3.9 verwendet mit `USB_MODE=1` den festen
  Hardware-CDC-/Serial-JTAG-Controller. `USB_MODE=0` würde einen anderen,
  TinyUSB-basierten USB-OTG-/CDC-Pfad wählen. Dieser Wechsel wurde nicht vorgenommen.
- `HWCDC::begin(baud)` benutzt die Baudrate nicht zur USB-Taktung. 2000000 und
  921600 ändern damit nicht die physische USB-Geschwindigkeit. Line-Coding und
  DTR/RTS werden beim Hardware-CDC-Gerät vom Controller behandelt; es werden
  keine zusätzlichen TinyUSB-Control-Callbacks benötigt. Die Wechselwirkung
  mit dem konkreten webOS-Treiber muss am Gerät geprüft werden.
- Im öffentlichen HyperHDR-Quellcode sendet der erzwungene Erkennungspfad ein
  AWA-Kommando, setzt DTR/RTS und sucht nach einer Antwort mit `Awa driver`.
  Er umgeht den expliziten Reset-Zweig. Der Adapter routet auch die dazugehörige
  Backend-Ausgabe auf USB. Die auf dem TV installierte HyperHDR-Version wurde
  nicht ausgelesen oder verändert.
- `ENABLE_DEBUG` bleibt deaktiviert, `CORE_DEBUG_LEVEL` und `LOG_LOCAL_LEVEL`
  bleiben 0. Die normalen Debug-Ausgaben einschließlich der Debug-Startpause
  sind damit ausgeschaltet. Die optionale WiFi-Tuning-Variante kann bei SDK-Fehlern
  weiterhin ihre bisherigen Fehlermeldungen über Serial ausgeben; die hier
  erzeugte Standardfirmware aktiviert diese WiFi-Tuning-Flags nicht.

Primärquellen:
[Arduino-Portauswahl](https://github.com/espressif/arduino-esp32/blob/3.3.9/cores/esp32/HardwareSerial.h),
[Hardware-CDC](https://github.com/espressif/arduino-esp32/blob/3.3.9/cores/esp32/HWCDC.cpp),
[Espressif USB Serial/JTAG](https://docs.espressif.com/projects/esp-idf/en/v5.5.3/esp32s3/api-guides/usb-serial-jtag-console.html),
[HyperHDR AWA-Treiber](https://github.com/awawa-dev/HyperHDR/blob/master/sources/led-drivers/serial/DriverSerialAdalight.cpp),
[HyperHDR Handshake](https://github.com/awawa-dev/HyperHDR/blob/master/include/led-drivers/serial/EspTools.h).

## Änderungen und Schutz bestehender Funktionen

| Datei | Änderung |
| --- | --- |
| `platformio.ini` | CDC-Abschnitt und S2-Referenz korrigiert; USB-Adapter nur im FH4R2-Profil aktiviert. |
| `src/usb_serial_bridge.cpp` | Begrenzte UART0-zu-Hardware-CDC-Umleitung für das vorhandene Backend. |
| `tests/test_usb_config.py` | Prüft die von PlatformIO aufgelöste Vererbung, Referenzen, CDC-Flags und eigenen Boardoptionen. |
| `tests/test_usb_serial_bridge.py` | Prüft Linker-Wrapper, USB-Empfang, Ausgaben, beide Baudwerte und die Weiterleitung anderer UARTs/Print-Ziele. |
| `.github/workflows/build.yml` | Führt den PlatformIO-Konfigurationstest vor den vorhandenen FH4R2-Builds aus. |
| `readme.md` | Verweis auf diesen Bericht und die Installationsschritte. |
| `USB_SERIAL_FIX.md` | Ursachen, Nachweise und Hardware-Prüfplan. |

Unverändert bleiben sämtliche bisherigen Quellen für LED-Treiber, GPIO-Auswahl,
Segmentkonfiguration, RGBW/Farbreihenfolge, GPIO1/NVS, WiFi-Recovery, Weboberfläche
und lokale OTA-Uploads. Die 4-MB-Flashgröße und `partitions_4mb.csv` bleiben gleich.
Die LED-Anzahl und die konkrete Aufteilung der 258 LEDs liegen in der gespeicherten
Gerätekonfiguration; sie wurden nicht aus dem Gerät gelesen und nicht verändert.
Es gab zu Arbeitsbeginn keine uncommitteten Änderungen, die hätten übernommen
werden müssen. Es wurde kein Gerät geflasht und nichts am TV verändert.

## Build und automatische Validierung

Verwendetes Environment: `esp32s3-fh4r2`, mit Arduino-ESP32 3.3.9, ESP-IDF 5.5.4,
PlatformIO 6.2.0 und der bestehenden Plattform `55.03.39`.

Reproduktion nach Installation von `requirements-build.txt`:

```sh
python -m unittest discover -s tests -p 'test_*.py'
python scripts/check_backend_ui.py --output /tmp/hyperk-ui
HYPERK_BACKEND_FIXTURES=/tmp/hyperk-ui npm test
pio run -e esp32s3-fh4r2 -t clean
pio run -e esp32s3-fh4r2
```

Der USB-Konfigurationstest benötigt PlatformIO. Ohne dieses Python-Modul wird
nur dieser Test übersprungen; im CI-Build läuft er nach der Werkzeuginstallation
verpflichtend mit PlatformIO. Der neue C++-Adapter verweigert zusätzlich die
Kompilierung bei fehlenden CDC-Flags oder falschem Zielchip.

Lokale Ergebnisse am 8. November 2026:

- Vollständiger Firmware-Build erfolgreich, einschließlich OTA-/Factory-Image
  und Manifest. Keine Compiler-Warnungen im erfolgreichen Buildlauf.
- 15 Python-Tests bestanden, keine übersprungen; 18 Browser-Tests bestanden.
- Der neue Konfigurationstest schlug vor der INI-Korrektur erwartungsgemäß fehl.
- Die tatsächlichen Compilerbefehle wurden über `pio run -t compiledb` geprüft.
  Präprozessierung mit demselben ESP32-Compiler und denselben Optionen ergab:

  ```c
  #define ARDUINO_USB_CDC_ON_BOOT 1
  #define ARDUINO_USB_MODE 1
  #define CONFIG_IDF_TARGET_ESP32S3 1
  #define Serial HWCDCSerial
  ```

- `ARDUINO_USB_MODE=1` kommt identisch aus Boarddefinition und Buildprofil;
  es gibt keine widersprüchliche Überschreibung.
- Das finale ELF enthält `HWCDCSerial` und alle zehn Wrapper. Die Disassemblierung
  von `SerialPort::init()` zeigt Aufrufe der RX-Puffer-/Begin-Wrapper; der
  Empfangspfad ruft die Available-/ReadBytes-Wrapper auf. Der Begin-Wrapper
  verzweigt für `Serial0` tatsächlich zu `HWCDC::begin()`.
- RAM: 50696 / 327680 Byte (15,5 %). Flash: 1222929 / 1900544 Byte (64,3 %).
- Backend-SHA-256 unverändert:
  `4b36e800804c5b63df8a2ce9ca6938e45056e894d4f79289ffee13fb7e201a6e`.
- Ein erster Lauf mit `pio run -v` scheiterte nach erfolgreichem Linken an
  einem SCons-Formatierungsfehler (`_Null` plus `str`). Der anschließende normale
  vollständige Build war erfolgreich; keine Abhängigkeit wurde dafür geändert.

Erzeugte Dateien in `release/`:

- `OTA_Hyperk_0.0.5_esp32s3-fh4r2_978950b3-dirty-6be825d0f1.bin`
  (1223328 Byte), SHA-256:
  `3e3e89ea4edb51c324c1d1770b32ab0266bc75ec471318238a0446b6f6ff0d74`.
- `Hyperk_0.0.5_esp32s3-fh4r2_978950b3-dirty-6be825d0f1_factory.bin`
  (1288864 Byte), SHA-256:
  `659bca57f5c02faa398654fef37aa26379830039f73d560790424af88918e076`.
- `Hyperk_0.0.5_esp32s3-fh4r2_978950b3-dirty-6be825d0f1.json`:
  Buildoptionen und erfolgreich geprüfte Artefakt-Hashes.

Die oben genannten Artefakte wurden vor dem Commit gebaut; `dirty` in der
Build-ID beschreibt den Quellzustand zum Buildzeitpunkt. Die in `.pio/build/esp32s3-fh4r2/` erzeugte
`Hyperk_0.0.5.bin` ist dasselbe reine Anwendungsimage wie die OTA-Datei.

## Installation unter Erhalt der Einstellungen

Diese Schritte sind ausschließlich eine Anleitung. Es wurde kein serieller
Gerätezugriff und kein Hardware-Reset ausgeführt.

### OTA bei erreichbarer Weboberfläche

Unter **Settings → Firmware Update (OTA) → Lokale Firmware installieren** die
oben genannte `OTA_...bin` auswählen. Die vorhandene lokale OTA-Funktion schreibt
nur den inaktiven Anwendungsslot und aktualisiert anschließend die Bootauswahl.
Partitionstabelle, NVS und Dateisystem bleiben erhalten, sofern das Gerät dieselbe
Partitionierung besitzt. Nicht den Stable-/Testing-Download verwenden, da dieser
die offizielle Firmware statt des eigenen Builds lädt. Bei defektem WLAN ist
OTA nicht möglich; dann den nachfolgenden USB-Weg am Computer verwenden.

### Kabelgebunden am Computer

HyperHDR bzw. andere Programme mit geöffnetem Port vor dem manuellen Flash schließen.
Den ESP32-S3 am Computer anschließen und dessen Port statt des TV-Pfads verwenden
(z. B. `/dev/cu.usbmodem...` unter macOS oder `COM...` unter Windows).
Falls erforderlich, das Board manuell über BOOT/RESET in den Downloadmodus bringen.

Zuerst ein vollständiges Backup und die vorhandene Partitionstabelle lesen:

```sh
python -m esptool --chip esp32s3 --port PORT read-flash 0x0 0x400000 hyperk-backup.bin
python -m esptool --chip esp32s3 --port PORT read-flash 0x8000 0x1000 hyperk-partitions.bin
python /PATH/TO/ARDUINO_CORE/tools/gen_esp32part.py hyperk-partitions.bin
```

`gen_esp32part.py` ist im Arduino-ESP32-Paket der PlatformIO-Installation enthalten.
Vor dem Schreiben muss die gelesene Tabelle dieselben Anwendungsbereiche zeigen:
`app0` ab `0x10000`, `app1` ab `0x1E0000`, jeweils Größe `0x1D0000`.
NVS liegt ab `0x9000`, das Dateisystem ab `0x3B0000`. Bei abweichender Tabelle
keinen dieser Offsets ungeprüft verwenden.

Bei bestätigter Tabelle lässt sich ausschließlich das Anwendungsimage in beide
Anwendungsslots schreiben. Dadurch muss die bestehende OTA-Bootauswahl nicht
gelöscht oder verändert werden; unabhängig vom ausgewählten Slot startet das
neue Image. Die vorherige Firmware wird dabei in beiden Slots ersetzt.

```sh
python -m esptool --chip esp32s3 --port PORT write-flash 0x10000 release/OTA_Hyperk_0.0.5_esp32s3-fh4r2_978950b3-dirty-6be825d0f1.bin 0x1E0000 release/OTA_Hyperk_0.0.5_esp32s3-fh4r2_978950b3-dirty-6be825d0f1.bin
```

Bootloader, Partitionstabelle, OTA-Auswahl, NVS und Dateisystem werden von diesem
Befehl nicht beschrieben. Es wird kein `erase-flash` benötigt. Das kombinierte
`_factory.bin` ist für diese einstellungserhaltende Installation ungeeignet,
weil sein zusammenhängender Flashbereich auch die Konfigurationsbereiche abdeckt.
Wer nur einen App-Slot ersetzen möchte, muss vorher die aktuelle Bootauswahl
bestimmen; nach einem früheren OTA-Update ist nicht zwingend `app0` aktiv.

Zum Hintergrund: [Espressif OTA-/Partitionsdokumentation](https://docs.espressif.com/projects/esp-idf/en/v5.5.3/esp32s3/api-reference/system/ota.html).

## Hardware-Abnahme: vollständig offen

Erst nach manueller Installation am echten Gerät prüfen:

1. Zuverlässiger Start und erhaltene HyperK-Einstellungen einschließlich GPIO1.
2. Native USB-Erkennung und `/dev/ttyACM0` auf dem LG-TV.
3. HyperHDR: Adalight, Port `/dev/ttyACM0`, 2000000 Baud, AWA aktiviert,
   ESP32 Handshake aktiviert, Force HyperSerial Detection aktiviert.
4. Erfolgreiche HyperSerial-Erkennung und vollständige Farbframes ohne
   `Timeout writing to ttyACM0`.
5. Beide bisherigen LED-Ausgänge, Segmentgrenzen, alle 258 SK6812-RGBW-LEDs
   und unveränderte Farbkanal-Reihenfolge mit einfarbigen Testbildern prüfen.
6. Kontinuierliche PicCap-Bildübertragung und stabiles Öffnen/Schließen des Ports
   prüfen, anschließend denselben Test mit 921600 Baud wiederholen.
7. Betrieb ohne funktionierendes WLAN und USB-Trennen/Wiederverbinden prüfen.

Keiner dieser Hardwarepunkte ist durch Quellcodeprüfung, Build, Host-Tests oder
den Nachweis gelinkter Symbole als bestanden nachgewiesen.
