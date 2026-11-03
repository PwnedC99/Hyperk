(() => {
    // Keep the backend script and all its controls; extend only the S3 pin list.
    const sourceUrl = new URL(document.currentScript.src);
    sourceUrl.searchParams.set('hyperk_original', '1');

    const boardReady = new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = '/board_controls.js';
        script.onload = resolve;
        script.onerror = () => reject(new Error('Board controls failed to load'));
        document.head.appendChild(script);
    });
    const backendReady = fetch(sourceUrl, { cache: 'no-store' })
        .then(response => {
            if (!response.ok) throw new Error(`LED settings: HTTP ${response.status}`);
            return response.text();
        })
        .then(source => {
            let matches = 0;
            const extended = source.replace(/("ESP32-S3"\s*:\s*\{\s*gpio\s*:\s*\[)([^\]]*)(\])/g,
                (match, prefix, values, suffix) => {
                    matches++;
                    const pins = values.split(',').map(value => Number(value.trim()));
                    if (!pins.every(Number.isInteger)) throw new Error('Invalid ESP32-S3 GPIO list');
                    return prefix + [...new Set([...pins.filter(pin => pin !== 1), 37, 38])].sort((a, b) => a - b).join(',') + suffix;
                });
            if (matches !== 1) throw new Error('Unsupported backend: ESP32-S3 GPIO list not found');

            const script = document.createElement('script');
            script.textContent = extended;
            document.head.appendChild(script);
            script.remove();
            if (window.setupLedHardware === initialize) throw new Error('LED settings failed to load');
            const setup = window.setupLedHardware;
            if (typeof setup !== 'function') throw new Error('LED settings initializer missing');
            window.setupLedHardware = initialize;
            return setup;
        });

    const ready = Promise.all([backendReady, boardReady]).then(([setup]) => {
        const wrapped = (...args) => {
            const result = setup(...args);
            window.HyperkBoard.mount(document.getElementById('led_hardware_page'));
            return result;
        };
        window.setupLedHardware = wrapped;
        return wrapped;
    });

    // The settings page calls this on script.onload, before fetch may complete.
    function initialize() {
        return ready.then(setup => setup()).catch(error => {
            console.error(error);
            const message = document.createElement('p');
            message.setAttribute('role', 'alert');
            message.textContent = 'Could not load LED settings. Reload the page. ' + error.message;
            document.getElementById('led_hardware_page').appendChild(message);
        });
    }
    window.setupLedHardware = initialize;
})();
