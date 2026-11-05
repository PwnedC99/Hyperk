const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { JSDOM } = require('jsdom');
const fixtures = process.env.HYPERK_BACKEND_FIXTURES;
const integration = (name, fn) => test(name, { skip: !fixtures }, fn);
const tick = () => new Promise(setImmediate);

async function openOta({ sourceError = false, delayBackend = false } = {}) {
    const html = fs.readFileSync(path.join(fixtures, 'settings.html'), 'utf8');
    const ota = fs.readFileSync(path.join(fixtures, 'settings_ota.html'), 'utf8');
    const backend = fs.readFileSync(path.join(fixtures, 'settings_ota.js'), 'utf8');
    const dom = new JSDOM(html, { runScripts: 'outside-only', url: 'http://hyperk.local/settings.html' });
    const w = dom.window;
    w.config = { version: '0.0.5', architecture: 'ESP32-S3', board: 'esp32s3' };
    const page = w.document.getElementById('ota_page');
    page.style.display = 'block';
    page.insertAdjacentHTML('beforeend', ota);
    const modal = w.document.getElementById('confirm-modal');
    modal.showModal = () => modal.setAttribute('open', '');
    modal.close = () => modal.removeAttribute('open');
    const toasts = [];
    w.showToast = reboot => toasts.push(reboot);
    w.Blob.prototype.arrayBuffer = function () {
        return new Promise((resolve, reject) => {
            const reader = new w.FileReader();
            reader.onload = () => resolve(reader.result);
            reader.onerror = () => reject(reader.error);
            reader.readAsArrayBuffer(this);
        });
    };
    const uploads = [];
    w.XMLHttpRequest = class {
        upload = {};
        headers = {};
        open(method, url, async) { Object.assign(this, { method, url, async }); }
        setRequestHeader(key, value) { this.headers[key] = value; }
        send(data) { this.data = data; uploads.push(this); }
        respond(status = 200, text = 'OK') {
            this.status = status; this.responseText = text; this.onload();
        }
    };
    const requests = [];
    let releaseBackend;
    const gate = new Promise(resolve => { releaseBackend = resolve; });
    if (!delayBackend) releaseBackend();
    w.fetch = async (url, options) => {
        requests.push({ url: String(url), options });
        if (String(url).includes('settings_ota.js')) {
            await gate;
            return { ok: !sourceError, status: sourceError ? 503 : 200, text: async () => backend };
        }
        return { ok: true, json: async () => [{ tag_name: '0.0.6', prerelease: false, assets: [
            { name: 'OTA_Hyperk_0.0.6_esp32s3.bin', browser_download_url: 'https://example.test/official.bin' }
        ] }], blob: async () => new w.Blob(['official']) };
    };
    Object.defineProperty(w.document, 'currentScript', {
        get: () => ({ src: 'http://hyperk.local/settings_ota.js?v=0.0.5' })
    });
    const append = w.document.head.appendChild.bind(w.document.head);
    w.document.head.appendChild = script => {
        const element = append(script);
        vm.runInContext(script.textContent, dom.getInternalVMContext());
        return element;
    };
    // Expected failure is displayed by the extension, not logged to the test runner.
    w.console.error = () => {};
    vm.runInContext(fs.readFileSync(path.join(__dirname, '../data/ota_extension.js'), 'utf8'), dom.getInternalVMContext());
    const initialized = w.setupOta();
    if (!delayBackend) await initialized;
    const fileInput = () => page.querySelector('[data-local-ota-file]');
    function choose(name = 'OTA_Hyperk_0.0.5_esp32s3-fh4r2_build-id.bin', options = {}) {
        const bytes = new Uint8Array(options.size ?? 512);
        if (bytes.length >= 288) {
            const header = new DataView(bytes.buffer);
            header.setUint8(0, options.magic ?? 0xE9);
            header.setUint16(12, options.chip ?? 9, true);
            header.setUint32(32, options.appMagic ?? 0xABCD5432, true);
        }
        const file = new w.File([bytes], name);
        Object.defineProperty(fileInput(), 'files', { configurable: true, value: [file] });
        fileInput().dispatchEvent(new w.Event('change'));
        return file;
    }
    async function start() {
        page.querySelector('[data-local-ota-install]').click();
        // FileReader completes asynchronously; wait for validation/confirmation.
        for (let attempt = 0; attempt < 100 && !modal.open && !page.querySelector('[data-local-ota-status]:not([hidden])'); attempt++) {
            await new Promise(resolve => setTimeout(resolve, 2));
        }
    }
    return { dom, w, page, modal, uploads, requests, toasts, choose, start, fileInput,
        initialized, releaseBackend, install: () => page.querySelector('[data-local-ota-install]'),
        status: () => page.querySelector('[data-local-ota-status]') };
}

integration('OTA panel is mounted once inside the existing settings and preserves official channels', async () => {
    const p = await openOta();
    try {
        p.w.setupOta();
        assert.equal(p.page.querySelectorAll('[data-local-ota]').length, 1);
        assert.equal(p.page.querySelector('form'), null);
        assert.equal(p.install().type, 'button');
        assert.equal(p.install().disabled, true);
        assert(p.page.querySelector('.ota-footer').previousElementSibling.matches('[data-local-ota]'));
        assert.deepEqual(Array.from(p.page.querySelector('#ota_channel').options, option => option.value), ['stable', 'testing']);
        assert(p.requests[0].url.includes('hyperk_original=1'));
        assert.equal(p.requests[0].options.cache, 'no-store');
        await p.w.checkFirmwareUpdates();
        assert.equal(p.page.querySelector('#install_update_btn').innerText, 'Install Update');
        assert(p.requests.some(request => request.url.includes('releases-api-proxy')));
    } finally { p.dom.window.close(); }
});

integration('local OTA waits for confirmation and uploads the exact selected file with backend-compatible headers', async () => {
    const p = await openOta();
    try {
        const file = p.choose();
        await p.start();
        assert(p.modal.open);
        assert.equal(p.uploads.length, 0);
        p.w.closeConfirm(true); await tick();
        assert.equal(p.uploads.length, 1);
        const xhr = p.uploads[0];
        assert.equal(xhr.method, 'POST'); assert.equal(xhr.url, '/ota');
        assert.equal(xhr.headers['hyperk-ota-firmware-size'], String(file.size));
        assert.equal(xhr.headers['hyperk-ota-firmware-name'], 'OTA_Hyperk_local_esp32s3.bin');
        const sent = xhr.data.get('update');
        assert.equal(sent.name, file.name);
        assert.deepEqual(new Uint8Array(await sent.arrayBuffer()), new Uint8Array(await file.arrayBuffer()));
        assert(p.w.document.querySelector('button[type="submit"]').disabled);
        assert(p.w.onbeforeunload());
        xhr.upload.onprogress({ lengthComputable: true, loaded: 100, total: 100 });
        assert.match(p.status().textContent, /wird geprüft/);
        assert.equal(p.toasts.length, 0);
        xhr.respond(200, 'Ok'); await tick();
        assert.deepEqual(p.toasts, [true]);
        assert.match(p.status().textContent, /erfolgreich/);
        assert.equal(p.install().disabled, true);
        assert.equal(p.w.onbeforeunload(), undefined);
    } finally { p.dom.window.close(); }
});

integration('factory, wrong-chip, bootloader, oversized and incomplete files are rejected before upload', async () => {
    const p = await openOta();
    try {
        for (const [name, options, expected] of [
            ['Hyperk_esp32s3_factory.bin', {}, /Factory/],
            ['OTA_esp32c3.bin', { chip: 5 }, /ESP32-S3/],
            ['renamed-factory.bin', {}, /Factory/],
            ['firmware.bin', { appMagic: 0 }, /Anwendungsfirmware/],
            ['firmware.bin', { magic: 0 }, /ESP32-S3/],
            ['firmware.bin', { size: 0 }, /unvollständig/],
            ['firmware.bin', { size: 0x1D0001 }, /zu groß/],
            ['firmware.txt', {}, /OTA-BIN/]
        ]) {
            p.choose(name, options); await p.start();
            assert.equal(p.modal.open, false);
            assert.equal(p.uploads.length, 0);
            assert.match(p.status().textContent, expected);
            assert.equal(p.status().getAttribute('role'), 'alert');
            assert.equal(p.install().disabled, false);
        }
    } finally { p.dom.window.close(); }
});

integration('cancel and Escape dismiss confirmation without writing firmware', async () => {
    const p = await openOta();
    try {
        for (const escape of [false, true]) {
            p.choose(); await p.start();
            assert(p.modal.open);
            if (escape) p.modal.dispatchEvent(new p.w.Event('cancel', { cancelable: true }));
            else p.w.closeConfirm(false);
            await tick();
            assert.equal(p.modal.open, false);
            assert.equal(p.uploads.length, 0);
            assert.equal(p.install().disabled, false);
        }
    } finally { p.dom.window.close(); }
});

integration('HTTP errors, a FAIL body, network errors, abort and timeout restore controls for retry', async () => {
    const p = await openOta();
    try {
        for (const failure of ['http', 'body', 'network', 'abort', 'timeout']) {
            p.choose(); await p.start(); p.w.closeConfirm(true); await tick();
            const xhr = p.uploads.at(-1);
            if (failure === 'http') xhr.respond(500, 'FAIL');
            else if (failure === 'body') xhr.respond(200, 'FAIL');
            else if (failure === 'network') xhr.onerror();
            else if (failure === 'abort') xhr.onabort();
            else xhr.ontimeout();
            await tick();
            assert.equal(p.toasts.length, 0);
            assert.equal(p.status().getAttribute('role'), 'alert');
            assert.equal(p.install().disabled, false);
            assert.equal(p.fileInput().disabled, false);
            assert.equal(p.w.document.querySelector('button[type="submit"]').disabled, false);
            assert.equal(p.w.onbeforeunload(), undefined);
        }
    } finally { p.dom.window.close(); }
});

integration('local and official updates cannot overlap and saving settings is blocked during local upload', async () => {
    const p = await openOta();
    try {
        p.choose();
        await p.w.checkFirmwareUpdates();
        const remote = p.w.startOtaUpdate();
        assert(p.modal.open);
        p.install().click();
        assert.equal(p.uploads.length, 0);
        p.w.closeConfirm(false); await remote;
        await p.start();
        await p.w.startOtaUpdate();
        assert(p.modal.open);
        p.w.closeConfirm(true); await tick();
        p.install().click();
        await p.w.startOtaUpdate();
        assert.equal(p.uploads.length, 1);
        const submit = new p.w.Event('submit', { bubbles: true, cancelable: true });
        p.page.closest('form').dispatchEvent(submit);
        assert(submit.defaultPrevented);
        p.uploads[0].respond(); await tick();
    } finally { p.dom.window.close(); }
});

integration('official update still uses its native download and upload path', async () => {
    const p = await openOta();
    try {
        p.choose(); await p.w.checkFirmwareUpdates();
        const remote = p.w.startOtaUpdate();
        p.w.closeConfirm(true); await remote;
        assert.equal(p.uploads.length, 1);
        assert.equal(p.uploads[0].headers['hyperk-ota-firmware-name'], 'OTA_Hyperk_0.0.6_esp32s3.bin');
        assert(p.install().disabled);
        p.uploads[0].respond(); await tick();
        assert.deepEqual(p.toasts, [true]);
    } finally { p.dom.window.close(); }
});

integration('OTA initializes when the original script arrives after onload, and reports backend errors', async () => {
    const p = await openOta({ delayBackend: true });
    try {
        assert.equal(p.install(), null);
        p.releaseBackend(); await p.initialized;
        assert(p.install());
    } finally { p.dom.window.close(); }
    const failed = await openOta({ sourceError: true });
    try {
        assert.equal(failed.install(), null);
        assert.match(failed.page.querySelector('[role="alert"]').textContent, /HTTP 503/);
    } finally { failed.dom.window.close(); }
});
