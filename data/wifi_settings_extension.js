(() => {
    const sourceUrl = new URL(document.currentScript.src);
    sourceUrl.searchParams.set('hyperk_original', '1');
    const controlsReady = window.HyperkBoard ? Promise.resolve() : new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = '/board_controls.js';
        script.onload = resolve;
        script.onerror = () => reject(new Error('Settings controls failed to load'));
        document.head.appendChild(script);
    });
    const backendReady = fetch(sourceUrl, { cache: 'no-store' }).then(async response => {
        if (!response.ok) throw new Error(`WiFi settings: HTTP ${response.status}`);
        const script = document.createElement('script');
        script.textContent = await response.text();
        document.head.appendChild(script);
        script.remove();
        const setup = window.setupWifi;
        if (typeof setup !== 'function' || setup === initialize) throw new Error('WiFi initializer missing');
        window.setupWifi = initialize;
        return setup;
    });
    const ready = Promise.all([backendReady, controlsReady]);
    function initialize() {
        return ready.then(([setup]) => {
            setup();
            window.HyperkBoard.installSettingsSaver();
        }).catch(error => {
            const message = document.createElement('p');
            message.setAttribute('role', 'alert');
            message.textContent = 'WLAN-Einstellungen konnten nicht geladen werden. ' + error.message;
            document.getElementById('wifi_configuration_page').appendChild(message);
        });
    }
    window.setupWifi = initialize;
})();
