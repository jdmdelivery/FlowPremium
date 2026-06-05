/**
 * HLS playback: native on iOS Safari, hls.js on Android/Chrome/PC.
 */
(function (global) {
    'use strict';

    var hlsInstance = null;

    function isIosSafari() {
        return /iPhone|iPad|iPod/i.test(navigator.userAgent);
    }

    function shouldUseHlsJs() {
        return global.Hls && global.Hls.isSupported() && !isIosSafari();
    }

    function destroyHls() {
        if (hlsInstance) {
            try {
                hlsInstance.destroy();
            } catch (e) { /* ignore */ }
            hlsInstance = null;
        }
    }

    function getLevels(hls) {
        if (!hls || !hls.levels) return [];
        return hls.levels.map(function (level, index) {
            var h = level.height || 0;
            return {
                id: String(h || index),
                index: index,
                label: h ? h + 'P' : 'Level ' + (index + 1),
                height: h,
            };
        });
    }

    function setup(video, masterUrl, callbacks) {
        callbacks = callbacks || {};
        destroyHls();

        if (!masterUrl) {
            return null;
        }

        if (shouldUseHlsJs()) {
            hlsInstance = new global.Hls({
                enableWorker: true,
                lowLatencyMode: false,
            });
            hlsInstance.loadSource(masterUrl);
            hlsInstance.attachMedia(video);
            hlsInstance.on(global.Hls.Events.MANIFEST_PARSED, function () {
                var levels = getLevels(hlsInstance);
                if (callbacks.onReady) {
                    callbacks.onReady({ mode: 'hls.js', levels: levels, hls: hlsInstance });
                }
            });
            hlsInstance.on(global.Hls.Events.ERROR, function (event, data) {
                if (data.fatal && callbacks.onError) {
                    callbacks.onError(data);
                }
            });
            return { mode: 'hls.js', hls: hlsInstance };
        }

        if (video.canPlayType('application/vnd.apple.mpegurl')) {
            video.src = masterUrl;
            video.addEventListener('loadedmetadata', function onMeta() {
                video.removeEventListener('loadedmetadata', onMeta);
                if (callbacks.onReady) {
                    callbacks.onReady({ mode: 'native', levels: [], hls: null });
                }
            });
            return { mode: 'native', hls: null };
        }

        if (callbacks.onError) {
            callbacks.onError({ type: 'unsupported' });
        }
        return null;
    }

    function setQuality(hls, levelIndex) {
        if (!hls) return;
        if (levelIndex < 0) {
            hls.currentLevel = -1;
            return;
        }
        hls.currentLevel = levelIndex;
    }

    global.FlowPremiumHls = {
        setup: setup,
        destroy: destroyHls,
        getLevels: getLevels,
        setQuality: setQuality,
        shouldUseHlsJs: shouldUseHlsJs,
        isIosSafari: isIosSafari,
    };
})(window);
