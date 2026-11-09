(() => {
    const storageErrors = {
        filesystem_mount_failed: 'Dateisystem konnte nicht eingebunden werden. Vorhandene Daten wurden erhalten.',
        filesystem_not_mounted: 'Dateisystem ist nicht verfügbar.',
        existing_config_invalid: 'Gespeicherte Konfiguration ist ungültig. Die Datei wurde nicht gelöscht.',
        backend_load_failed: 'Das Backend konnte die Konfiguration nicht laden.',
        pending_cleanup_failed: 'Temporäre Konfigurationsdatei konnte nicht entfernt werden.',
        backend_write_failed: 'Konfiguration konnte nicht geschrieben werden.',
        config_sync_failed: 'Schreiben in den Flash konnte nicht abgeschlossen werden.',
        written_config_invalid: 'Geschriebene Konfiguration war unvollständig oder ungültig.',
        config_commit_failed: 'Geprüfte Konfiguration konnte nicht übernommen werden.',
        config_backup_failed: 'Vorherige Konfiguration konnte nicht gesichert werden.',
        committed_config_invalid: 'Konfiguration nach dem Übernehmen nicht lesbar; Wiederherstellung erforderlich.',
        config_recovery_failed: 'Vorherige Konfiguration konnte nicht wiederhergestellt werden.',
        form_data_required: 'Dieser Endpunkt erwartet Formulardaten.',
        save_failed_and_reload_failed: 'Speichern und Wiederherstellen der vorherigen Konfiguration sind fehlgeschlagen.'
    };
    function installSettingsSaver() {
        for (const path of ['/save_wifi', '/save_config']) {
            const form = document.querySelector(`form[action="${path}"]`);
            if (!form || form.dataset.protectedSave) continue;
            form.dataset.protectedSave = 'true';
            const message = document.createElement('p');
            message.dataset.configSaveStatus = 'true';
            message.setAttribute('role', 'status');
            message.setAttribute('aria-live', 'polite');
            form.appendChild(message);
            let busy = false;
            form.addEventListener('submit', async event => {
                event.preventDefault();
                event.stopImmediatePropagation();
                if (busy) return;
                message.textContent = '';
                message.setAttribute('role', 'status');
                if (!form.reportValidity()) return;
                const custom = form.querySelector('#ssid_custom');
                if (form.querySelector('#ssid_select')?.value === '---CUSTOM---' && !custom?.value.trim()) {
                    message.textContent = 'Bitte einen WLAN-Namen eingeben.';
                    custom?.focus();
                    return;
                }
                const fields = new FormData(form);
                if (path === '/save_config' && document.getElementById('led_hardware_page')?.dataset.loaded) {
                    if (typeof clearErrors === 'function') clearErrors(form);
                    if (typeof validateSegments === 'function' && !validateSegments(form)) return;
                    fields.set('segments', config.segments.flatMap(segment =>
                        [segment.startIndex, segment.data, segment.clock, segment.reversed ? 1 : 0]).join(','));
                }
                const button = event.submitter || form.querySelector('button[type="submit"]');
                const controller = new AbortController();
                const timeout = setTimeout(() => controller.abort(), 15000);
                busy = true;
                if (button) { button.disabled = true; button.setAttribute('aria-busy', 'true'); }
                try {
                    const response = await fetch(form.action, {
                        method: 'POST', body: new URLSearchParams(fields), signal: controller.signal, cache: 'no-store'
                    });
                    const text = await response.text();
                    let result;
                    try { result = JSON.parse(text); } catch (_) { result = {}; }
                    if (!response.ok) throw new Error(storageErrors[result.error] || result.error || `HTTP ${response.status}`);
                    if (path === '/save_config' && !['ok', 'saved', 'reboot'].includes(result.status))
                        throw new Error('Ungültige Speicherbestätigung');
                    const reboot = path === '/save_wifi' || result.status === 'reboot';
                    message.textContent = reboot ? 'Gespeichert. Gerät startet neu.' : 'Konfiguration gespeichert.';
                    if (typeof showToast === 'function') showToast(reboot);
                } catch (error) {
                    message.setAttribute('role', 'alert');
                    message.textContent = error.name === 'AbortError' || error.name === 'TypeError' ?
                        'Keine Speicherbestätigung vom Gerät. Nach dem Neuverbinden die Einstellungen prüfen.' :
                        `Speichern fehlgeschlagen: ${error.message}`;
                } finally {
                    clearTimeout(timeout);
                    busy = false;
                    if (button) { button.disabled = false; button.setAttribute('aria-busy', 'false'); }
                }
            }, true);
        }
    }
    function mount(parent) {
        if (!parent || parent.querySelector('[data-board-panel]')) return;
        const panel = document.createElement('div');
        panel.dataset.boardPanel = 'true';
        panel.innerHTML = `<div class="toggleContainer">
            <label>Peripherie (GPIO1)
                <input type="checkbox" role="switch" data-peripheral-toggle disabled>
            </label>
            <small data-peripheral-status role="status" aria-live="polite">Zustand wird geladen …</small>
            <small> · Wird sofort gespeichert und nach einem Neustart wiederhergestellt.</small>
            </div>
            <details><summary>WLAN-Diagnose</summary>
                <dl data-wifi-diagnostics></dl>
            </details>
            <small><a href="/board.html">Board-Steuerung öffnen</a></small>
            <p data-board-error role="alert" hidden></p>`;
        parent.appendChild(panel);
        const button = panel.querySelector('[data-peripheral-toggle]');
        const status = panel.querySelector('[data-peripheral-status]');
        const error = panel.querySelector('[data-board-error]');
        const diagnostics = panel.querySelector('[data-wifi-diagnostics]');
        const value = (number, unit) => number === null || number === undefined ? '–' : `${number} ${unit}`;
        function showDiagnostics(state) {
            if (!state.wifi) return;
            const wifi = state.wifi;
            const entries = [
                ['Verbindung', wifi.connected ? 'Mit Router verbunden' : wifi.ap_active ? 'Setup-Access-Point' : 'Verbindungsaufbau'],
                ['IP-Adresse', wifi.ip], ['WLAN-Kanal', wifi.channel],
                ['Empfang (RSSI)', value(wifi.rssi_dbm, 'dBm')],
                ['Vorgegebene TX-Grenze', wifi.configured_tx_dbm == null ? 'SDK-Standard' : value(wifi.configured_tx_dbm, 'dBm')],
                ['TX-Grenze laut Treiber', value(wifi.driver_tx_limit_dbm, 'dBm')],
                ['Geringe Latenz', wifi.low_latency === null ? 'Unbekannt' : wifi.low_latency ? 'Aktiv' : 'Inaktiv'],
                ['Verbindungsabbrüche', wifi.disconnect_count],
                ['Letzter Abbruch', `${wifi.last_disconnect_text} (${wifi.last_disconnect_reason})`],
                ['Build', state.build_id]
            ];
            if (state.storage) {
                entries.push(['Dateisystem', state.storage.mounted ? 'Verfügbar' : 'Nicht verfügbar'],
                    ['Konfigurationsdatei', state.storage.config_valid ? 'Gültig' : 'Nicht gültig'],
                    ['Letzte Speicherung', !state.storage.save_attempted ? 'In dieser Sitzung noch nicht gespeichert' :
                        state.storage.last_save_succeeded ? 'Erfolgreich' : 'Fehlgeschlagen'],
                    ['Speicherstatus', storageErrors[state.storage.error] || state.storage.error]);
                if (state.storage.led_recovery) entries.push(['LED-Wiederherstellung', 'LED-Initialisierung angehalten. Konfiguration prüfen und erneut speichern.']);
            }
            diagnostics.replaceChildren(...entries.flatMap(([label, text]) => {
                const term = document.createElement('dt'); term.textContent = label;
                const description = document.createElement('dd'); description.textContent = String(text ?? '–');
                return [term, description];
            }));
        }
        let enabled = false;
        let busy = false;
        let refreshing = false;
        let generation = 0;
        function render(state) {
            showDiagnostics(state);
            enabled = state.peripheral.enabled;
            status.textContent = `GPIO${state.peripheral.gpio}: ${enabled ? 'EIN (HIGH)' : 'AUS (LOW)'}`;
            button.checked = enabled;
            button.disabled = busy || !state.peripheral.storage_ready;
            if (!state.peripheral.storage_ready) throw new Error('Der Zustand kann nicht im Flash gespeichert werden.');
        }
        async function request(url, options) {
            const controller = new AbortController();
            const timer = setTimeout(() => controller.abort(), 8000);
            try {
                const response = await fetch(url, { cache: 'no-store', ...options, signal: controller.signal });
                const state = await response.json();
                if (!response.ok) throw new Error(state.error || `HTTP ${response.status}`);
                return state;
            } finally { clearTimeout(timer); }
        }
        async function refresh() {
            if (busy || refreshing) return;
            const current = generation;
            refreshing = true;
            try {
                const state = await request('/api/board');
                if (current === generation && !busy) { render(state); error.hidden = true; }
            } catch (err) {
                if (current === generation && !busy) { error.textContent = err.message; error.hidden = false; }
            } finally { refreshing = false; }
        }
        button.addEventListener('change', async () => {
            if (busy) return;
            generation++;
            busy = true; button.disabled = true;
            try {
                const state = await request('/api/peripheral', {
                    method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                    body: new URLSearchParams({ enabled: enabled ? '0' : '1' })
                });
                busy = false; render(state); error.hidden = true;
            } catch (err) {
                busy = false; await refresh();
                error.textContent = err.message; error.hidden = false;
            }
        });
        const relay = parent.querySelector('input[name="relay-gpio"]');
        if (relay) {
            const validate = () => relay.setCustomValidity(Number(relay.value) === 1 ? 'GPIO1 ist für die Peripherie reserviert.' : '');
            relay.addEventListener('input', validate);
            validate();
        }
        refresh();
        const timer = setInterval(() => {
            if (!panel.isConnected) { clearInterval(timer); return; }
            if (!document.hidden) refresh();
        }, 5000);
        window.addEventListener('pagehide', () => clearInterval(timer), { once: true });
    }
    window.HyperkBoard = { mount, installSettingsSaver };
    installSettingsSaver();
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => mount(document.getElementById('board-controls')), { once: true });
    } else mount(document.getElementById('board-controls'));
})();
