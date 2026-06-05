/**
 * StreamPremium player — native <video controls> + compact toolbar (Audio, CC, Speed, Quality, FS).
 */
(function (global) {
    'use strict';

    var SPEED_OPTIONS = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0];
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

    function speedLabel(s) {
        if (s === 1 || s === 1.0) return '1x';
        return s + 'x';
    }

    function closePopover() {
        var pop = document.getElementById('dw-popover');
        if (pop) pop.setAttribute('hidden', 'hidden');
        openPanel = null;
        document.querySelectorAll('.dw-tool-btn.is-open').forEach(function (b) {
            b.classList.remove('is-open');
        });
    }

    function openMenu(panelId, anchorBtn, items, onPick) {
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
                if (!item.disabled && onPick) onPick(item);
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

    function subtitleTracks(manifest) {
        var sub = manifest.subtitles || {};
        if (sub.tracks && sub.tracks.length) return sub.tracks;
        var sm = readJson('player-subtitle-manifest', {});
        return sm.tracks || [];
    }

    function hasHlsQualities(manifest) {
        return !!(manifest.qualities && manifest.qualities.hls_ready);
    }

    function qualityLevels(manifest) {
        if (!hasHlsQualities(manifest)) return [];
        var levels = (manifest.qualities && manifest.qualities.levels) || [];
        var out = [{ id: 'auto', label: 'Auto' }];
        var seen = {};
        levels.forEach(function (lv) {
            if (lv.id === 'auto' || lv.id === 'mp4') return;
            var h = parseInt(lv.id || lv.height, 10);
            if (!h || seen[h]) return;
            seen[h] = true;
            out.push({ id: String(h), label: lv.label || h + 'p', height: h, index: lv.index });
        });
        if (hlsLevels.length) {
            hlsLevels.forEach(function (lv) {
                var hh = lv.height;
                if (!hh || seen[hh]) return;
                seen[hh] = true;
                out.push({ id: String(hh), label: lv.label || hh + 'p', height: hh, index: lv.index });
            });
        }
        out.sort(function (a, b) {
            if (a.id === 'auto') return -1;
            if (b.id === 'auto') return 1;
            return parseInt(a.id, 10) - parseInt(b.id, 10);
        });
        return out;
    }

    function setButtonVisible(btn, visible) {
        if (!btn) return;
        if (visible) btn.removeAttribute('hidden');
        else btn.setAttribute('hidden', 'hidden');
    }

    function loadMp4(video, url, episodeId) {
        if (!url) return;
        if (global.FlowPremiumHls) global.FlowPremiumHls.destroy();
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
        if (!masterUrl || !global.FlowPremiumHls) return false;
        hlsMasterUrl = masterUrl;
        global.FlowPremiumHls.setup(video, masterUrl, {
            onReady: function (ctx) {
                hlsRef = ctx.hls;
                hlsLevels = ctx.levels || [];
                var qBtn = document.getElementById('dw-btn-quality');
                var manifest = readJson('player-playback-manifest', {});
                if (hasHlsQualities(manifest) || hlsLevels.length) {
                    setButtonVisible(qBtn, true);
                }
            },
            onError: function () {
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
        var tracks = (manifest.audio && manifest.audio.tracks) || [];
        if (!tracks.length) {
            setButtonVisible(btn, false);
            return;
        }
        setButtonVisible(btn, true);
        btn.addEventListener('click', function (e) {
            e.stopPropagation();
            if (openPanel === 'audio') { closePopover(); return; }
            var items = tracks.map(function (t) {
                return {
                    id: t.id || t.lang,
                    label: (t.flag ? t.flag + ' ' : '') + (t.label || t.language),
                };
            });
            openMenu('audio', btn, items, function (item) {
                if (global.FlowPremiumAudio) global.FlowPremiumAudio.selectTrack(video, item.id);
            });
        });
    }

    function bindSubtitlesButton(video, manifest, episodeId) {
        var btn = document.getElementById('dw-btn-subtitles');
        if (!btn) return;
        var tracks = subtitleTracks(manifest);
        if (!tracks.length) {
            setButtonVisible(btn, false);
            return;
        }
        setButtonVisible(btn, true);
        btn.textContent = 'CC';
        btn.addEventListener('click', function (e) {
            e.stopPropagation();
            if (openPanel === 'subtitles') { closePopover(); return; }
            var items = [{ id: 'off', label: 'Off' }];
            tracks.forEach(function (t) {
                items.push({
                    id: t.lang,
                    label: (t.flag ? t.flag + ' ' : '') + t.label,
                });
            });
            openMenu('subtitles', btn, items, function (item) {
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
        btn.textContent = '1x';
        btn.addEventListener('click', function (e) {
            e.stopPropagation();
            if (openPanel === 'speed') { closePopover(); return; }
            var items = SPEED_OPTIONS.map(function (s) {
                return { id: String(s), label: speedLabel(s), active: s === currentSpeed };
            });
            openMenu('speed', btn, items, function (item) {
                currentSpeed = parseFloat(item.id);
                video.playbackRate = currentSpeed;
                btn.textContent = speedLabel(currentSpeed);
            });
        });
    }

    function bindQualityButton(video, manifest, defaultStreamUrl, episodeId) {
        var btn = document.getElementById('dw-btn-quality');
        if (!btn) return;
        if (!hasHlsQualities(manifest)) {
            setButtonVisible(btn, false);
            return;
        }
        setButtonVisible(btn, true);
        btn.addEventListener('click', function (e) {
            e.stopPropagation();
            if (openPanel === 'quality') { closePopover(); return; }
            var levels = qualityLevels(manifest);
            if (levels.length <= 1) return;
            var items = levels.map(function (lv) {
                return { id: lv.id, label: lv.label, index: lv.index, active: lv.id === currentQuality };
            });
            openMenu('quality', btn, items, function (item) {
                currentQuality = item.id;
                btn.textContent = item.label;
                if (item.id === 'auto') {
                    if (hlsMasterUrl && tryLoadHls(video, hlsMasterUrl, episodeId, defaultStreamUrl)) return;
                    loadMp4(video, defaultStreamUrl, episodeId);
                    return;
                }
                if (global.FlowPremiumHls && hlsRef) {
                    var idx = -1;
                    for (var i = 0; i < hlsLevels.length; i++) {
                        if (String(hlsLevels[i].height) === item.id) { idx = hlsLevels[i].index; break; }
                    }
                    if (idx >= 0) global.FlowPremiumHls.setQuality(hlsRef, idx);
                }
            });
        });
    }

    function enterFullscreen(video, stage) {
        if (video && typeof video.webkitEnterFullscreen === 'function') {
            try { video.webkitEnterFullscreen(); return; } catch (err) { /* fallback */ }
        }
        var el = stage || video;
        if (el.requestFullscreen) {
            el.requestFullscreen().catch(function () {});
        } else if (el.webkitRequestFullscreen) {
            el.webkitRequestFullscreen();
        } else if (el.msRequestFullscreen) {
            el.msRequestFullscreen();
        } else if (video && video.webkitEnterFullscreen) {
            video.webkitEnterFullscreen();
        }
    }

    function bindFullscreenButton(video) {
        var btn = document.getElementById('dw-btn-fullscreen');
        var stage = document.getElementById('player-wrapper');
        if (!btn) return;
        btn.addEventListener('click', function (e) {
            e.stopPropagation();
            enterFullscreen(video, stage);
        });
    }

    function init(video, episodeId, defaultStreamUrl) {
        var manifest = readJson('player-playback-manifest', {});

        setupSource(video, manifest, defaultStreamUrl, episodeId);
        bindAudioButton(video, manifest);
        bindSubtitlesButton(video, manifest, episodeId);
        bindSpeedButton(video);
        bindQualityButton(video, manifest, defaultStreamUrl, episodeId);
        bindFullscreenButton(video);

        document.addEventListener('click', closePopover);

        var tracks = subtitleTracks(manifest);
        if (tracks.length && global.FlowPremiumSubtitles) {
            global.FlowPremiumSubtitles.init(video, episodeId, document.getElementById('dw-btn-subtitles'));
        }
    }

    global.FlowPremiumPlayer = { init: init, enterFullscreen: enterFullscreen };
})(window);
