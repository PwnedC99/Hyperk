const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');
const fixtures = process.env.HYPERK_BACKEND_FIXTURES;
const root = path.join(__dirname, '..');
const tick = () => new Promise(setImmediate);

function state(enabled = false) {
    return { peripheral: { gpio: 1, enabled, storage_ready: true }, build_id: 'test-build',
        wifi: { connected: true, ap_active: false, ip: '192.0.2.2', channel: 6, rssi_dbm: -54,
            configured_tx_dbm: 17, driver_tx_limit_dbm: 16.5, low_latency: true,
            disconnect_count: 0, last_disconnect_text: 'Noch kein Abbruch', last_disconnect_reason: 0 } };
}
async function openSettings(config, savedState = state(), failPost = false) {
    const html = fs.readFileSync(path.join(fixtures, 'settings.html'), 'utf8');
    const hardware = fs.readFileSync(path.join(fixtures, 'settings_led_hardware.html'), 'utf8');
    const backend = fs.readFileSync(path.join(fixtures, 'settings_led_hardware.js'), 'utf8');
    const dom = new JSDOM(html, { runScripts: 'outside-only', url: 'http://hyperk.local/settings.html' });
    const w = dom.window;
    w.config = config;
    w.document.getElementById('led_hardware_page').insertAdjacentHTML('beforeend', hardware);
    const helperStart = html.indexOf('function setupPageControls');
    w.eval(html.slice(helperStart, html.indexOf('async function loadCurrentConfig', helperStart)));
    const posts = [];
    w.fetch = async (url, options = {}) => {
        if (String(url).includes('settings_led_hardware.js')) return { ok: true, text: async () => backend };
        if (String(url) === '/api/peripheral') {
            posts.push(String(options.body));
            if (failPost) return { ok: false, status: 503, json: async () => ({ error: 'Speicherung fehlgeschlagen' }) };
            savedState.peripheral.enabled = new URLSearchParams(options.body).get('enabled') === '1';
        }
        return { ok: true, json: async () => structuredClone(savedState) };
    };
    Object.defineProperty(w.document, 'currentScript', { get: () => ({ src: 'http://hyperk.local/settings_led_hardware.js?v=0.0.5' }) });
    const append = w.document.head.appendChild.bind(w.document.head);
    w.document.head.appendChild = script => {
        const element = append(script);
        if (script.src) {
            w.eval(fs.readFileSync(path.join(root, 'data/board_controls.js'), 'utf8'));
            script.onload();
        } else w.eval(script.textContent);
        return element;
    };
    w.eval(fs.readFileSync(path.join(root, 'data/s3_gpio_extension.js'), 'utf8'));
    await w.setupLedHardware();
    await tick();
    return { dom, w, posts, savedState };
}
const config = (type = '0') => ({ architecture: 'ESP32-S3', type, numLeds: 100, segmentSupported: 4,
    segments: [{ data: 37, clock: type === '2' ? 38 : 0, startIndex: 0 }] });
const integration = (name, fn) => test(name, { skip: !fixtures }, fn);

integration('real backend: GPIO37/38 survive segment editing and reload; GPIO1 is reserved', async () => {
    const cfg = config();
    cfg.segments.push({ data: 38, clock: 0, startIndex: 50 });
    let page = await openSettings(cfg);
    try {
        const first = page.w.document.querySelector('[name="dataPin0"]');
        assert.equal(first.value, '37');
        assert(![...first.options].some(option => option.value === '1' || option.value === '38'));
        page.w.document.getElementById('addSegmentBtn').click();
        assert.equal(cfg.segments.length, 3);
        assert.equal(page.w.document.querySelector('[name="dataPin1"]').value, '38');
    } finally { page.dom.window.close(); }
    page = await openSettings(JSON.parse(JSON.stringify(cfg)));
    try { assert.equal(page.w.document.querySelector('[name="dataPin0"]').value, '37'); }
    finally { page.dom.window.close(); }
});

integration('real backend: SPI data/clock retain GPIO37/38 and relay GPIO1 is invalid', async () => {
    const page = await openSettings(config('2'));
    try {
        const form = page.w.document.querySelector('form[action="/save_config"]');
        const fields = new page.w.FormData(form);
        assert.equal(fields.get('dataPin0'), '37');
        assert.equal(fields.get('clockPin0'), '38');
        const relay = page.w.document.querySelector('[name="relay-gpio"]');
        relay.value = '1'; relay.dispatchEvent(new page.w.Event('input'));
        assert.equal(relay.checkValidity(), false);
        relay.value = '2'; relay.dispatchEvent(new page.w.Event('input'));
        assert.equal(relay.checkValidity(), true);
    } finally { page.dom.window.close(); }
});

integration('peripheral button sends an explicit desired state and shows separate TX/RSSI values', async () => {
    const page = await openSettings(config());
    try {
        const button = page.w.document.querySelector('[data-peripheral-toggle]');
        assert.equal(button.type, 'checkbox');
        assert.equal(button.getAttribute('role'), 'switch');
        assert.equal(button.checked, false);
        assert(button.closest('.toggleContainer'));
        assert.equal(button.closest('[data-board-panel]').tagName, 'DIV');
        button.click(); await tick();
        assert.deepEqual(page.posts, ['enabled=1']);
        assert.equal(button.checked, true);
        assert.match(page.w.document.querySelector('[data-wifi-diagnostics]').textContent, /17 dBm.*16.5 dBm/);
        button.click(); await tick();
        assert.deepEqual(page.posts, ['enabled=1', 'enabled=0']);
    } finally { page.dom.window.close(); }
});

integration('saved enabled state is reflected after a page reload', async () => {
    const saved = state(true);
    const page = await openSettings(config(), saved);
    try { assert.equal(page.w.document.querySelector('[data-peripheral-toggle]').checked, true); }
    finally { page.dom.window.close(); }
});

integration('failed peripheral writes remain visible and never show an enabled output', async () => {
    const page = await openSettings(config(), state(false), true);
    try {
        const button = page.w.document.querySelector('[data-peripheral-toggle]');
        button.click(); await tick();
        assert.equal(button.checked, false);
        const error = page.w.document.querySelector('[data-board-error]');
        assert.equal(error.hidden, false);
        assert.match(error.textContent, /Speicherung fehlgeschlagen/);
    } finally { page.dom.window.close(); }
});
