/**
 * Subtitles via <track kind="subtitles"> — Safari iOS, Android, desktop.
 */
(function (global) {
    'use strict';

    var STORAGE_KEY = 'flowpremium_subtitle_lang';

    function readManifest() {
        var el = document.getElementById('player-subtitle-manifest');
        if (!el) return { tracks: [] };
        try {
            return JSON.parse(el.textContent || '{}');
        } catch (e) {
            return { tracks: [] };
        }
    }

    function savedLang(episodeId) {
        try {
            var raw = localStorage.getItem(STORAGE_KEY);
            if (!raw) return null;
            var data = JSON.parse(raw);
            return data && data[String(episodeId)] != null ? data[String(episodeId)] : data.global || null;
        } catch (e) {
            return null;
        }
    }

    function persistLang(episodeId, lang) {
        try {
            var raw = localStorage.getItem(STORAGE_KEY);
            var data = raw ? JSON.parse(raw) : {};
            if (!data || typeof data !== 'object') data = {};
            data.global = lang;
            data[String(episodeId)] = lang;
            localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
        } catch (e) { /* private mode */ }
    }

    function textTrackForLang(video, lang) {
        for (var i = 0; i < video.textTracks.length; i++) {
            var tt = video.textTracks[i];
            if (!tt || tt.kind !== 'subtitles') continue;
            if (tt.language === lang || tt.language.indexOf(lang) === 0) return tt;
        }
        return null;
    }

    function hideAllTracks(video) {
        for (var i = 0; i < video.textTracks.length; i++) {
            if (video.textTracks[i].kind === 'subtitles') {
                video.textTracks[i].mode = 'hidden';
            }
        }
    }

    function applyChoice(video, lang, btnCc) {
        hideAllTracks(video);
        if (!lang || lang === 'off') {
            if (btnCc) btnCc.classList.remove('is-active');
            return;
        }
        var track = textTrackForLang(video, lang);
        if (!track) {
            for (var i = 0; i < video.textTracks.length; i++) {
                if (video.textTracks[i].kind === 'subtitles') {
                    track = video.textTracks[i];
                    break;
                }
            }
        }
        if (track) {
            track.mode = 'showing';
            if (btnCc) btnCc.classList.add('is-active');
        } else if (btnCc) {
            btnCc.classList.remove('is-active');
        }
    }

    function ensureTrackElements(video, manifest) {
        var existing = video.querySelectorAll('track[kind="subtitles"]');
        if (existing.length) return;
        manifest.tracks.forEach(function (t, idx) {
            var track = document.createElement('track');
            track.kind = 'subtitles';
            track.src = t.url;
            track.srclang = t.lang;
            track.label = t.label;
            if (idx === 0) track.default = true;
            video.appendChild(track);
        });
    }

    function wireEvents(video, episodeId, btnCc, preferredLang) {
        function reapply() {
            applyChoice(video, preferredLang === 'off' ? 'off' : preferredLang, btnCc);
        }
        video.addEventListener('loadedmetadata', reapply);
        video.addEventListener('canplay', reapply);
        var trackEls = video.querySelectorAll('track');
        trackEls.forEach(function (trackEl) {
            trackEl.addEventListener('load', reapply);
        });
        if (video.textTracks && video.textTracks.addEventListener) {
            video.textTracks.addEventListener('addtrack', reapply);
        }
    }

    function selectLang(video, episodeId, lang) {
        var btnCc = document.getElementById('dw-btn-subtitles');
        persistLang(episodeId, lang);
        applyChoice(video, lang === 'off' ? 'off' : lang, btnCc);
    }

    function init(video, episodeId, btnCc) {
        var manifest = readManifest();
        if (!manifest.tracks || !manifest.tracks.length) return;

        ensureTrackElements(video, manifest);

        var preferred = savedLang(episodeId);
        var langs = manifest.tracks.map(function (t) { return t.lang; });
        var activeLang = preferred === 'off' ? 'off' : (
            preferred && langs.indexOf(preferred) >= 0 ? preferred : (manifest.default_lang || langs[0])
        );

        wireEvents(video, episodeId, btnCc, activeLang);

        if (activeLang !== 'off') {
            applyChoice(video, activeLang, btnCc);
            persistLang(episodeId, activeLang);
        } else {
            applyChoice(video, 'off', btnCc);
        }
    }

    global.FlowPremiumSubtitles = { init: init, selectLang: selectLang };
})(window);
