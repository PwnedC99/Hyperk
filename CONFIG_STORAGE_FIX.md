# Konfiguration wird nach dem Speichern nicht übernommen

**Nachtrag 08.11.2026:** Diese erste Korrektur enthielt selbst einen Fehler in der
Schema-Prüfung (`numLeds` statt `led.numLeds`) und beließ den HTTP-Stack bei 4 KB.
Der aktuelle Befund, Korrekturen und die Windows-Testanleitung stehen in
[CONFIG_PERSISTENCE_INVESTIGATION.md](CONFIG_PERSISTENCE_INVESTIGATION.md).
Die unten genannten älteren Firmwaredateien sind damit für diese Untersuchung
überholt.

## Befund und Grenze der Diagnose

Die Untersuchung des unveränderten Backends 0.0.5 zeigt drei konkrete Schwächen:

- `Storage::saveConfig()` öffnet `/config.json` direkt zum Überschreiben. Der
  Erfolg wird vom Öffnen der Datei abgeleitet, ohne das vollständig geschriebene
  JSON erneut zu lesen und zu prüfen.
- Die HTTP-Handler planen nach `Config::saveConfig()` einen Neustart oder die
  erneute LED-Initialisierung, ohne einen Speicherfehler zuverlässig abzufangen.
- `Storage::loadConfig()` formatiert bei einem JSON-Lesefehler das Dateisystem
  und schreibt Standardwerte zurück. Das kann den erneuten Setup-AP erklären.

Dies sind durch Binärprüfung belegte Fehler in der Speicherbehandlung. Welcher
ursprüngliche Schreib-/Lesefehler auf dem konkreten Board auftritt, ist ohne
Geräteprotokoll weiterhin nicht bewiesen. Der neue Build liefert dafür einen
konkreten Fehlercode. Die zuvor diskutierten RMT-/USB-Vermutungen sind keine
bestätigte Erklärung für das allgemeine Speicherproblem.

## Korrektur im FH4R2-Profil

`src/config_store.cpp` bindet die bestehenden Konfigurationsfunktionen über
Linker-Wrapper an. Das Backend-Archiv und das Konfigurationsschema bleiben gleich.

1. Das Backend schreibt zunächst `/config.pending.json`.
2. Nach Flush/Close wird die Datei mit dem festgelegten ArduinoJson-Parser erneut
   gelesen und auf gültiges JSON und die benötigten Konfigurationsfelder geprüft.
3. Erst anschließend ersetzt ein Dateisystem-Rename die bisherige `/config.json`.
4. Bei einem Fehler bleibt die vorherige Datei erhalten. Eine vorhandene gültige
   Konfiguration wird zusätzlich wieder in den RAM geladen. Scheitert auch das,
   wird ein gesonderter Fehler gemeldet.
5. Fehlgeschlagene Speicherungen unterdrücken den geplanten Neustart bzw. das
   Anwenden der neuen LED-Einstellungen; der HTTP-Status ist 503.
6. Ungültige bestehende Konfigurationsdateien werden nicht automatisch gelöscht.
   Der bisherige Formatierungs-Fallback des Backend-Laders wird abgefangen.
7. Ein nicht einbindbares Dateisystem wird nur dann initialisiert, wenn seine
   gesamte Partition nachweislich gelöscht ist (alle Bytes 0xff). Andere Inhalte
   werden für eine spätere Wiederherstellung erhalten.

Das betrifft nur `esp32s3-fh4r2`. Partitionstabelle, GPIOs, LED-Treiber, RGBW,
Segmentverarbeitung, GPIO1/NVS und USB-Adapter bleiben unverändert. Bei einer
bereits beschädigten Datei können frühere verlorene Werte nicht rekonstruiert
werden. Ohne gültige Datei startet das Backend mit seinen RAM-Standardwerten;
die beschädigte Datei wird dabei erhalten.

Die WLAN-/Einstellungsformulare zeigen nun den konkreten Fehler auf der Seite.
Die ursprünglichen Feldnamen und die Segmentdaten werden weiter verwendet.
Eine Bestätigung bzw. Neustartmeldung erscheint erst nach erfolgreicher Antwort.

`/api/board` enthält zusätzlich `storage` mit `mounted`, `config_valid`,
`save_attempted`, `last_save_succeeded` und `error`. WLAN-Passwörter und der Inhalt
der Konfigurationsdatei werden nicht über diese Diagnose ausgegeben. Die gleichen
Informationen stehen im bestehenden Diagnosebereich der Board-Steuerung.

## Validierung

- `esp32s3-fh4r2` erfolgreich kompiliert, keine Compilerwarnungen.
- 17 Python-Tests und 24 Browser-Tests bestanden, keine übersprungen.
- Fehlertests verwenden den echten ArduinoJson-Parser und die tatsächliche
  Speicherimplementierung mit simuliertem Dateisystem: Teil-Schreibvorgänge,
  ungültiges JSON, Open-/Rename-/Cleanup-Fehler, RAM-Wiederherstellung,
  Mount-Fehler, Formatierungsschutz und Neustart-/Apply-Unterdrückung.
- WLAN-Integration mit den unveränderten HTML-/JS-Assets aus Backend 0.0.5 geprüft.
- Im fertigen ELF sind alle sieben Speicher-Wrapper vorhanden. Die ursprünglichen
  Konfigurations-/Dateifunktionen rufen die entsprechenden Wrapper auf.
- Artefakt-Hashes und unveränderte Backend-SHA-256 geprüft; Partitionstabelle,
  USB-Adapter, GPIO1- und WiFi-Leistungssteuerung gegen HEAD unverändert.
- Tests auf dem echten Board, dauerhafte Speicherung über einen stromlosen
  Neustart und die tatsächliche WLAN-Anmeldung stehen noch aus.

Die vollständigen Speicher-Fehlertests benötigen die ArduinoJson-Header, die
`pio run -e esp32s3-fh4r2` installiert. CI führt diesen Test nach dem ersten
Firmware-Build verpflichtend aus:

```sh
python tests/test_config_store.py
```

## Firmware und Installation

Build-ID: `3300c2c6-dirty-9b96009f5b`. Dateien in `release/`:

- `OTA_Hyperk_0.0.5_esp32s3-fh4r2_3300c2c6-dirty-9b96009f5b.bin`
- `Hyperk_0.0.5_esp32s3-fh4r2_3300c2c6-dirty-9b96009f5b_factory.bin`
- `Hyperk_0.0.5_esp32s3-fh4r2_3300c2c6-dirty-9b96009f5b.json`

Zur Untersuchung eines bestehenden Speicherproblems ein Backup behalten und
keinen vollständigen Flash-Erase durchführen. Für ein Update unter Erhalt von
NVS und Dateisystem die OTA-/Anwendungsdatei verwenden. Das kombinierte
Factory-Image überschreibt unter anderem NVS, deckt aber das Dateisystem nicht ab.

Bei bestehender, bestätigter FH4R2-Partitionierung können beide App-Slots per USB
beschrieben werden, ohne die vorhandene Bootauswahl oder Datenpartitionen zu
ändern. Dabei wird die vorherige Firmware in beiden App-Slots ersetzt:

```sh
hyperk_app="/Users/a21/Developer/Hyperk/release/OTA_Hyperk_0.0.5_esp32s3-fh4r2_3300c2c6-dirty-9b96009f5b.bin"
esptool --chip esp32s3 -p /dev/cu.usbmodem101 write-flash \
  0x10000 "$hyperk_app" 0x1E0000 "$hyperk_app"
```

Die Tabelle muss `app0` ab `0x10000` und `app1` ab `0x1E0000`, jeweils mit Größe
`0x1D0000`, enthalten. Siehe auch `USB_SERIAL_FIX.md` zur Prüfung und Sicherung.
Es wurde kein angeschlossenes Gerät geflasht oder zurückgesetzt.

Nach manueller Installation zuerst einen einzelnen Wert speichern, neu laden
und nach einem stromlosen Neustart vergleichen. Bei einem Fehler die jetzt
angezeigte Meldung bzw. `storage.error` aus `/api/board` auswerten.
