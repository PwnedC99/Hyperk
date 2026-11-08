const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');
const tick = () => new Promise(setImmediate);
const source = fs.readFileSync(path.join(__dirname, '../data/board_controls.js'), 'utf8');

function page(reply, hardware = false) {
    const dom = new JSDOM(`<form action="/save_wifi"><select id="ssid_select" name="ssid"><option value="home">home</option></select>
        <input id="ssid_custom" name="ssid_custom"><input name="password" value="secret"><button type="submit">Save</button></form>
        <form action="/save_config"><div id="led_hardware_page" ${hardware ? 'data-loaded="true"' : ''}></div>
        <input name="numLeds" value="258"><button type="button">Add segment</button><button type="submit">Save Settings</button></form>`,
        { runScripts: 'outside-only', url: 'http://hyperk.local/settings.html' });
    const w = dom.window;
    const requests = [], toasts = [], alerts = [];
    let nativeSubmits = 0;
    w.config = { segments: [{ startIndex: 0, data: 37, clock: 0 }, { startIndex: 129, data: 38, clock: 0, reversed: true }] };
    w.validateSegments = () => true;
    w.clearErrors = () => {};
    w.showToast = reboot => toasts.push(reboot);
    w.alert = text => alerts.push(text);
    for (const form of w.document.forms) form.addEventListener('submit', () => { nativeSubmits++; });
    w.fetch = async (url, options) => {
        requests.push({ url, body: new URLSearchParams(String(options.body)) });
        return typeof reply === 'function' ? reply() : reply;
    };
    w.eval(source);
    function submit(action) {
        const form = w.document.querySelector(`form[action="${action}"]`);
        form.dispatchEvent(new w.Event('submit', { bubbles: true, cancelable: true }));
        return form;
    }
    return { dom, w, submit, requests, toasts, alerts, nativeSubmits: () => nativeSubmits };
}

test('failed settings save shows storage reason and never claims success or reboots', async () => {
    const p = page({ ok: false, status: 503, text: async () => '{"error":"written_config_invalid"}' }, true);
    try {
        const form = p.submit('/save_config'); await tick();
        assert.match(form.querySelector('[data-config-save-status]').textContent, /unvollständig oder ungültig/);
        assert.equal(form.querySelector('[data-config-save-status]').getAttribute('role'), 'alert');
        assert.deepEqual(p.toasts, []); assert.deepEqual(p.alerts, []);
        assert.equal(p.nativeSubmits(), 0);
        assert.equal(form.querySelector('button[type="submit"]').disabled, false);
        assert.equal(p.requests[0].body.get('segments'), '0,37,0,0,129,38,0,1');
    } finally { p.dom.window.close(); }
});

test('successful settings save preserves segment payload and reports confirmed success', async () => {
    const p = page({ ok: true, text: async () => '{"status":"saved"}' }, true);
    try {
        const form = p.submit('/save_config'); await tick();
        assert.match(form.querySelector('[data-config-save-status]').textContent, /gespeichert/);
        assert.deepEqual(p.toasts, [false]); assert.equal(p.nativeSubmits(), 0);
        assert.equal(p.requests[0].body.get('numLeds'), '258');
    } finally { p.dom.window.close(); }
});

test('WiFi storage error remains on the page with no successful restart message', async () => {
    const p = page({ ok: false, status: 503, text: async () => '{"error":"filesystem_not_mounted"}' });
    try {
        const form = p.submit('/save_wifi'); await tick();
        assert.match(form.querySelector('[data-config-save-status]').textContent, /Dateisystem ist nicht verfügbar/);
        assert.deepEqual(p.toasts, []);
        assert.equal(p.requests[0].body.get('ssid'), 'home');
        assert.equal(p.requests[0].body.get('password'), 'secret');
    } finally { p.dom.window.close(); }
});

test('WiFi success accepts the native HTML response and reports the restart', async () => {
    const p = page({ ok: true, text: async () => '<html>Rebooting...</html>' });
    try {
        const form = p.submit('/save_wifi'); await tick();
        assert.match(form.querySelector('[data-config-save-status]').textContent, /Gerät startet neu/);
        assert.deepEqual(p.toasts, [true]);
    } finally { p.dom.window.close(); }
});

test('network failures are visible; duplicate submissions and installs do not duplicate writes', async () => {
    let resolve;
    const response = new Promise(done => { resolve = done; });
    const p = page(() => response);
    try {
        p.w.HyperkBoard.installSettingsSaver();
        const form = p.submit('/save_config'); p.submit('/save_config');
        assert.equal(p.requests.length, 1);
        resolve({ ok: false, status: 500, text: async () => 'failure' }); await tick();
        assert.match(form.querySelector('[data-config-save-status]').textContent, /HTTP 500/);
        p.w.fetch = async () => { throw new Error('Connection lost'); };
        p.submit('/save_config'); await tick();
        assert.match(form.querySelector('[data-config-save-status]').textContent, /Connection lost/);
        assert.deepEqual(p.toasts, []);
    } finally { p.dom.window.close(); }
});

const fixtures = process.env.HYPERK_BACKEND_FIXTURES;
test('real WiFi backend loader keeps native field names and exposes storage failure', { skip: !fixtures }, async () => {
    const html = fs.readFileSync(path.join(fixtures, 'settings_wifi.html'), 'utf8');
    const backend = fs.readFileSync(path.join(fixtures, 'settings_wifi.js'), 'utf8');
    const dom = new JSDOM(`<form action="/save_wifi"><div id="wifi_configuration_page">${html}</div></form>`,
        { runScripts: 'outside-only', url: 'http://hyperk.local/settings.html' });
    const w = dom.window;
    let payload;
    w.scanInterval = 12000;
    w.showToast = () => assert.fail('Storage failure must not report success');
    w.fetch = async (url, options = {}) => {
        if (String(url).includes('settings_wifi.js')) return { ok: true, text: async () => backend };
        if (String(url).includes('/api/wifi_scan')) return { status: 200, json: async () => [{ ssid: 'home', rssi: -50 }] };
        if (String(url).endsWith('/save_wifi')) {
            payload = new URLSearchParams(String(options.body));
            return { ok: false, status: 503, text: async () => '{"error":"config_commit_failed"}' };
        }
        throw new Error(`Unexpected request: ${url}`);
    };
    Object.defineProperty(w.document, 'currentScript', { get: () => ({ src: 'http://hyperk.local/settings_wifi.js?v=0.0.5' }) });
    const append = w.document.head.appendChild.bind(w.document.head);
    w.document.head.appendChild = script => {
        const result = append(script);
        if (script.src) { w.eval(source); script.onload(); }
        else w.eval(script.textContent);
        return result;
    };
    try {
        w.eval(fs.readFileSync(path.join(__dirname, '../data/wifi_settings_extension.js'), 'utf8'));
        await w.setupWifi(); await tick();
        w.document.getElementById('ssid_select').value = 'home';
        w.document.querySelector('[name="pass"]').value = 'secret';
        const form = w.document.forms[0];
        form.dispatchEvent(new w.Event('submit', { bubbles: true, cancelable: true })); await tick();
        assert.equal(payload.get('ssid'), 'home'); assert.equal(payload.get('pass'), 'secret');
        assert.match(form.querySelector('[data-config-save-status]').textContent, /konnte nicht übernommen werden/);
        assert.equal(form.querySelector('button[type="submit"]').disabled, false);
    } finally { dom.window.close(); }
});
