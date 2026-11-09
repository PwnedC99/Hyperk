# HyperK FH4R2: Speicherung und „Load failed“, 08.11.2026

## Ergebnis und Grenzen

Im neuesten Commit `248b327` ist ein eigenständiger Speicherfehler nachgewiesen:
`validFile()` prüft `doc["numLeds"]`. Das tatsächlich vom Backend erzeugte
Dateiformat enthält diesen Wert unter `doc["led"]["numLeds"]`. Deshalb lehnt
der Wrapper gültige vorhandene Dateien beim Start und gültige neue Dateien vor
dem Übernehmen ab. Das erklärt fehlende Übernahme und Setup mit Standardwerten.
Die alten Tests enthielten denselben Schemafehler und konnten ihn nicht erkennen.

Zusätzlich stellt der veröffentlichte Stand weiterhin nur 4096 Byte für den
AsyncTCP-Task bereit. Die bereits lokal vorhandene Erhöhung auf 16384 Byte war
nie Bestandteil dieser Commits. Die frühere reale Messung mit 299 LEDs zeigte
einen Panic-Reset beim Speichern mit 4096 Byte und erfolgreiche Speicherung samt
Neustart mit 16384 Byte. Diese Beobachtung ist ein starker Beleg für den früheren
Absturzpfad, aber kein Beweis für die konkrete Ursache jedes jetzigen
Verbindungsabbruchs bei 258 LEDs.

„Load failed“ ist eine Browser-Netzwerkausnahme: Die Antwort konnte nicht
vollständig empfangen werden. Daraus lässt sich allein weder ein gescheiterter
Flash-Schreibvorgang noch dessen Erfolg ableiten. Ein regulär zurückgegebener
Schemafehler würde hier HTTP 503 mit `written_config_invalid` liefern. Ohne
aktuelle USB-Logs bleibt offen, ob der gemeldete Abbruch durch einen Panic,
Verbindungsverlust oder einen anderen Transportfehler ausgelöst wurde.

**Geräterückmeldung vom 09.11.2026:** Der Nutzer bestätigt, dass die neue
17-dBm-Version `248b3271-dirty-42ee122df8` die gemeldeten Fehler behoben hat.
Dies ist eine Bestätigung am echten ESP. Ein detailliertes Protokoll aller
Einzeltests zu stromlosem Neustart, WLAN, SPI/RMT-Wechsel und Dauerbetrieb liegt
weiterhin nicht vor. Während dieser Untersuchung wurde durch den Assistenten
kein Gerät automatisch geflasht, zurückgesetzt oder gelöscht.

## A. Git-Analyse

Der lokale Branch `codex/development` stand zunächst auf `978950b`. Nach Fetch
wurde er ohne Merge-Commit auf den gemeldeten aktuellen Stand `248b327`
vorgezogen. Die vorhandenen Änderungen an `platformio.ini` und `readme.md`
wurden vorher gesichert und anschließend konfliktfrei wiederhergestellt.
Das vorhandene eigenständige Projekt `diagnostics/led-test/` blieb erhalten.

| Stand | Relevante Änderung |
| --- | --- |
| `f83984b` | Upstream 0.0.5; direktes Schreiben von `/config.json`, automatische Formatierung bei Ladefehlern, 4-KB-HTTP-Stack bereits vorhanden. |
| `899af1c` | FH4R2-Profil, GPIO37/38-UI, GPIO1/Preferences, WLAN-Wiederherstellung und feste Backend-Prüfsumme; keine Reparatur des nativen Speicherns. |
| `3f22e47` | Beschränkt CI auf FH4R2; keine Speicheränderung. |
| `978950b` | Lokaler OTA-Upload und Einbindung/Stil der Peripherie; kein Entfernen der Persistenz. |
| `3300c2c` | Korrigierte CDC-Profilreferenz und UART0→Native-USB-Brücke für das vorkompilierte HyperSerial-Backend. |
| `248b327` | Speicher-Wrapper, temporäre Datei, Fehler-Middleware, neue GUI-Meldung; falscher JSON-Pfad blockiert jede gültige Konfiguration. Stack bleibt 4 KB. |

Untersucht wurden die Commit-Diffs, `git blame`, das fixierte Backend-Archiv,
dessen Symbole und Disassembly sowie die unveränderten eingebetteten GUI-Assets.
Ein automatisches Hardware-Bisect wurde mangels aktuell ausführbarem Gerätetest
nicht vorgetäuscht. Der letzte Fix hat Speicheraufrufe nicht entfernt: Er ruft
sie auf, lehnt danach aber die korrekt aufgebaute Datei ab und blockiert
Neustart/Apply. Beim Start blockiert er außerdem das Laden vorhandener Dateien.

## B. Vollständiger Konfigurationspfad und Belege

### GUI und HTTP

Die ursprünglichen Backend-Assets verwenden POST-Formulardaten an
`/save_config` und `/save_wifi`, kein JSON im Request-Body. Die Erweiterung in
`data/board_controls.js` verwendet weiterhin `URLSearchParams(FormData)`.
Das WLAN-Feld heißt tatsächlich `pass`. Segmentdaten werden als CSV
`start,data,clock,reversed,...` übertragen. Die Formularprüfung und die
Segmentserialisierung bleiben erhalten. JSON-Requests an diese Endpunkte werden
jetzt ausdrücklich mit HTTP 415 abgelehnt.

`/api/get_current_config` liefert dagegen `{ "config": { ... } }` mit flachen
GUI-Feldern wie `numLeds`, `brightness`, `disableSpiEmulation` und `ssid`.
Diese API-Struktur ist **nicht** das Dateiformat. Das gespeicherte JSON hat
unter anderem `led.numLeds`, `led.brightness`, `wifi` und
`quirks.disableSpiEmulation`. Genau diese Unterscheidung fehlte im letzten Test.
`tests/fixtures/config_0_0_5.json` bildet das echte Dateiformat mit erfundenen
Beispiel-Zugangsdaten, 258 RGBW-LEDs und GPIO37/38 ab. Private Gerätesicherungen
wurden weder in Tests kopiert noch veröffentlicht.

### Backend und Persistenz

Der eigentliche Backend-Quellcode ist in diesem Checkout nicht vorhanden.
Er liegt unverändert als `export_backend/precompiled/0.0.5/esp32s3/libBackend_esp32s3.a`
vor. SHA-256:
`4b36e800804c5b63df8a2ce9ca6938e45056e894d4f79289ffee13fb7e201a6e`.
Die Reparatur arbeitet wie der letzte Commit über überprüfte Linker-Wrapper.
Es wurde kein fremdes Backend und kein Bibliotheksupdate übernommen.

Anhand des Archivs nachgewiesen:

- `Config::saveConfig()` aktualisiert die interne RAM-Konfiguration vor dem
  Aufruf von `Storage::saveConfig()`.
- `Storage::saveConfig()` öffnet `/config.json` mit `w`, serialisiert, führt
  Flush/Close aus, prüft jedoch nicht die geschriebene Länge oder einen Readback.
  Der Rückgabewert beruht auf dem erfolgreichen Öffnen der Datei.
- Der normale HTTP-Speicherhandler wertet den booleschen Speicherfehler nicht
  aus, sondern antwortet und plant Apply bzw. Neustart.
- Der native Lader formatiert bei JSON-Deserialisierungsfehlern das Dateisystem
  und schreibt Defaults. Der Wrapper verhindert diesen Pfad beim Laden.
- Der neueste Wrapper verlangt fälschlich das flache Feld `numLeds`, obwohl
  die echte gespeicherte Datei `led.numLeds` enthält. Dieser Fehler betrifft
  WLAN und alle anderen Einstellungen gleichermaßen, unabhängig vom Treiber.

Der korrigierte Pfad lautet:

1. Request-Middleware nimmt die Konfigurationssperre und prüft GPIO1 sowie den
   Request-Typ. Das Backend verarbeitet die ursprünglichen Formulardaten.
2. Das Backend aktualisiert RAM und schreibt durch die Dateiumleitung
   `/config.pending.json`.
3. Zusätzlich zu dessen Flush/Close wird `fsync` mit geprüftem Rückgabewert
   ausgeführt. Auch Fehler beim Öffnen/Schließen dieses Deskriptors scheitern.
4. Die geschlossene Datei wird erneut gelesen: JSON, vollständiges Dateiende,
   korrektes Schema, LED-Anzahl/-Typ, geordnete Segmentgrenzen und Datenpins.
5. Eine vorhandene gültige aktuelle Datei wird bytegenau geprüft als
   `/config.previous.json` gesichert. Erst dann ersetzt Rename die aktuelle
   Datei. Anschließend folgt eine weitere Prüfung der übernommenen Datei.
6. Erst jetzt gilt die Speicherung als erfolgreich. Bei Fehlern wird eine
   vorhandene gültige Konfiguration zurück in den RAM geladen; Apply und
   neu angeforderter Neustart werden unterdrückt; die Middleware ersetzt die
   ursprüngliche Erfolgsmeldung vor dem tatsächlichen Senden durch HTTP 503.
7. Beim Start wird ein beschädigtes/fehlendes aktuelles JSON aus der gültigen
   vorherigen Datei wiederhergestellt. Ohne solche Datei bleiben beschädigte
   Inhalte erhalten und die LED-Initialisierung wird nicht ausgeführt.
8. Das erneute Laden nach Neustart sowie die API-Anzeige sind zusätzliche,
   getrennt zu prüfende Schritte. Ein HTTP 200 allein beweist diese nicht.

LittleFS dokumentiert atomare Rename-Operationen auch bei Stromausfall:
[LittleFS-Projekt](https://github.com/littlefs-project/littlefs).
Die vorherige Datei ist eine **zuletzt gültig gespeicherte** Konfiguration;
sie ist noch keine auf echter LED-Hardware bestätigte Funktionsgarantie.

### Partitionen, LittleFS und NVS

`partitions_4mb.csv` blieb unverändert:

| Partition | Adresse | Größe |
| --- | --- | --- |
| NVS | `0x9000` | `0x5000` |
| OTA-Auswahl | `0xE000` | `0x2000` |
| app0 | `0x10000` | `0x1D0000` |
| app1 | `0x1E0000` | `0x1D0000` |
| spiffs / LittleFS | `0x3B0000` | `0x50000` (320 KiB) |

Der Partitionsname `spiffs` ist hier auch für LittleFS vorgesehen und kein
Beweis eines falschen Dateisystems. Die Hauptkonfiguration ist LittleFS-JSON,
kein NVS-Blob. Nur der zusätzliche GPIO1-Zustand verwendet separat Preferences
mit Namespace `hyperk-board`. Dessen Initialisierungs-/Schreibergebnisse werden
bereits geprüft. Beide App-Images und die Bootloader-Abbilder verwenden 4 MB;
die allgemeine PlatformIO-Boardbeschreibung nennt weiterhin 8 MB, der
projektspezifische Upload-/Image-Wert überschreibt dies auf 4 MB.

Im FH4R2-Pfad wird `LittleFS.begin(false)` verwendet. Nur wenn die gesamte
Datenpartition nachweislich ausschließlich `0xff` enthält, wird ein neues
Dateisystem angelegt. Ein anderweitiger Mount-Fehler formatiert nichts.
Die zusätzliche Formatierung des nativen JSON-Laders wird weiter abgefangen.
Mount-Resultat und Partitionsgröße sind über USB diagnostizierbar; freier Heap,
größter Block und Task-Stackreserve stehen in jeder Diagnosezeile. Ein realer
Flashdefekt oder tatsächliche Speichererschöpfung des jetzigen Geräts ist
ohne Messung nicht nachgewiesen.

### WLAN und LED-Treiber

Gespeicherte Credentials werden beim Start über `Config::getWifiCredentials()`
geladen. Nur bei vorhandenen Credentials beginnt `WiFi.begin()`. Nach
12 Sekunden ohne Verbindung startet der Setup-AP; die vorhandene Recovery-Logik
versucht später erneut STA und lässt einen verbundenen Setup-Client bestehen.
Ein AP-Fallback beweist deshalb keinen Speicherfehler. Das falsche Schema in
`248b327` kann allerdings bereits davor das Laden der Credentials verhindern.
Neue Logs unterscheiden Startversuch, numerische Events, Disconnect-Grund,
AP-Start und AP-Abschaltung. SSID/Passwort werden dabei nicht ausgegeben.

`Leds::applyLedConfig()` wird beim Boot vor WLAN ausgeführt und später über
Manager-Ereignisse aufgerufen. Im Backend erkennbar sind Renderer-Warten,
Freigabe bestehender Ressourcen/Sync-Manager und neue SPI-/RMT-Initialisierung.
Dass eine bestimmte DMA-/RMT-Ressource den früheren Panic verursacht hat, ist
dadurch **nicht bewiesen**. Der allgemeine Schemafehler ist unabhängig davon.

Der neue Guard serialisiert LED-Neuinitialisierung gegen Konfigurationsrequests.
Backend-Neustarts warten ebenfalls auf dieselbe Sperre, damit ein bereits
fälliger Neustart nicht mitten in einen weiteren Speichervorgang fällt.
Vor der Initialisierung wird ein synchronisierter Marker geschrieben. Bleibt
er nach Panic, Watchdog oder Stromausfall bestehen, wird beim nächsten Start
die LED-Initialisierung übersprungen, damit WLAN/Web zur Korrektur starten kann.
Auch zurückgegebene SPI-/RMT-/Sync-Manager-Fehler lassen den Marker bestehen.
Ein erfolgreiches erneutes Speichern erlaubt einen weiteren Initialisierungsversuch.
Eine Stromunterbrechung genau während einer eigentlich funktionierenden
Initialisierung kann daher vorsorglich ebenfalls diesen Modus auslösen.

Die Treiberbibliothek, Pins und bestehende RGBW-Konfiguration werden nicht
umgestellt. SPI bleibt der Referenzzustand; es wird kein RMT erzwungen.
Die unbekannten internen Renderer-Lebensdauern des vorkompilierten Backends
werden nicht durch spekulative Pointer-/DMA-Änderungen ersetzt. Ein sicherer
realer SPI/RMT-Wechsel und seine Last unter HyperSerial bleiben Hardwaretests.

## C. Geänderte Dateien

| Datei/Funktion | Zweck |
| --- | --- |
| `src/config_store.cpp`: `validFile`, Save-/Load-Wrapper | Schema korrigieren, Semantik prüfen, Sicherung/Wiederherstellung und öffentliche Prüfsumme. |
| `src/config_store_sync.cpp`: `syncFile` | Geprüfte `open`-/`fsync`-/`close`-Rückgaben statt stiller Flush-Fehler. |
| `include/config_store.h` | Kleine Diagnose-, Sperr- und LED-Guard-Schnittstelle. |
| `src/led_init_guard.cpp` | Boot-Marker, gegenseitiger Ausschluss sowie SPI/RMT/Sync-Rückgabecodes; keine Änderung der Treiberauswahl. |
| `include/config_diagnostics.h`, `src/config_diagnostics.cpp` | Begrenzter RAM-Logpuffer und USB-Ausgabe ausschließlich in Diagnose-Builds. |
| `src/main.cpp`, `src/board_api.cpp` | Start-/WLAN-Phasen, Fehler bei JSON-Requests, API-Status/Prüfsumme/LED-Recovery. |
| `data/board_controls.js` | Neue konkrete Speicherfehler, unbestätigtes Netzwerkergebnis, keine Erfolgsmeldung für unerwartetes HTTP-200-HTML. |
| `platformio.ini` | Vorhandenen 16-KB-Fix erhalten, Wrapper aktivieren, gesondertes Diagnose-Environment. |
| `.github/workflows/build.yml` | Diagnose-Abbilder ebenfalls bauen. |
| `tests/test_config_store.py`, `tests/test_config_store_sync.py`, Fixture | Tatsächlicher C++-Code mit echtem ArduinoJson, Fehler-/Neustart-/Parallelitätsfälle. |
| `tests/test_config_controls.cjs`, `tests/test_usb_config.py` | Netzwerkfehler, falsche Bestätigung, USB-Vererbung und Trennung der Diagnose. |
| `diagnostics/config-persistence/`, `tests/test_config_probe.py` | Windows-USB-Monitor und ausschließlich lesender, auf öffentliche Felder begrenzter API-Vergleich. |
| Dokumentation | Dieser Bericht, Korrekturvermerk im alten Bericht und README-Verweis; ältere lokale Ergänzungen bleiben erhalten. |

Die öffentlichen Prüfsummen schließen das gesamte `wifi`-Objekt aus. Sie sind
zur Diagnose von LED-/Namensänderungen geeignet, nicht zur Prüfung eines
WLAN-Passworts. Die vollständigen Dateien werden intern trotzdem verglichen.
Die normalen Builds enthalten keine zusätzlichen Diagnose-Serial-Prints.
Der Diagnose-Build startet den HyperSerial-Task bewusst nicht; er ist kein
Firmware-Abbild für gleichzeitigen HyperHDR-Dauerbetrieb.

## D. Automatische Tests und Build

Host-C++-Tests wurden unter dem bereits vorhandenen WSL-Ubuntu/g++ ausgeführt.
Die PlatformIO-Vererbungsprüfungen liefen separat mit dem vorhandenen Windows-
PlatformIO, weil dieses Paket in WSL nicht installiert ist. Insgesamt bestehen
20 unterschiedliche Python-Tests und 26 Browser-Tests, einschließlich der
Integration mit aus dem unveränderten Backend extrahierten GUI-Assets.
Die vier unter WSL übersprungenen PlatformIO-Tests bestanden separat unter Windows.

Der Speicher-Test enthält 17 isolierte Szenarien: echtes Schema/Laden,
Wiederholung und simulierte Neustarts, Teil-Schreiben und RAM-Rollback, kaputtes
JSON/ungültige Werte, Open-Fehler, Sync-Fehler, Backup-/Rename-/Cleanup-Fehler,
Unterbrechung vor und nach Commit, Wiederherstellung, beschädigte Datei ohne
Backup, nativer Formatierungsschutz, LED-Bootmarker und gespeicherte SPI/RMT-
Auswahl, Mount-Fehler/fremde Dateien, Neustartsteuerung/geheimnisfreie Prüfsumme,
konkurrierendes Speichern während Laufzeitänderung und konkurrierender Neustart.
Ein weiterer Test prüft die tatsächliche POSIX-Sync-Funktion mit injizierten
Open-/Sync-/Close-Fehlern. Das simuliert weder Flash-Elektrik noch RMT-Timing.

Reproduzierbare lokale Befehle, im Projektordner:

```powershell
wsl --exec python3 -m unittest discover -v -s /mnt/c/Users/Pwn/Desktop/Hyperk/tests -p 'test_*.py'
& "$env:USERPROFILE\.platformio\penv\Scripts\python.exe" tests/test_usb_config.py
& "$env:USERPROFILE\.platformio\penv\Scripts\python.exe" scripts/check_backend_ui.py --output .pio/config-investigation/ui
$env:HYPERK_BACKEND_FIXTURES = "$PWD\.pio\config-investigation\ui"
npm test
& "$env:USERPROFILE\.platformio\penv\Scripts\pio.exe" run -j 2 -e esp32s3-fh4r2 -e esp32s3-fh4r2-diagnostic
```

Die finalen Dateien, Größen und SHA-256 stehen im separaten
`release/config-persistence-validation.json`. Normale OTA-/Factory-Firmware,
Diagnose-OTA-/Factory-Firmware sowie die jeweiligen Build-Manifeste befinden
sich in `release/`. Ältere Dateien dort sind frühere Builds und sollten nicht
anhand ihres Dateidatums verwechselt werden. Der Name enthält absichtlich
`dirty`, weil bestehende und neue Änderungen nicht automatisch committed wurden.

Beide finalen Builds sind erfolgreich, ohne Compilerwarnungen:

| Zweck | Anwendungs-/OTA-Datei | Größe |
| --- | --- | --- |
| Normal, HyperSerial aktiv | `release/OTA_Hyperk_0.0.5_esp32s3-fh4r2_248b3271-dirty-90b5eee2ae.bin` | 1.237.984 Byte |
| USB-Diagnose, HyperSerial aus | `release/OTA_Hyperk_0.0.5_esp32s3-fh4r2-diagnostic_248b3271-dirty-0a3d06311d.bin` | 1.229.088 Byte |

Die Factory-Dateien tragen denselben jeweiligen Build-Namen mit
`Hyperk_..._factory.bin` statt `OTA_Hyperk_....bin`; sie wurden ebenfalls gebaut.
Die normale App benötigt statisch 50.832 Byte RAM, die Diagnose 63.120 Byte.
Beide passen in den unveränderten App-Slot von 1.900.544 Byte. Der endgültige
Image-Header bestätigt ESP32-S3, 4 MB, DIO und eine gültige Image-Prüfsumme.
Beide erzeugten Partitionstabellen sind bytegleich. Die ELF-Prüfung bestätigt
die Speicher-Wrapper in beiden HTTP-Speicherpfaden, den geschützten Neustart
und die SPI-/RMT-/Sync-Aufrufe im echten Backend. Im Diagnose-Setup fehlt der
HyperSerial-Init-Aufruf, im normalen Setup ist er vorhanden. Die zusätzlichen
Diagnose-Logtexte fehlen in der normalen App.

### Ergänzung 09.11.2026: 17-dBm-WLAN-Variante

Zusätzlich erfolgreich gebaut: `248b3271-dirty-42ee122df8`, mit
`WIFI_TX_POWER_DBM=17.0` und `WIFI_LOW_LATENCY=1` (WLAN-Schlafmodus aus).
Der Quellcode-Hash ist identisch mit dem korrigierten Standard-Build; HyperSerial
bleibt aktiv. Die zuvor verlinkte Variante `90b5eee2ae` verwendet den SDK-Standard
für WLAN. Die 17-dBm-Angabe ist die konfigurierte Sendeleistungsgrenze, keine
Messung der abgestrahlten Leistung.

- USB-Neuinstallation: `release/Hyperk_0.0.5_esp32s3-fh4r2_248b3271-dirty-42ee122df8_factory.bin`
- OTA-Update: `release/OTA_Hyperk_0.0.5_esp32s3-fh4r2_248b3271-dirty-42ee122df8.bin`
- Manifest und passende ELF-Datei stehen mit derselben Kennung in `release/`.

Image-Header (ESP32-S3, 4 MB, DIO) und Artefakt-Prüfsummen wurden geprüft.
Der Assistent hat nichts automatisch geflasht; der Nutzer bestätigt am
09.11.2026 die Fehlerbehebung durch diese Version. Die Dateien und Hashes sind unter
`wifi17` in `release/config-persistence-validation.json` eingetragen.

## E. Konkreter Test am ESP unter Windows

### Installation ohne Löschen

Zunächst die **Diagnose-OTA-/Anwendungs-BIN** aus dem genannten Manifest
installieren. Bevorzugt den vorhandenen lokalen Firmware-OTA-Upload benutzen.
Die `factory.bin` ist für diese Untersuchung ungeeignet: Ihr zusammengeführter
Adressbereich überschreibt auch NVS/OTA-Verwaltung, obwohl kein expliziter
Erase-all ausgeführt wird. Ein Anwendungs-Update lässt die Datenpartitionen
bei unverändertem Layout bestehen.

Falls OTA in der aktuellen Betriebsart nicht erreichbar ist, ist ein manueller
USB-App-Flash möglich. **Die folgenden Befehle wurden nicht ausgeführt.**
HyperHDR und andere serielle Programme vorher schließen. COM4 muss im
Geräte-Manager weiterhin das Espressif-Gerät `303A:1001` sein.

Im Projektordner zunächst die tatsächlich geflashte Tabelle und Daten sichern:

```powershell
$py = "$env:USERPROFILE\.platformio\penv\Scripts\python.exe"
New-Item -ItemType Directory -Force .pio/config-investigation/device-backup | Out-Null
& $py -m esptool --chip esp32s3 --port COM4 --no-stub read-flash 0x8000 0x1000 .pio/config-investigation/device-backup/partitions.bin
& $py "$env:USERPROFILE\.platformio\packages\framework-arduinoespressif32\tools\gen_esp32part.py" .pio/config-investigation/device-backup/partitions.bin
```

Nur wenn die ausgelesenen Adressen/Größen genau der obigen Tabelle entsprechen:

```powershell
& $py -m esptool --chip esp32s3 --port COM4 --no-stub read-flash 0x9000 0x5000 .pio/config-investigation/device-backup/nvs.bin
& $py -m esptool --chip esp32s3 --port COM4 --no-stub read-flash 0xE000 0x2000 .pio/config-investigation/device-backup/otadata.bin
& $py -m esptool --chip esp32s3 --port COM4 --no-stub read-flash 0x3B0000 0x50000 .pio/config-investigation/device-backup/littlefs.bin
Get-Item .pio/config-investigation/device-backup/*.bin | Select-Object Name,Length
```

Erwartete Größen: Tabelle 4096, NVS 20480, OTA-Verwaltung 8192,
LittleFS 327680 Byte. Nur erfolgreich abgeschlossene Reads gelten als Backup.
Die Backups enthalten Zugangsdaten und gehören nicht in Git oder öffentliche
Fehlerberichte. Bei abweichender Tabelle oder unvollständigen Reads hier stoppen.

Der folgende App-Flash ersetzt **beide bisherigen App-Versionen**, damit die
unveränderte OTA-Bootauswahl sicher eine korrigierte App auswählt. NVS,
OTA-Verwaltung, Bootloader und LittleFS werden dabei nicht adressiert:

```powershell
$manifest = Get-Content release/config-persistence-validation.json -Raw | ConvertFrom-Json
$app = Join-Path $PWD $manifest.diagnostic.ota
& $py -m esptool --chip esp32s3 --port COM4 write-flash 0x10000 $app 0x1E0000 $app
```

Kein `erase-flash`, kein Factory-Reset und kein Schreiben einer Factory-BIN.
Die oben vorgeschaltete Prüfung ist notwendig, weil die echte Gerätetabelle in
diesem Auftrag nicht ausgelesen wurde.

### USB-Logs auslesen

Native Serial/JTAG ist eine serielle Schnittstelle; sie benötigt für diesen
Test keinen JTAG-Debugger. Siehe [Espressif USB Serial/JTAG](https://docs.espressif.com/projects/esp-idf/en/v5.2/esp32s3/api-guides/usb-serial-jtag-console.html).
Der beigefügte Monitor sendet keine Reset-/Firmware-/Konfigurationsbefehle und
versucht nach einem USB-Abbruch erneut zu öffnen:

```powershell
& "$env:USERPROFILE\.platformio\penv\Scripts\python.exe" diagnostics/config-persistence/capture_usb.py --port COM4 --seconds 300
```

Er sammelt nach Öffnen gepufferte Startmeldungen. Falls nötig einmal die
Reset-Taste betätigen und den Port im Geräte-Manager erneut kontrollieren.
Datei: `.pio/config-investigation/usb.log`. HyperHDR währenddessen getrennt lassen.
Zusätzliche Logs sind bei normaler Firmware absichtlich nicht verfügbar.
Die Instrumentierung ersetzt keinen vollständigen Panic-Stacktrace: Wenn der
ROM-/SDK-Panictext nicht über USB erscheint, belegt der nächste Boot zumindest
Reset-Ursache und einen eventuell hinterlassenen LED-Marker.

### Hardware-Test A: unabhängig von einer Router-Verbindung

1. Mit `Hyperk-Setup` verbinden, `http://192.168.4.1` öffnen. Nach Installation
   die Seite vollständig neu laden, damit keine alten Scripts verwendet werden.
2. Zunächst Zustand über den lesenden Probe-Befehl erfassen:

   ```powershell
   & "$env:USERPROFILE\.platformio\penv\Scripts\python.exe" diagnostics/config-persistence/probe.py --host 192.168.4.1
   ```

3. Nur die Helligkeit um einen Schritt ändern, z. B. 255→254. LED-Hardwarepanel
   zunächst geschlossen lassen, Treiber/Anzahl/Pins unverändert lassen. Bei
   geöffnetem WLAN-Setup das separate allgemeine „Save Settings“ verwenden.
4. Speichern. Erwartet: Request, Write started, Backend returned=1,
   Verification, Write completed und RAM/save result=1. Die GUI bestätigt erst
   nach empfangener gültiger Antwort. Die API muss die neue Helligkeit zeigen,
   `storage.config_valid=true`, `error=none`, `last_save_succeeded=true`.
5. Einmal stromlos neu starten, erneut verbinden und denselben Probe-Befehl
   ausführen. Helligkeit und öffentliche Prüfsumme müssen erhalten bleiben.
   `save_attempted=false` nach erneutem Boot ist normal, wenn keine neue
   Speicherung stattfand; entscheidend sind Laden, Prüfsumme und Wert.

### Hardware-Test B bis E

- **B – Wiederholen:** Helligkeit 254↔253 fünfmal ändern, jeweils speichern,
  stromlos starten und API-Wert prüfen. Kein Erase zwischen Versuchen.
- **C – WLAN:** Erst nach A/B SSID und Passwort im Setup speichern. Nach dem
  Neustart müssen `Configuration load result=1` und `STA connection attempt
  started` erscheinen. Ein Disconnect-Grund oder AP-Fallback danach ist
  getrennt zu bewerten. Im AP oder über die neue Router-IP prüfen:

  ```powershell
  & "$env:USERPROFILE\.platformio\penv\Scripts\python.exe" diagnostics/config-persistence/probe.py --host 192.168.4.1 --expected-ssid "DEINE-SSID"
  ```

  `wifi_ssid_matches=true` bestätigt den nach Boot erneut geladenen SSID-Wert,
  ohne ihn auszugeben. Ein korrektes Passwort wird nicht über die Diagnose-API
  offengelegt; erfolgreiche Router-Authentifizierung ist dessen zusätzlicher
  Hardwaretest. Bei früher bestehender STA-Verbindung statt AP-IP die aktuelle
  Router-IP verwenden; `10.0.0.47` ist nur eine frühere Adresse.
- **D – LEDs:** SPI zunächst beibehalten, insgesamt 258 SK6812-RGBW und Daten
  auf GPIO37/38 kontrollieren. Segmentbeginn nach tatsächlicher Aufteilung:
  nur bei zwei gleich langen 129er-Streifen sind die Starts 0/129. Danach
  gezielt RMT testen, ohne Anzahl/Pins gleichzeitig zu ändern. Erwartete
  SPI-/RMT-/Sync-Ergebnisse sind `value=0` (ESP_OK); `LED initialization
  result=1` bedeutet, dass diese Aufrufe ohne erfassten Fehler zurückkehrten,
  nicht automatisch fehlerfreie optische Ausgabe. Bei einem Absturz erneut
  starten: Ein stehengebliebener Marker soll LED-Init überspringen und Web
  verfügbar machen. Konfiguration dort korrigieren und erneut speichern.
- **E – Dauerbetrieb:** Wieder normale OTA-Firmware installieren, dann USB
  an den LG-TV und HyperHDR anschließen. Erkennung von HyperSerial, RGBW,
  beide Ausgänge, FPS und längeren Betrieb prüfen. Die Diagnosefirmware hat
  absichtlich keinen HyperSerial-Datenempfang. Die früheren ca. 95 FPS sind
  eine Referenz, kein neu gemessener Wert.

Zurückmelden: Build-ID, fehlgeschlagene Phase/Fehlercode, Zeilen `[BOOT]`,
`[CONFIG]`, `[LED]`, `[WIFI]` rund um den Fehler, Reset-Grund und die öffentliche
Probe-Ausgabe vor dem Speichern/nach erneutem Boot. Keine Passwörter oder
LittleFS-/NVS-Backups senden. Damit lässt sich ein neuer Schreibfehler von
einem reinen WLAN-Abbruch und einem LED-Initialisierungsproblem unterscheiden.
