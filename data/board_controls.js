(() => {
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
    window.HyperkBoard = { mount };
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => mount(document.getElementById('board-controls')), { once: true });
    } else mount(document.getElementById('board-controls'));
})();
