/**
 * Audio language pills (MP4 variants + HLS). Mobile uses separate MP4 URLs, not embedded tracks.
 */
(function (global) {
    'use strict';

    var STORAGE_KEY = 'flowpremium_audio_lang';
    var hlsInstance = null;
    var currentTrackId = null;

    function supportsEmbeddedAudio() {
        var v = document.createElement('video');
        return typeof v.audioTracks !== 'undefined' && v.audioTracks !== null;
    }

    function isMobile() {
        return /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent);
    }

    function savedAudio(episodeId) {
        try {
            var raw = localStorage.getItem(STORAGE_KEY);
            if (!raw) return null;
            var data = JSON.parse(raw);
            if (!data || typeof data !== 'object') return null;
            if (data[String(episodeId)] != null) return data[String(episodeId)];
            return data.global || null;
        } catch (e) {
            return null;
        }
    }

    function persistAudio(episodeId, trackId) {
        try {
            var raw = localStorage.getItem(STORAGE_KEY);
            var data = raw ? JSON.parse(raw) : {};
            if (!data || typeof data !== 'object') data = {};
            data.global = trackId;
            data[String(episodeId)] = trackId;
            localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
        } catch (e) { /* ignore */ }
    }

    function switchableTracks(manifest) {
        if (!manifest || !manifest.tracks) return [];
        return manifest.tracks.filter(function (track) {
            if (track.type === 'url' || track.type === 'hls') return true;
            if (track.type === 'embedded' && supportsEmbeddedAudio() && !isMobile()) return true;
            return false;
        });
    }

    function findTrack(manifest, trackId) {
        if (!manifest || !manifest.tracks) return null;
        for (var i = 0; i < manifest.tracks.length; i++) {
            if (manifest.tracks[i].id === trackId) return manifest.tracks[i];
        }
        return null;
    }

    function findTrackByLang(manifest, lang) {
        if (!manifest || !manifest.tracks) return null;
        for (var i = 0; i < manifest.tracks.length; i++) {
            if (manifest.tracks[i].lang === lang) return manifest.tracks[i];
        }
        return null;
    }

    function resolveInitialTrackId(manifest, episodeId) {
        var tracks = switchableTracks(manifest);
        if (!tracks.length) return manifest.default || 'es';
        var preferred = savedAudio(episodeId);
        if (preferred) {
            if (findTrack(manifest, preferred)) return preferred;
            var byLang = findTrackByLang(manifest, preferred);
            if (byLang) return byLang.id;
        }
        return manifest.default || tracks[0].id;
    }

    function destroyHls() {
        if (hlsInstance) {
            try {
                hlsInstance.destroy();
            } catch (e) { /* ignore */ }
            hlsInstance = null;
        }
    }

    function setVideoSource(video, url) {
        if (!video || !url) return;
        destroyHls();
        video.src = url;
        video.load();
    }

    function hideAudioRow() {
        var row = document.getElementById('watch-audio-row');
        if (row) row.setAttribute('hidden', 'hidden');
    }

    function showAudioRow() {
        var row = document.getElementById('watch-audio-row');
        if (row) row.removeAttribute('hidden');
    }

    function switchEmbeddedTrack(video, track) {
        var list = video.audioTracks;
        if (!list || !list.length) return false;
        for (var i = 0; i < list.length; i++) {
            var enabled = list[i].id === String(track.index) || i === track.index;
            list[i].enabled = enabled;
        }
        return true;
    }

    function switchUrlTrack(video, track) {
        var savedTime = video.currentTime || 0;
        var wasPlaying = !video.paused;
        setVideoSource(video, track.url);
        video.addEventListener('loadedmetadata', function once() {
            video.removeEventListener('loadedmetadata', once);
            if (savedTime > 0 && savedTime < (video.duration || savedTime + 1) - 0.5) {
                video.currentTime = savedTime;
            }
            if (wasPlaying) {
                video.play().catch(function () {});
            }
        });
    }

    function applyTrack(video, manifest, track, hls) {
        if (!track) return;
        currentTrackId = track.id;
        if (track.type === 'hls' && track.url) {
            setupHlsPlayer(video, track.url, manifest, currentTrackId, null);
            return;
        }
        if (track.type === 'url' && track.url) {
            switchUrlTrack(video, track);
            return;
        }
        if (track.type === 'embedded') {
            switchEmbeddedTrack(video, track);
        }
    }

    function setActivePill(container, trackId) {
        if (!container) return;
        container.querySelectorAll('.watch-audio-pill').forEach(function (btn) {
            btn.classList.toggle('is-active', btn.dataset.trackId === trackId);
            btn.setAttribute('aria-pressed', btn.dataset.trackId === trackId ? 'true' : 'false');
        });
    }

    function renderAudioPills(container, manifest, video, episodeId, onSelect) {
        if (!container) return;
        container.innerHTML = '';
        var tracks = switchableTracks(manifest);
        if (tracks.length < 2) {
            hideAudioRow();
            return;
        }
        showAudioRow();

        tracks.forEach(function (track) {
            var btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'watch-audio-pill';
            btn.dataset.trackId = track.id;
            btn.setAttribute('aria-pressed', 'false');
            btn.textContent = (track.flag ? track.flag + ' ' : '') + track.label;
            if (track.id === currentTrackId) {
                btn.classList.add('is-active');
                btn.setAttribute('aria-pressed', 'true');
            }
            btn.addEventListener('click', function (e) {
                e.preventDefault();
                onSelect(track);
                persistAudio(episodeId, track.id);
            });
            container.appendChild(btn);
        });
    }

    function setupHlsPlayer(video, masterUrl, manifest, defaultTrackId, episodeId) {
        currentTrackId = defaultTrackId || manifest.default;
        episodeId = episodeId || 0;

        function onManifestParsed(hls) {
            var tracks = manifest.tracks && manifest.tracks.length
                ? switchableTracks(manifest)
                : (hls.audioTracks || []).map(function (t, i) {
                    return {
                        id: 'hls-' + i,
                        lang: t.lang || 'track' + i,
                        label: t.name || t.lang || 'Track ' + (i + 1),
                        flag: '🔊',
                        type: 'hls',
                        index: i,
                    };
                });

            var pills = document.getElementById('watch-audio-pills');
            renderAudioPills(pills, { tracks: tracks, default: currentTrackId }, video, episodeId, function (track) {
                setActivePill(pills, track.id);
                applyTrack(video, manifest, track, hls);
            });

            var initial = findTrack({ tracks: tracks }, currentTrackId) || tracks[0];
            if (initial) {
                applyTrack(video, manifest, initial, hls);
                setActivePill(pills, initial.id);
            }
        }

        if (global.Hls && global.Hls.isSupported() && !isMobile()) {
            destroyHls();
            hlsInstance = new global.Hls();
            hlsInstance.loadSource(masterUrl);
            hlsInstance.attachMedia(video);
            hlsInstance.on(global.Hls.Events.MANIFEST_PARSED, function () {
                onManifestParsed(hlsInstance);
            });
            return;
        }

        if (video.canPlayType('application/vnd.apple.mpegurl')) {
            setVideoSource(video, masterUrl);
            video.addEventListener('loadedmetadata', function onMeta() {
                video.removeEventListener('loadedmetadata', onMeta);
                var pills = document.getElementById('watch-audio-pills');
                renderAudioPills(pills, manifest, video, episodeId, function (track) {
                    setActivePill(pills, track.id);
                    applyTrack(video, manifest, track, null);
                });
                var initial = findTrack(manifest, currentTrackId) || switchableTracks(manifest)[0];
                if (initial) {
                    applyTrack(video, manifest, initial, null);
                    setActivePill(pills, initial.id);
                }
            });
        }
    }

    function init(video, manifest, defaultStreamUrl, episodeId) {
        if (!video || !manifest) return;

        episodeId = episodeId || 0;
        currentTrackId = resolveInitialTrackId(manifest, episodeId);
        var pills = document.getElementById('watch-audio-pills');
        var tracks = switchableTracks(manifest);

        if (manifest.mode === 'hls' && manifest.master_url) {
            setupHlsPlayer(video, manifest.master_url, manifest, currentTrackId, episodeId);
            return;
        }

        if (tracks.length < 2) {
            hideAudioRow();
            var single = findTrack(manifest, currentTrackId) || tracks[0];
            var url = (single && single.url) || defaultStreamUrl;
            if (url) {
                setVideoSource(video, url);
            }
            return;
        }

        var defaultTrack = findTrack(manifest, currentTrackId) || tracks[0];
        if (defaultTrack && defaultTrack.url) {
            setVideoSource(video, defaultTrack.url);
        } else if (defaultStreamUrl) {
            setVideoSource(video, defaultStreamUrl);
        }

        renderAudioPills(pills, manifest, video, episodeId, function (track) {
            setActivePill(pills, track.id);
            applyTrack(video, manifest, track, null);
        });

        if (defaultTrack && defaultTrack.type === 'embedded' && supportsEmbeddedAudio() && !isMobile()) {
            video.addEventListener('loadedmetadata', function once() {
                video.removeEventListener('loadedmetadata', once);
                switchEmbeddedTrack(video, defaultTrack);
                setActivePill(pills, defaultTrack.id);
            });
        } else if (defaultTrack) {
            setActivePill(pills, defaultTrack.id);
        }
    }

    global.FlowPremiumAudio = {
        init: init,
        destroyHls: destroyHls,
        setVideoSource: setVideoSource,
        switchableTracks: switchableTracks,
    };
})(window);
