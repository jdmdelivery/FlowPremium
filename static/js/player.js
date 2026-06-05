(function () {
    'use strict';

    var wrapper = document.getElementById('player-wrapper');
    if (!wrapper) return;

    var video = document.getElementById('video-player');
    var cinemaLoading = document.getElementById('cinema-loading');
    var streamUrl = wrapper.dataset.streamUrl;
    var fallbackDuration = parseFloat(wrapper.dataset.duration || '0');
    var audioManifest = null;

    try {
        var manifestEl = document.getElementById('player-audio-manifest');
        audioManifest = manifestEl ? JSON.parse(manifestEl.textContent || '{}') : null;
    } catch (e) {
        audioManifest = null;
    }

    var progressUrl = wrapper.dataset.progressUrl;
    var episodeId = parseInt(wrapper.dataset.episodeId, 10);
    var startPos = parseFloat(wrapper.dataset.start || '0');
    var saveTimer = null;
    var lastSaved = 0;

    function formatTime(sec) {
        if (!isFinite(sec) || sec < 0) sec = 0;
        var m = Math.floor(sec / 60);
        var s = Math.floor(sec % 60);
        return m + ':' + (s < 10 ? '0' : '') + s;
    }

    function applyDurationFallback() {
        var durEl = document.getElementById('dw-time-duration');
        if (!durEl || !fallbackDuration) return;
        if (!isFinite(video.duration) || video.duration <= 0) {
            durEl.textContent = formatTime(fallbackDuration);
        }
    }

    if (streamUrl && video) {
        video.src = streamUrl;
        video.load();
    }

    if (cinemaLoading) {
        cinemaLoading.classList.add('is-hidden');
    }

    applyDurationFallback();

    if (window.FlowPremiumPlayer) {
        window.FlowPremiumPlayer.init(video, episodeId, streamUrl);
    } else if (window.FlowPremiumAudio) {
        window.FlowPremiumAudio.init(video, audioManifest, streamUrl, episodeId);
        if (window.FlowPremiumSubtitles) {
            window.FlowPremiumSubtitles.init(video, episodeId, document.getElementById('dw-btn-subtitles'));
        }
    }

    function logVideo(msg, detail) {
        if (detail !== undefined) {
            console.info('[FlowPremium Video]', msg, detail);
        } else {
            console.info('[FlowPremium Video]', msg);
        }
    }

    function logVideoError(msg, detail) {
        if (detail !== undefined) {
            console.error('[FlowPremium Video]', msg, detail);
        } else {
            console.error('[FlowPremium Video]', msg);
        }
    }

    logVideo('stream url', streamUrl);

    video.addEventListener('loadstart', function () {
        if (cinemaLoading && video.readyState < 2) {
            cinemaLoading.classList.remove('is-hidden');
        }
    });

    video.addEventListener('canplay', function () {
        if (cinemaLoading) cinemaLoading.classList.add('is-hidden');
        logVideo('canplay', { duration: video.duration, readyState: video.readyState });
        applyDurationFallback();
    });

    video.addEventListener('waiting', function () {
        if (cinemaLoading && !video.paused) {
            cinemaLoading.classList.remove('is-hidden');
        }
    });

    video.addEventListener('playing', function () {
        if (cinemaLoading) cinemaLoading.classList.add('is-hidden');
    });

    video.addEventListener('stalled', function () {
        logVideoError('stalled', { networkState: video.networkState, readyState: video.readyState });
    });

    video.addEventListener('error', function () {
        var err = video.error;
        logVideoError('playback error', {
            code: err ? err.code : null,
            message: err ? err.message : null,
            src: video.currentSrc || video.src
        });
        if (cinemaLoading) cinemaLoading.classList.add('is-hidden');
    });

    video.addEventListener('loadedmetadata', function () {
        logVideo('loadedmetadata', { duration: video.duration });
        applyDurationFallback();
        if (startPos > 0) {
            var total = isFinite(video.duration) && video.duration > 0
                ? video.duration
                : fallbackDuration;
            if (total && startPos < total - 5) {
                video.currentTime = startPos;
            }
        }
    });

    video.addEventListener('durationchange', applyDurationFallback);

    video.addEventListener('timeupdate', function () {
        scheduleSave();
    });

    video.addEventListener('ended', function () {
        saveProgress(video.duration || fallbackDuration, true);
        var nextUrl = wrapper.dataset.nextUrl;
        if (nextUrl) {
            setTimeout(function () { window.location.href = nextUrl; }, 2000);
        }
    });

    window.addEventListener('beforeunload', function () {
        if (video.currentTime > 0) {
            saveProgress(video.currentTime, false, true);
        }
    });

    function scheduleSave() {
        clearTimeout(saveTimer);
        saveTimer = setTimeout(function () {
            if (Math.abs(video.currentTime - lastSaved) >= 10) {
                saveProgress(video.currentTime, false);
            }
        }, 5000);
    }

    function saveProgress(position, completed, sync) {
        if (!progressUrl || !episodeId) return;
        lastSaved = position;
        var payload = JSON.stringify({
            episode_id: episodeId,
            position_seconds: Math.floor(position),
            completed: completed
        });
        if (sync && navigator.sendBeacon) {
            navigator.sendBeacon(progressUrl, new Blob([payload], { type: 'application/json' }));
            return;
        }
        fetch(progressUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: payload,
            credentials: 'same-origin'
        }).catch(function () {});
    }
})();
