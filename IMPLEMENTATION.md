# Umsetzung

1. [x] Eigenes ESP32-S3FH4R2-Profil; GPIO1 für Peripherie reserviert.
2. [x] GPIO1-Schalter mit Speicherung des letzten Zustands in NVS; Oberfläche unter /board.html und LED Hardware.
3. [x] WLAN-Diagnose, konfigurierbare Wartezeiten und Wiederverbindung ohne regelmäßige Neustarts.
4. [x] Optionaler WLAN-Modus mit geringer Latenz.
5. [x] Atomare, prüfsummengeschützte Backend-Downloads und optionale ccache-Nutzung.
6. [x] Festgelegte Abhängigkeiten, Build-Kennzeichnung und Manifest.
7. [x] Automatische Tests, Backend-UI-Kompatibilitätsprüfung und Firmware-Builds.
8. [x] Dokumentation und abschließende Prüfung.

Hardwaretests stehen aus; keine Firmware wird automatisch auf ein Board geflasht.

## Lokale Prüfung

- 10 Python-Tests erfolgreich (GPIO-Zustand/NVS, Pin-Konflikte, WLAN-Zeitabläufe, Download-Abbrüche, Build-ID und Compiler-Optionen).
- 10 JavaScript-/DOM-Tests erfolgreich, einschließlich unveränderter Backend-Oberfläche 0.0.5.
- Firmware-Builds erfolgreich: generischer ESP32-S3, FH4R2-Standard und FH4R2 mit 17 dBm / WIFI_LOW_LATENCY=1.
- Standard- und Testvariante haben verschiedene Build-IDs; Artefakt-Prüfsummen und 4-MB-Flashheader geprüft.
- GitHub-Actions-Workflow eingerichtet und als YAML geprüft; noch nicht auf GitHub ausgeführt.
- Hardwareprüfung bleibt offen; siehe readme.md.
