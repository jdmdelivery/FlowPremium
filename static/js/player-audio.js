/**
 * Custom audio language selector (MP4 variants, embedded tracks, HLS).
 * Works on iPhone/Android without native video controls.
 */
(function (global) {
    'use strict';

    var hlsInstance = null;
    var currentTrackId = null;

    function supportsEmbeddedAudio() {
        var v = document.createElement('video');
        return typeof v.audioTracks !== 'undefined' && v.audioTracks !== null;
    }

    function isMobile() {
        return /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent);
    }

    function switchableTracks(manifest) {
        if (!manifest || !manifest.tracks) return [];
        return manifest.tracks.filter(function (track) {
            if (track.type === 'url' || track.type === 'hls') return true;
            if (track.type === 'embedded' && supportsEmbeddedAudio()) return true;
            return false;
        });
    }

    function findTrack(manifest, trackId) {
        for (var i = 0; i < manifest.tracks.length; i++) {
            if (manifest.tracks[i].id === trackId) return manifest.tracks[i];
        }
        return null;
    }

    function destroyHls() {
        if (hlsInstance) {
            try {
                hlsInstance.destroy();
            } catch (e) { /* ignore */ }
            hlsInstance = null;
        }
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

    function switchUrlTrack(video, track, onReady) {
        var savedTime = video.currentTime || 0;
        var wasPlaying = !video.paused;
        destroyHls();

        function resume() {
            if (savedTime > 0 && savedTime < (video.duration || savedTime + 1) - 0.5) {
                video.currentTime = savedTime;
            }
            if (wasPlaying) {
                video.play().catch(function () {});
            }
            if (onReady) onReady();
        }

        video.addEventListener('loadedmetadata', function once() {
            video.removeEventListener('loadedmetadata', once);
            resume();
        });
        video.src = track.url;
        video.load();
    }

    function switchHlsTrack(video, hls, track, manifest) {
        if (track.type === 'hls' && track.url) {
            destroyHls();
            setupHlsPlayer(video, track.url, manifest, track.id);
            return;
        }
        if (track.type === 'url' && track.url) {
            switchUrlTrack(video, track);
            return;
        }
        if (track.type === 'embedded' && hls && hls.audioTracks && hls.audioTracks.length) {
            for (var i = 0; i < hls.audioTracks.length; i++) {
                hls.audioTrack = i;
            }
            return;
        }
        if (track.type === 'embedded') {
            switchEmbeddedTrack(video, track);
        }
    }

    function setActiveButton(container, trackId) {
        if (!container) return;
        container.querySelectorAll('.audio-track-btn').forEach(function (btn) {
            btn.classList.toggle('is-active', btn.dataset.trackId === trackId);
        });
    }

    function renderAudioButtons(container, manifest, video, onSelect) {
        if (!container) return;
        container.innerHTML = '';
        var tracks = switchableTracks(manifest);
        if (tracks.length < 2) {
            container.closest('.audio-track-bar')?.setAttribute('hidden', 'hidden');
            return;
        }
        var bar = container.closest('.audio-track-bar');
        if (bar) bar.removeAttribute('hidden');

        tracks.forEach(function (track) {
            var btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'audio-track-btn';
            btn.dataset.trackId = track.id;
            btn.setAttribute('aria-pressed', 'false');
            btn.textContent = (track.flag ? track.flag + ' ' : '') + track.label;
            if (track.id === currentTrackId || track.id === manifest.default) {
                btn.classList.add('is-active');
            }
            btn.addEventListener('click', function (e) {
                e.stopPropagation();
                onSelect(track);
            });
            container.appendChild(btn);
        });
    }

    function setupHlsPlayer(video, masterUrl, manifest, defaultTrackId) {
        currentTrackId = defaultTrackId || manifest.default;

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

            var bar = document.getElementById('audio-track-options');
            renderAudioButtons(bar, { tracks: tracks, default: currentTrackId }, video, function (track) {
                currentTrackId = track.id;
                setActiveButton(bar, track.id);
                if (track.type === 'embedded' || (track.index !== undefined && hls.audioTracks.length)) {
                    hls.audioTrack = track.index !== undefined ? track.index : 0;
                } else if (track.type === 'url') {
                    switchUrlTrack(video, track);
                }
            });

            if (hls.audioTracks.length && !manifest.tracks) {
                hls.audioTrack = 0;
            }
        }

        if (global.Hls && global.Hls.isSupported()) {
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
            destroyHls();
            video.src = masterUrl;
            video.addEventListener('loadedmetadata', function onMeta() {
                video.removeEventListener('loadedmetadata', onMeta);
                var bar = document.getElementById('audio-track-options');
                renderAudioButtons(bar, manifest, video, function (track) {
                    currentTrackId = track.id;
                    setActiveButton(bar, track.id);
                    if (track.type === 'url') {
                        switchUrlTrack(video, track);
                    } else if (track.type === 'embedded') {
                        if (!switchEmbeddedTrack(video, track) && track.type === 'hls') {
                            /* Safari native HLS: try audioTracks */
                        }
                    }
                });
                if (supportsEmbeddedAudio() && video.audioTracks.length > 1) {
                    var def = findTrack(manifest, manifest.default);
                    if (def && def.type === 'embedded') {
                        switchEmbeddedTrack(video, def);
                    }
                }
            });
        }
    }

    function init(video, manifest, defaultStreamUrl) {
        if (!video || !manifest) return;

        currentTrackId = manifest.default || 'es';
        var bar = document.getElementById('audio-track-options');
        var tracks = switchableTracks(manifest);

        if (manifest.mode === 'hls' && manifest.master_url) {
            setupHlsPlayer(video, manifest.master_url, manifest, currentTrackId);
            return;
        }

        var defaultTrack = findTrack(manifest, currentTrackId) || tracks[0];
        if (defaultTrack && defaultTrack.url && !video.src) {
            video.src = defaultTrack.url;
        } else if (defaultStreamUrl && !video.src) {
            video.src = defaultStreamUrl;
        }

        renderAudioButtons(bar, manifest, video, function (track) {
            currentTrackId = track.id;
            setActiveButton(bar, track.id);
            if (track.type === 'url') {
                switchUrlTrack(video, track);
            } else if (track.type === 'embedded') {
                if (!switchEmbeddedTrack(video, track) && isMobile()) {
                    alert('En este dispositivo sube un MP4 en inglés separado o usa HLS.');
                }
            }
        });

        if (defaultTrack && defaultTrack.type === 'embedded' && supportsEmbeddedAudio()) {
            video.addEventListener('loadedmetadata', function once() {
                video.removeEventListener('loadedmetadata', once);
                switchEmbeddedTrack(video, defaultTrack);
            });
        }
    }

    global.FlowPremiumAudio = {
        init: init,
        destroyHls: destroyHls,
        supportsEmbeddedAudio: supportsEmbeddedAudio,
        switchableTracks: switchableTracks,
    };
})(window);
