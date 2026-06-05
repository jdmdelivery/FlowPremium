/**
 * DramaWave-style player toolbar: Audio | Subtitles | Speed | Quality
 */
(function (global) {
    'use strict';

    var SPEED_OPTIONS = [0.5, 1.0, 1.25, 1.5, 2.0];
    var currentSpeed = 1.0;
    var currentQuality = 'auto';
    var hlsRef = null;
    var hlsLevels = [];
    var openPanel = null;

    function readJson(id, fallback) {
        var el = document.getElementById(id);
        if (!el) return fallback;
        try {
            return JSON.parse(el.textContent || '{}');
        } catch (e) {
            return fallback;
        }
    }

    function formatTime(sec) {
        if (!isFinite(sec) || sec < 0) sec = 0;
        var m = Math.floor(sec / 60);
        var s = Math.floor(sec % 60);
        return m + ':' + (s < 10 ? '0' : '') + s;
    }

    function closePopover() {
        var pop = document.getElementById('dw-popover');
        if (pop) pop.setAttribute('hidden', 'hidden');
        openPanel = null;
        document.querySelectorAll('.dw-tool-btn.is-open').forEach(function (b) {
            b.classList.remove('is-open');
        });
    }

    function openMenu(panelId, items, onPick) {
        var pop = document.getElementById('dw-popover');
        var panel = document.getElementById('dw-popover-panel');
        if (!pop || !panel) return;

        panel.innerHTML = '';
        items.forEach(function (item) {
            var btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'dw-popover-item' + (item.active ? ' is-active' : '');
            btn.textContent = item.label;
            btn.disabled = !!item.disabled;
            btn.addEventListener('click', function (e) {
                e.stopPropagation();
                if (!item.disabled) {
                    onPick(item);
                }
                closePopover();
            });
            panel.appendChild(btn);
        });

        pop.removeAttribute('hidden');
        openPanel = panelId;
        document.querySelectorAll('.dw-tool-btn').forEach(function (b) {
            b.classList.toggle('is-open', b.dataset.panel === panelId);
        });
    }

    function bindToolbar(video, manifest) {
        var btnAudio = document.getElementById('dw-btn-audio');
        var btnSubs = document.getElementById('dw-btn-subtitles');
        var btnSpeed = document.getElementById('dw-btn-speed');
        var btnQuality = document.getElementById('dw-btn-quality');

        if (btnAudio) {
            var audioTracks = (manifest.audio && manifest.audio.tracks) || [];
            if (!manifest.audio || !manifest.audio.available || audioTracks.length === 0) {
                btnAudio.disabled = true;
                btnAudio.textContent = manifest.audio ? manifest.audio.unavailable_label : 'Audio';
            } else if (audioTracks.length === 1) {
                btnAudio.textContent = audioTracks[0].label;
                btnAudio.disabled = true;
            } else {
                btnAudio.addEventListener('click', function (e) {
                    e.stopPropagation();
                    if (openPanel === 'audio') {
                        closePopover();
                        return;
                    }
                    var items = audioTracks.map(function (t) {
                        return {
                            id: t.id || t.lang,
                            label: (t.flag ? t.flag + ' ' : '') + t.label,
                            active: false,
                        };
                    });
                    openMenu('audio', items, function (item) {
                        if (global.FlowPremiumAudio) {
                            global.FlowPremiumAudio.selectTrack(video, item.id);
                        }
                        btnAudio.textContent = item.label.replace(/^[^\s]+\s/, '');
                    });
                });
            }
        }

        if (btnSubs) {
            var subTracks = (manifest.subtitles && manifest.subtitles.tracks) || [];
            if (!manifest.subtitles || !manifest.subtitles.available || subTracks.length === 0) {
                btnSubs.disabled = true;
                btnSubs.textContent = manifest.subtitles ? manifest.subtitles.unavailable_label : 'Subtitles';
            } else {
                btnSubs.addEventListener('click', function (e) {
                    e.stopPropagation();
                    if (openPanel === 'subtitles') {
                        closePopover();
                        return;
                    }
                    var items = [{ id: 'off', label: 'Off', active: false }];
                    subTracks.forEach(function (t) {
                        items.push({
                            id: t.lang,
                            label: (t.flag ? t.flag + ' ' : '') + t.label,
                            active: false,
                        });
                    });
                    openMenu('subtitles', items, function (item) {
                        if (global.FlowPremiumSubtitles) {
                            global.FlowPremiumSubtitles.selectLang(
                                video,
                                parseInt(manifest.episode_id, 10),
                                item.id
                            );
                        }
                        btnSubs.classList.toggle('is-active', item.id !== 'off');
                    });
                });
            }
        }

        if (btnSpeed) {
            btnSpeed.addEventListener('click', function (e) {
                e.stopPropagation();
                if (openPanel === 'speed') {
                    closePopover();
                    return;
                }
                var items = SPEED_OPTIONS.map(function (s) {
                    return {
                        id: String(s),
                        label: s === 1 ? '1.0X' : s + 'X',
                        active: s === currentSpeed,
                    };
                });
                openMenu('speed', items, function (item) {
                    currentSpeed = parseFloat(item.id);
                    video.playbackRate = currentSpeed;
                    btnSpeed.textContent = item.label;
                });
            });
        }

        if (btnQuality) {
            updateQualityButton(btnQuality, manifest);
            btnQuality.addEventListener('click', function (e) {
                e.stopPropagation();
                if (openPanel === 'quality') {
                    closePopover();
                    return;
                }
                var levels = (manifest.qualities && manifest.qualities.levels) || [];
                if (!manifest.qualities || !manifest.qualities.available || levels.length < 2) {
                    return;
                }
                var items = levels.map(function (lv) {
                    return {
                        id: lv.id,
                        label: lv.label,
                        index: lv.index,
                        active: lv.id === currentQuality,
                    };
                });
                openMenu('quality', items, function (item) {
                    currentQuality = item.id;
                    btnQuality.textContent = item.label;
                    if (item.id === 'auto') {
                        if (global.FlowPremiumHls && hlsRef) {
                            global.FlowPremiumHls.setQuality(hlsRef, -1);
                        }
                    } else if (global.FlowPremiumHls && hlsRef) {
                        var idx = hlsLevels.findIndex(function (l) {
                            return String(l.height) === item.id || String(l.id) === item.id;
                        });
                        if (idx >= 0) {
                            global.FlowPremiumHls.setQuality(hlsRef, hlsLevels[idx].index);
                        }
                    }
                });
            });
        }

        document.addEventListener('click', closePopover);
    }

    function updateQualityButton(btn, manifest) {
        if (!btn) return;
        if (manifest.qualities && manifest.qualities.available && manifest.qualities.levels.length > 1) {
            btn.disabled = false;
            var def = manifest.qualities.default || 'auto';
            var match = manifest.qualities.levels.find(function (l) { return l.id === def; });
            btn.textContent = match ? match.label : 'Auto';
            currentQuality = def;
        } else {
            btn.disabled = true;
            btn.textContent = manifest.qualities ? manifest.qualities.unavailable_label : 'Auto';
        }
    }

    function setupSource(video, manifest, defaultStreamUrl, episodeId) {
        var master = manifest.hls_master_url;
        var legacy = manifest.legacy_audio;

        if (master && global.FlowPremiumHls) {
            global.FlowPremiumHls.setup(video, master, {
                onReady: function (ctx) {
                    hlsRef = ctx.hls;
                    hlsLevels = ctx.levels || [];
                    if (global.FlowPremiumAudio && manifest.audio && manifest.audio.tracks.length) {
                        global.FlowPremiumAudio.initFromPlayback(video, manifest, episodeId);
                    }
                },
                onError: function () {
                    if (defaultStreamUrl) {
                        video.src = defaultStreamUrl;
                        video.load();
                    }
                },
            });
            return;
        }

        if (legacy && legacy.mode === 'hls' && legacy.master_url && global.FlowPremiumAudio) {
            global.FlowPremiumAudio.init(video, legacy, defaultStreamUrl, episodeId);
            return;
        }

        if (global.FlowPremiumAudio) {
            var audioManifest = readJson('player-audio-manifest', {});
            if (manifest.audio && manifest.audio.tracks && manifest.audio.tracks.length) {
                global.FlowPremiumAudio.initFromPlayback(video, manifest, episodeId);
            } else {
                global.FlowPremiumAudio.init(video, audioManifest, defaultStreamUrl, episodeId);
            }
        } else if (defaultStreamUrl) {
            video.src = defaultStreamUrl;
            video.load();
        }
    }

    function initProgressUi(video) {
        var bar = document.getElementById('dw-progress');
        var cur = document.getElementById('dw-time-current');
        var dur = document.getElementById('dw-time-duration');
        var centerPlay = document.getElementById('dw-center-play');

        function sync() {
            if (!video.duration) return;
            var pct = (video.currentTime / video.duration) * 100;
            if (bar) bar.value = pct;
            if (cur) cur.textContent = formatTime(video.currentTime);
            if (dur) dur.textContent = formatTime(video.duration);
        }

        video.addEventListener('timeupdate', sync);
        video.addEventListener('loadedmetadata', sync);

        if (bar) {
            bar.addEventListener('input', function () {
                if (video.duration) {
                    video.currentTime = (parseFloat(bar.value) / 100) * video.duration;
                }
            });
        }

        if (centerPlay) {
            centerPlay.addEventListener('click', function () {
                if (video.paused) {
                    video.play().catch(function () {});
                } else {
                    video.pause();
                }
            });
        }

        video.addEventListener('play', function () {
            if (centerPlay) centerPlay.classList.add('is-hidden');
        });
        video.addEventListener('pause', function () {
            if (centerPlay && !video.ended) centerPlay.classList.remove('is-hidden');
        });
        video.addEventListener('ended', function () {
            if (centerPlay) centerPlay.classList.remove('is-hidden');
        });
    }

    function init(video, episodeId, defaultStreamUrl) {
        var manifest = readJson('player-playback-manifest', {});
        bindToolbar(video, manifest);
        setupSource(video, manifest, defaultStreamUrl, episodeId);
        initProgressUi(video);

        if (global.FlowPremiumSubtitles) {
            global.FlowPremiumSubtitles.init(video, episodeId, document.getElementById('dw-btn-subtitles'));
        }
    }

    global.FlowPremiumPlayer = { init: init };
})(window);
