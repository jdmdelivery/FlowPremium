/**
 * DramaWave-style player: Audio | Subtitles | Speed | Quality (always visible).
 */
(function (global) {
    'use strict';

    var SPEED_OPTIONS = [0.5, 1.0, 1.25, 1.5, 2.0];
    var currentSpeed = 1.0;
    var currentQuality = 'auto';
    var hlsRef = null;
    var hlsLevels = [];
    var openPanel = null;
    var hlsMasterUrl = null;

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
                if (!item.disabled && onPick) {
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

    function loadMp4(video, url, episodeId) {
        if (!url) return;
        if (global.FlowPremiumHls) {
            global.FlowPremiumHls.destroy();
        }
        if (global.FlowPremiumAudio && global.FlowPremiumAudio.initFromPlayback) {
            var manifest = readJson('player-playback-manifest', {});
            if (manifest.audio && manifest.audio.tracks && manifest.audio.tracks.length) {
                global.FlowPremiumAudio.initFromPlayback(video, manifest, episodeId);
                return;
            }
        }
        video.src = url;
        video.load();
    }

    function tryLoadHls(video, masterUrl, episodeId, mp4Url) {
        if (!masterUrl || !global.FlowPremiumHls) {
            return false;
        }
        hlsMasterUrl = masterUrl;
        global.FlowPremiumHls.setup(video, masterUrl, {
            onReady: function (ctx) {
                hlsRef = ctx.hls;
                hlsLevels = ctx.levels || [];
            },
            onError: function () {
                console.warn('[FlowPremium] HLS failed, falling back to MP4');
                loadMp4(video, mp4Url, episodeId);
            },
        });
        return true;
    }

    function setupSource(video, manifest, defaultStreamUrl, episodeId) {
        hlsMasterUrl = manifest.hls_master_url || null;

        if (defaultStreamUrl) {
            loadMp4(video, defaultStreamUrl, episodeId);
        } else if (hlsMasterUrl) {
            tryLoadHls(video, hlsMasterUrl, episodeId, null);
        }
    }

    function bindAudioButton(video, manifest) {
        var btn = document.getElementById('dw-btn-audio');
        if (!btn) return;

        btn.textContent = (manifest.audio && manifest.audio.button_label) || 'Audio';
        btn.disabled = false;

        btn.addEventListener('click', function (e) {
            e.stopPropagation();
            if (openPanel === 'audio') {
                closePopover();
                return;
            }
            var tracks = (manifest.audio && manifest.audio.tracks) || [];
            if (!tracks.length) {
                openMenu('audio', [{
                    id: 'none',
                    label: manifest.audio.unavailable_label || 'Audio no disponible',
                    disabled: true,
                }], null);
                return;
            }
            var items = tracks.map(function (t) {
                return {
                    id: t.id || t.lang,
                    label: (t.flag ? t.flag + ' ' : '') + (t.label || t.language),
                    active: false,
                };
            });
            openMenu('audio', items, function (item) {
                if (global.FlowPremiumAudio) {
                    global.FlowPremiumAudio.selectTrack(video, item.id);
                }
            });
        });
    }

    function bindSubtitlesButton(video, manifest, episodeId) {
        var btn = document.getElementById('dw-btn-subtitles');
        if (!btn) return;

        btn.textContent = (manifest.subtitles && manifest.subtitles.button_label) || 'Subtitles';
        btn.disabled = false;

        btn.addEventListener('click', function (e) {
            e.stopPropagation();
            if (openPanel === 'subtitles') {
                closePopover();
                return;
            }

            if (manifest.subtitles && manifest.subtitles.generating) {
                openMenu('subtitles', [{
                    id: 'generating',
                    label: manifest.subtitles.generating_label || 'Generando subtítulos...',
                    disabled: true,
                }], null);
                return;
            }

            var tracks = (manifest.subtitles && manifest.subtitles.tracks) || [];
            if (!tracks.length) {
                openMenu('subtitles', [{
                    id: 'none',
                    label: manifest.subtitles.unavailable_label || 'No disponible',
                    disabled: true,
                }], null);
                return;
            }

            var items = [{ id: 'off', label: 'Off', active: false }];
            tracks.forEach(function (t) {
                items.push({
                    id: t.lang,
                    label: (t.flag ? t.flag + ' ' : '') + t.label,
                    active: false,
                });
            });
            openMenu('subtitles', items, function (item) {
                if (global.FlowPremiumSubtitles) {
                    global.FlowPremiumSubtitles.selectLang(video, episodeId, item.id);
                }
                btn.classList.toggle('is-active', item.id !== 'off');
            });
        });
    }

    function bindSpeedButton(video) {
        var btn = document.getElementById('dw-btn-speed');
        if (!btn) return;
        btn.textContent = '1.0X';
        btn.disabled = false;

        btn.addEventListener('click', function (e) {
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
                btn.textContent = item.label;
            });
        });
    }

    function bindQualityButton(video, manifest, defaultStreamUrl, episodeId) {
        var btn = document.getElementById('dw-btn-quality');
        if (!btn) return;

        var levels = (manifest.qualities && manifest.qualities.levels) || [
            { id: 'auto', label: 'Auto' },
            { id: 'mp4', label: 'MP4' },
        ];
        btn.textContent = (manifest.qualities && manifest.qualities.button_label) || 'Calidad';
        btn.disabled = false;

        btn.addEventListener('click', function (e) {
            e.stopPropagation();
            if (openPanel === 'quality') {
                closePopover();
                return;
            }
            var items = levels.map(function (lv) {
                return {
                    id: lv.id,
                    label: lv.label,
                    index: lv.index,
                    active: lv.id === currentQuality,
                    disabled: lv.id !== 'mp4' && lv.id !== 'auto' && !manifest.qualities.hls_ready,
                };
            });
            openMenu('quality', items, function (item) {
                currentQuality = item.id;
                btn.textContent = item.label;
                if (item.id === 'mp4' || !manifest.qualities.hls_ready) {
                    loadMp4(video, defaultStreamUrl, episodeId);
                    return;
                }
                if (item.id === 'auto') {
                    if (hlsMasterUrl && tryLoadHls(video, hlsMasterUrl, episodeId, defaultStreamUrl)) {
                        return;
                    }
                    loadMp4(video, defaultStreamUrl, episodeId);
                    return;
                }
                if (global.FlowPremiumHls && hlsRef) {
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

    function initProgressUi(video, manifest) {
        var bar = document.getElementById('dw-progress');
        var cur = document.getElementById('dw-time-current');
        var dur = document.getElementById('dw-time-duration');
        var centerPlay = document.getElementById('dw-center-play');
        var fallbackDur = (manifest && manifest.duration_seconds) || 0;

        function sync() {
            var total = video.duration;
            if (!isFinite(total) || total <= 0) {
                total = fallbackDur > 0 ? fallbackDur : 0;
            }
            if (total > 0) {
                var pct = (video.currentTime / total) * 100;
                if (bar) bar.value = Math.min(100, Math.max(0, pct));
            }
            if (cur) cur.textContent = formatTime(video.currentTime);
            if (dur) {
                var d = isFinite(video.duration) && video.duration > 0 ? video.duration : fallbackDur;
                dur.textContent = formatTime(d);
            }
        }

        video.addEventListener('timeupdate', sync);
        video.addEventListener('loadedmetadata', sync);
        video.addEventListener('durationchange', sync);
        video.addEventListener('canplay', sync);

        if (fallbackDur > 0 && dur) {
            dur.textContent = formatTime(fallbackDur);
        }

        if (bar) {
            bar.addEventListener('input', function () {
                var total = video.duration;
                if (!isFinite(total) || total <= 0) total = fallbackDur;
                if (total > 0) {
                    video.currentTime = (parseFloat(bar.value) / 100) * total;
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

        setupSource(video, manifest, defaultStreamUrl, episodeId);
        bindAudioButton(video, manifest);
        bindSubtitlesButton(video, manifest, episodeId);
        bindSpeedButton(video);
        bindQualityButton(video, manifest, defaultStreamUrl, episodeId);
        initProgressUi(video, manifest);

        document.addEventListener('click', closePopover);

        if (global.FlowPremiumSubtitles) {
            global.FlowPremiumSubtitles.init(video, episodeId, document.getElementById('dw-btn-subtitles'));
        }
    }

    global.FlowPremiumPlayer = { init: init };
})(window);
