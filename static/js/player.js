(function () {
    'use strict';

    var wrapper = document.getElementById('player-wrapper');
    if (!wrapper) return;

    var video = document.getElementById('video-player');
    var cinemaLoading = document.getElementById('cinema-loading');
    var streamUrl = wrapper.dataset.streamUrl;
    var progressUrl = wrapper.dataset.progressUrl;
    var episodeId = parseInt(wrapper.dataset.episodeId, 10);
    var startPos = parseFloat(wrapper.dataset.start || '0');
    var saveTimer = null;
    var lastSaved = 0;

    function readManifest() {
        var el = document.getElementById('player-playback-manifest');
        if (!el) return {};
        try { return JSON.parse(el.textContent || '{}'); } catch (e) { return {}; }
    }

    function showSpinner() {
        if (cinemaLoading) cinemaLoading.classList.remove('is-hidden');
    }

    function hideSpinner() {
        if (cinemaLoading) cinemaLoading.classList.add('is-hidden');
    }

    hideSpinner();

    if (window.FlowPremiumPlayer) {
        window.FlowPremiumPlayer.init(video, episodeId, streamUrl);
    } else if (streamUrl) {
        video.src = streamUrl;
        video.load();
    }

    video.addEventListener('loadstart', function () {
        if (video.readyState < 2) showSpinner();
    });

    video.addEventListener('canplay', hideSpinner);
    video.addEventListener('playing', hideSpinner);

    video.addEventListener('waiting', function () {
        if (!video.paused && video.readyState < 3) showSpinner();
    });

    video.addEventListener('error', hideSpinner);

    video.addEventListener('loadedmetadata', function () {
        if (startPos > 0) {
            var total = video.duration;
            if (isFinite(total) && total > 0 && startPos < total - 5) {
                video.currentTime = startPos;
            }
        }
        hideSpinner();
    });

    video.addEventListener('timeupdate', scheduleSave);
    video.addEventListener('ended', function () {
        saveProgress(video.duration || 0, true);
        var nextUrl = wrapper.dataset.nextUrl;
        if (nextUrl) setTimeout(function () { window.location.href = nextUrl; }, 2000);
    });

    window.addEventListener('beforeunload', function () {
        if (video.currentTime > 0) saveProgress(video.currentTime, false, true);
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
