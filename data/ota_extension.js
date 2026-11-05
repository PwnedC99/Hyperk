(() => {
    // Extend the pinned backend's OTA settings while preserving its release channels.
    const sourceUrl = new URL(document.currentScript.src);
    sourceUrl.searchParams.set('hyperk_original', '1');
    let localBusy = false;
    let remotePending = false;

    function mount() {
        const page = document.getElementById('ota_page');
        if (!page || page.querySelector('[data-local-ota]')) return;
        const panel = document.createElement('div');
        panel.dataset.localOta = 'true';
        panel.innerHTML = `<hr class="section-divider">
            <h5>Lokale Firmware installieren</h5>
            <label>OTA-Firmware (.bin)
                <input type="file" accept=".bin" data-local-ota-file>
            </label>
            <p><small>OTA-BIN für den ESP32-S3FH4R2 auswählen. Die vorhandenen Einstellungen bleiben erhalten.
                Während des Updates die Stromversorgung eingeschaltet lassen.</small></p>
            <button type="button" class="secondary outline" data-local-ota-install disabled>Firmware hochladen</button>
            <progress data-local-ota-progress max="100" value="0" hidden aria-label="Firmware-Upload"></progress>
            <p data-local-ota-status role="status" aria-live="polite" hidden></p>`;
        const footer = page.querySelector('.ota-footer');
        if (footer) footer.before(panel);
        else page.appendChild(panel);
        const input = panel.querySelector('[data-local-ota-file]');
        const install = panel.querySelector('[data-local-ota-install]');
        const progress = panel.querySelector('[data-local-ota-progress]');
        const status = panel.querySelector('[data-local-ota-status]');
        const form = page.closest('form');

        function message(text, error = false) {
            status.textContent = text;
            status.hidden = false;
            status.setAttribute('role', error ? 'alert' : 'status');
        }
        function sync() {
            install.disabled = !input.files.length || localBusy || remotePending || isUpdating;
            input.disabled = localBusy || remotePending || isUpdating;
        }
        input.addEventListener('change', () => {
            status.hidden = true;
            progress.hidden = true;
            sync();
        });
        // The native updater sends its XHR asynchronously; keep both paths mutually exclusive.
        const nativeStart = window.startOtaUpdate;
        window.startOtaUpdate = async (...args) => {
            if (localBusy || remotePending || isUpdating) return;
            remotePending = true;
            sync();
            try { return await nativeStart(...args); }
            finally { remotePending = false; sync(); }
        };
        const nativeCheck = window.checkFirmwareUpdates;
        window.checkFirmwareUpdates = (...args) => {
            if (localBusy || remotePending || isUpdating) return;
            return nativeCheck(...args);
        };
        // Resolve the existing confirmation dialog when dismissed with Escape as well.
        document.getElementById('confirm-modal').addEventListener('cancel', event => {
            event.preventDefault();
            closeConfirm(false);
        });
        form?.addEventListener('submit', event => {
            if (localBusy) { event.preventDefault(); event.stopImmediatePropagation(); }
        }, true);
        const timer = setInterval(() => {
            if (!panel.isConnected) { clearInterval(timer); return; }
            sync();
        }, 500);
        window.addEventListener('pagehide', () => clearInterval(timer), { once: true });

        install.addEventListener('click', async () => {
            if (localBusy || remotePending || isUpdating || !input.files.length) return;
            const file = input.files[0];
            localBusy = true;
            sync();
            let controls = [];
            let succeeded = false;
            try {
                // ESP-IDF: 24-byte image header, 8-byte segment header, 256-byte app descriptor.
                // ESP32-S3 chip ID = 9; each OTA slot in partitions_4mb.csv is 0x1D0000 bytes.
                if (!/\.bin$/i.test(file.name) || /factory/i.test(file.name)) {
                    throw new Error('Bitte die OTA-BIN auswählen. Factory-Dateien können hier nicht installiert werden.');
                }
                if (file.size < 288 || file.size > 0x1D0000) {
                    throw new Error('Die Firmware ist leer, unvollständig oder zu groß für den OTA-Speicher.');
                }
                const bytes = await file.slice(0, 288).arrayBuffer();
                const header = new DataView(bytes);
                if (header.getUint8(0) !== 0xE9 || header.getUint16(12, true) !== 9) {
                    throw new Error('Diese Datei enthält keine ESP32-S3-Firmware.');
                }
                if (header.getUint32(32, true) !== 0xABCD5432) {
                    throw new Error('Keine OTA-Anwendungsfirmware erkannt. Bitte keine Factory- oder Bootloader-Datei auswählen.');
                }
                const confirmed = await customConfirm(`„${file.name}“ installieren? Der ESP startet danach neu. Die gespeicherten Einstellungen bleiben erhalten.`);
                if (!confirmed) return;
                isUpdating = true;
                controls = Array.from(document.querySelectorAll('form button, form input, form select'),
                    element => [element, element.disabled]);
                controls.forEach(([element]) => { element.disabled = true; });
                install.setAttribute('aria-busy', 'true');
                progress.value = 0;
                progress.hidden = false;
                message('Firmware wird hochgeladen. Bitte nicht ausschalten …');
                await new Promise((resolve, reject) => {
                    const xhr = new XMLHttpRequest();
                    xhr.open('POST', '/ota', true);
                    xhr.timeout = 180000;
                    xhr.setRequestHeader('hyperk-ota-firmware-size', String(file.size));
                    // Backend 0.0.5 expects "esp32s3."; our build-ID filenames use "esp32s3-fh4r2_".
                    // The actual image was checked above and is sent unchanged.
                    xhr.setRequestHeader('hyperk-ota-firmware-name', 'OTA_Hyperk_local_esp32s3.bin');
                    xhr.upload.onprogress = event => {
                        if (!event.lengthComputable) return;
                        const percent = Math.round(event.loaded / event.total * 100);
                        progress.value = percent;
                        message(percent === 100 ? 'Upload vollständig. Firmware wird geprüft …' : `Firmware wird hochgeladen: ${percent} %`);
                    };
                    xhr.onload = () => {
                        if (xhr.status === 200 && /^ok$/i.test(xhr.responseText.trim())) resolve();
                        else reject(new Error(`Update fehlgeschlagen: ${xhr.responseText.trim() || `HTTP ${xhr.status}`}`));
                    };
                    xhr.onerror = () => reject(new Error('Verbindung unterbrochen. Update nicht bestätigt; Erreichbarkeit und Firmwarestand prüfen.'));
                    xhr.ontimeout = () => reject(new Error('Zeitüberschreitung. Update nicht bestätigt; Erreichbarkeit und Firmwarestand prüfen.'));
                    xhr.onabort = () => reject(new Error('Der Upload wurde abgebrochen.'));
                    const data = new FormData();
                    data.append('update', file, file.name);
                    xhr.send(data);
                });
                succeeded = true;
                progress.value = 100;
                message('Update erfolgreich. Der ESP startet neu; die Seite wird anschließend neu geladen.');
                showToast(true);
            } catch (error) {
                progress.hidden = true;
                message(error.message, true);
            } finally {
                isUpdating = false;
                if (!succeeded) {
                    controls.forEach(([element, disabled]) => { element.disabled = disabled; });
                    localBusy = false;
                }
                install.removeAttribute('aria-busy');
                sync();
            }
        });
    }

    const ready = fetch(sourceUrl, { cache: 'no-store' })
        .then(response => {
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            return response.text();
        })
        .then(source => {
            const script = document.createElement('script');
            script.textContent = source;
            document.head.appendChild(script);
            script.remove();
            const setup = window.setupOta;
            if (setup === initialize || typeof setup !== 'function') throw new Error('OTA-Einstellungen konnten nicht geladen werden.');
            const wrapped = (...args) => { setup(...args); mount(); };
            window.setupOta = wrapped;
            return wrapped;
        });
    function initialize() {
        return ready.then(setup => setup()).catch(error => {
            console.error(error);
            const message = document.createElement('p');
            message.setAttribute('role', 'alert');
            message.textContent = `OTA-Einstellungen konnten nicht geladen werden. Bitte die Seite neu laden. ${error.message}`;
            document.getElementById('ota_page').appendChild(message);
        });
    }
    window.setupOta = initialize;
})();
