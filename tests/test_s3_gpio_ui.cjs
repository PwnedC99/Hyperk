const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const extension = fs.readFileSync(path.join(__dirname, '../data/s3_gpio_extension.js'), 'utf8');

function backend(pins = '1,2,4,5,6,7,8,10,16,17,18,48') {
    return `
        function setupLedHardware() { return setupPinValidator(); }
        function setupPinValidator() {
            const hardwareLimits = {
                "ESP32-S3": { gpio: [${pins}], spi: { data: [5], clock: [4] } },
                "ESP32-S2": { gpio: [1,2,4] }
            };
            return hardwareLimits;
        }
    `;
}

function browser(response) {
    const errors = [];
    const alerts = [];
    let fetched;
    const context = vm.createContext({
        URL,
        console: { error: error => errors.push(error) },
        fetch: (url, options) => {
            fetched = { url, options };
            return response;
        },
        document: {
            currentScript: { src: 'http://hyperk.local/settings_led_hardware.js?v=0.0.5' },
            createElement: () => ({ setAttribute() {}, remove() {} }),
            head: { appendChild: script => {
                if (script.src) { context.HyperkBoard = { mount() {} }; script.onload(); }
                else vm.runInContext(script.textContent, context);
            } },
            getElementById: () => ({ appendChild: element => alerts.push(element.textContent) })
        }
    });
    context.window = context;
    vm.runInContext(extension, context);
    return { context, errors, alerts, get fetched() { return fetched; } };
}

const ok = source => ({ ok: true, text: async () => source });

test('waits for backend loading and extends data/clock pins without changing other chips', async () => {
    let resolve;
    const page = browser(new Promise(done => { resolve = done; }));
    const pending = page.context.setupLedHardware();
    resolve(ok(backend()));
    const limits = await pending;
    assert.deepEqual(Array.from(limits['ESP32-S3'].gpio), [2,4,5,6,7,8,10,16,17,18,37,38,48]);
    assert.deepEqual(Array.from(limits['ESP32-S3'].spi.data), [5]);
    assert.deepEqual(Array.from(limits['ESP32-S2'].gpio), [1,2,4]);
    assert.equal(page.errors.length, 0);
    assert.equal(page.fetched.url.searchParams.get('hyperk_original'), '1');
    assert.equal(page.fetched.url.searchParams.get('v'), '0.0.5');
    assert.equal(page.fetched.options.cache, 'no-store');
});

test('also initializes when backend loading finishes before the page onload callback', async () => {
    const page = browser(Promise.resolve(ok(backend())));
    await new Promise(setImmediate);
    assert.equal(page.context.setupLedHardware()['ESP32-S3'].gpio.includes(37), true);
});

test('does not duplicate GPIOs already present in a newer backend', async () => {
    const page = browser(Promise.resolve(ok(backend('1,37,38,48'))));
    const limits = await page.context.setupLedHardware();
    assert.deepEqual(Array.from(limits['ESP32-S3'].gpio), [37,38,48]);
});

test('reports an incompatible backend instead of silently running an incomplete UI', async () => {
    const page = browser(Promise.resolve(ok('function setupLedHardware() {}')));
    await page.context.setupLedHardware();
    assert.match(page.alerts[0], /Unsupported backend/);
});

test('reports HTTP and network errors in the settings page', async () => {
    for (const response of [
        Promise.resolve({ ok: false, status: 404 }),
        Promise.reject(new Error('Network unavailable'))
    ]) {
        const page = browser(response);
        await page.context.setupLedHardware();
        assert.equal(page.alerts.length, 1);
        assert.equal(page.errors.length, 1);
    }
});
