(function () {
    'use strict';

    var wrapper = document.getElementById('player-wrapper');
    if (!wrapper) return;

    var video = document.getElementById('video-player');
    var cinemaLoading = document.getElementById('cinema-loading');
    var streamUrl = wrapper.dataset.streamUrl;
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

    if (window.FlowPremiumAudio) {
        window.FlowPremiumAudio.init(video, audioManifest, streamUrl, episodeId);
    } else if (streamUrl) {
        video.src = streamUrl;
        video.load();
    }

    if (window.FlowPremiumSubtitles) {
        window.FlowPremiumSubtitles.init(video, episodeId, document.getElementById('btn-cc'));
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
        if (cinemaLoading) cinemaLoading.classList.remove('is-hidden');
    });

    video.addEventListener('canplay', function () {
        if (cinemaLoading) cinemaLoading.classList.add('is-hidden');
        logVideo('canplay', { duration: video.duration, readyState: video.readyState });
    });

    video.addEventListener('waiting', function () {
        if (cinemaLoading) cinemaLoading.classList.remove('is-hidden');
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
        if (startPos > 0 && video.duration && startPos < video.duration - 5) {
            video.currentTime = startPos;
        }
    });

    video.addEventListener('timeupdate', function () {
        scheduleSave();
    });

    video.addEventListener('ended', function () {
        saveProgress(video.duration, true);
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
