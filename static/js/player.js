(function () {
    'use strict';

    var wrapper = document.getElementById('player-wrapper');
    if (!wrapper) return;

    var video = document.getElementById('video-player');
    var btnPlay = document.getElementById('btn-play');
    var progressBar = document.getElementById('progress-bar');
    var timeCurrent = document.getElementById('time-current');
    var timeDuration = document.getElementById('time-duration');
    var timeRemaining = document.getElementById('time-remaining');
    var btnFullscreen = document.getElementById('btn-fullscreen');
    var btnCc = document.getElementById('btn-cc');
    var cinemaControls = document.getElementById('cinema-controls');
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
    var remainingLabel = timeRemaining ? timeRemaining.textContent.split('0:00')[0] : ' · ';

    var saveTimer = null;
    var lastSaved = 0;
    var controlsTimer = null;

    if (window.FlowPremiumAudio) {
        window.FlowPremiumAudio.init(video, audioManifest, streamUrl, episodeId);
    } else {
        video.src = streamUrl;
    }

    if (window.FlowPremiumSubtitles) {
        window.FlowPremiumSubtitles.init(video, episodeId, btnCc);
    }

    var btnAudio = document.getElementById('btn-audio');
    var audioTrackBar = document.getElementById('audio-track-bar');
    if (btnAudio && audioTrackBar) {
        btnAudio.addEventListener('click', function (e) {
            e.stopPropagation();
            audioTrackBar.classList.toggle('is-open');
            btnAudio.classList.toggle('is-active');
        });
    }

    /* Mobile: attempt landscape-friendly fullscreen on play */
    var isMobile = /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent);

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
        logVideo('loadstart');
    });

    video.addEventListener('canplay', function () {
        if (cinemaLoading) cinemaLoading.classList.add('is-hidden');
        logVideo('canplay', { duration: video.duration, readyState: video.readyState });
    });

    video.addEventListener('stalled', function () {
        logVideoError('stalled — waiting for data', {
            networkState: video.networkState,
            readyState: video.readyState,
            currentTime: video.currentTime
        });
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

    video.addEventListener('loadedmetadata', function onMetaResume() {
        logVideo('loadedmetadata', { duration: video.duration });
        if (startPos > 0 && startPos < video.duration - 5) {
            video.currentTime = startPos;
        }
        updateTime();
    });

    video.addEventListener('timeupdate', function () {
        if (video.duration) {
            progressBar.value = (video.currentTime / video.duration) * 100;
        }
        updateTime();
        scheduleSave();
        showControlsBriefly();
    });

    video.addEventListener('ended', function () {
        saveProgress(video.duration, true);
        btnPlay.innerHTML = '&#9654;';
        var nextUrl = wrapper.dataset.nextUrl;
        if (nextUrl) {
            setTimeout(function () { window.location.href = nextUrl; }, 2000);
        }
    });

    video.addEventListener('click', togglePlay);

    btnPlay.addEventListener('click', function (e) {
        e.stopPropagation();
        togglePlay();
    });

    progressBar.addEventListener('input', function () {
        if (video.duration) {
            video.currentTime = (progressBar.value / 100) * video.duration;
        }
    });

    btnFullscreen.addEventListener('click', function (e) {
        e.stopPropagation();
        enterFullscreen();
    });

    wrapper.addEventListener('mousemove', showControlsBriefly);
    wrapper.addEventListener('touchstart', showControlsBriefly, { passive: true });

    window.addEventListener('beforeunload', function () {
        if (video.currentTime > 0) {
            saveProgress(video.currentTime, false, true);
        }
    });

    function togglePlay() {
        if (video.paused) {
            video.play();
            btnPlay.innerHTML = '&#10074;&#10074;';
            if (isMobile) {
                setTimeout(enterFullscreen, 300);
            }
        } else {
            video.pause();
            btnPlay.innerHTML = '&#9654;';
            saveProgress(video.currentTime, false);
        }
    }

    function enterFullscreen() {
        var target = wrapper.requestFullscreen ? wrapper : video;
        if (document.fullscreenElement) {
            document.exitFullscreen();
        } else if (target.requestFullscreen) {
            target.requestFullscreen();
        } else if (video.webkitEnterFullscreen) {
            video.webkitEnterFullscreen();
        } else if (wrapper.webkitRequestFullscreen) {
            wrapper.webkitRequestFullscreen();
        }
    }

    function showControlsBriefly() {
        if (!cinemaControls) return;
        cinemaControls.classList.add('is-visible');
        clearTimeout(controlsTimer);
        if (!video.paused) {
            controlsTimer = setTimeout(function () {
                cinemaControls.classList.remove('is-visible');
            }, 3500);
        }
    }

    function formatTime(sec) {
        sec = Math.floor(sec || 0);
        var h = Math.floor(sec / 3600);
        var m = Math.floor((sec % 3600) / 60);
        var s = sec % 60;
        if (h > 0) {
            return h + ':' + String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0');
        }
        return m + ':' + String(s).padStart(2, '0');
    }

    function updateTime() {
        var cur = video.currentTime || 0;
        var dur = video.duration || 0;
        var rem = Math.max(0, dur - cur);

        if (timeCurrent) timeCurrent.textContent = formatTime(cur);
        if (timeDuration) timeDuration.textContent = formatTime(dur);
        if (timeRemaining) {
            timeRemaining.textContent = remainingLabel + formatTime(rem);
        }
    }

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
