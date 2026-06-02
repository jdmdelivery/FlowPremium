/**
 * CC selector (Español / Off) — standard <track kind="subtitles">.
 * Logs to console for Safari / Chrome / Android debugging.
 */
(function (global) {
    'use strict';

    var STORAGE_KEY = 'flowpremium_subtitle_lang';
    var LOG_PREFIX = '[FlowPremium CC]';

    function log(msg, detail) {
        if (detail !== undefined) {
            console.info(LOG_PREFIX, msg, detail);
        } else {
            console.info(LOG_PREFIX, msg);
        }
    }

    function logError(msg, detail) {
        if (detail !== undefined) {
            console.error(LOG_PREFIX, msg, detail);
        } else {
            console.error(LOG_PREFIX, msg);
        }
    }

    function readManifest() {
        var el = document.getElementById('player-subtitle-manifest');
        if (!el) return { show_cc: false, tracks: [] };
        try {
            return JSON.parse(el.textContent || '{}');
        } catch (e) {
            logError('manifest JSON parse failed', e);
            return { show_cc: false, tracks: [] };
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
            if (tt.language === lang || tt.language === lang + '-ES' || tt.language.indexOf(lang) === 0) {
                return tt;
            }
        }
        return null;
    }

    function hideAllTracks(video) {
        for (var i = 0; i < video.textTracks.length; i++) {
            video.textTracks[i].mode = 'hidden';
        }
    }

    function dumpTrackState(video) {
        var list = [];
        for (var i = 0; i < video.textTracks.length; i++) {
            var tt = video.textTracks[i];
            list.push({
                index: i,
                kind: tt.kind,
                language: tt.language,
                label: tt.label,
                mode: tt.mode,
                cues: tt.cues ? tt.cues.length : 0
            });
        }
        log('textTracks state', list);
    }

    function applyChoice(video, lang, btnCc) {
        hideAllTracks(video);
        if (!lang || lang === 'off') {
            if (btnCc) btnCc.classList.remove('is-active');
            log('subtitles off');
            dumpTrackState(video);
            return;
        }
        var track = textTrackForLang(video, lang);
        if (!track && video.textTracks.length > 0) {
            track = video.textTracks[0];
            log('fallback to textTracks[0]', track.label);
        }
        if (track) {
            track.mode = 'showing';
            if (btnCc) btnCc.classList.add('is-active');
            log('activated', { lang: lang, mode: track.mode, cues: track.cues ? track.cues.length : 0 });
        } else {
            logError('no textTrack for lang', lang);
            if (btnCc) btnCc.classList.remove('is-active');
        }
        dumpTrackState(video);
    }

    function closeMenu(menu) {
        if (menu) menu.classList.remove('is-open');
    }

    function renderCcMenu(menu, manifest, video, episodeId, btnCc) {
        if (!menu) return;
        menu.innerHTML = '';

        manifest.tracks.forEach(function (t) {
            var btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'cc-menu-item';
            btn.dataset.lang = t.lang;
            btn.textContent = (t.flag ? t.flag + ' ' : '') + t.label;
            btn.addEventListener('click', function (e) {
                e.stopPropagation();
                persistLang(episodeId, t.lang);
                applyChoice(video, t.lang, btnCc);
                menu.querySelectorAll('.cc-menu-item').forEach(function (b) {
                    b.classList.toggle('is-active', b.dataset.lang === t.lang);
                });
                closeMenu(menu);
            });
            menu.appendChild(btn);
        });

        var offBtn = document.createElement('button');
        offBtn.type = 'button';
        offBtn.className = 'cc-menu-item';
        offBtn.dataset.lang = 'off';
        offBtn.textContent = menu.dataset.offLabel || 'Off';
        offBtn.addEventListener('click', function (e) {
            e.stopPropagation();
            persistLang(episodeId, 'off');
            applyChoice(video, 'off', btnCc);
            menu.querySelectorAll('.cc-menu-item').forEach(function (b) {
                b.classList.toggle('is-active', b.dataset.lang === 'off');
            });
            closeMenu(menu);
        });
        menu.appendChild(offBtn);
    }

    function bindTrackElement(video, trackEl, episodeId, btnCc, preferredLang) {
        trackEl.addEventListener('load', function () {
            log('track element loaded', trackEl.src);
            applyChoice(video, preferredLang === 'off' ? 'off' : preferredLang, btnCc);
        });
        trackEl.addEventListener('error', function () {
            logError('track element failed to load', trackEl.src);
            dumpTrackState(video);
        });
    }

    function wireTextTrackEvents(video, episodeId, btnCc, preferredLang) {
        video.addEventListener('loadedmetadata', function () {
            log('video loadedmetadata — re-applying subtitles');
            applyChoice(video, preferredLang === 'off' ? 'off' : preferredLang, btnCc);
        });
        if (video.textTracks && video.textTracks.addEventListener) {
            video.textTracks.addEventListener('addtrack', function (ev) {
                log('addtrack', ev.track && ev.track.language);
                applyChoice(video, preferredLang === 'off' ? 'off' : preferredLang, btnCc);
            });
        }
        for (var i = 0; i < video.textTracks.length; i++) {
            (function (tt) {
                tt.addEventListener('load', function () {
                    log('textTrack load', tt.language);
                    applyChoice(video, preferredLang === 'off' ? 'off' : preferredLang, btnCc);
                });
                tt.addEventListener('error', function () {
                    logError('textTrack error', tt.language);
                });
            })(video.textTracks[i]);
        }
    }

    function init(video, episodeId, btnCc) {
        var manifest = readManifest();
        var menu = document.getElementById('cc-menu');

        log('init', {
            episodeId: episodeId,
            status: manifest.status,
            show_cc: manifest.show_cc,
            tracks: manifest.tracks
        });

        var overlay = document.getElementById('watch-cc-overlay');

        if (!manifest.show_cc || !manifest.tracks || !manifest.tracks.length) {
            log('CC hidden — no subtitles ready', manifest.status);
            if (btnCc) btnCc.setAttribute('hidden', 'hidden');
            if (menu) menu.setAttribute('hidden', 'hidden');
            if (overlay) overlay.setAttribute('hidden', 'hidden');
            return;
        }

        if (overlay) overlay.removeAttribute('hidden');
        if (btnCc) btnCc.removeAttribute('hidden');

        var preferred = savedLang(episodeId);
        var langs = manifest.tracks.map(function (t) { return t.lang; });
        var activeLang = preferred === 'off' ? 'off' : (
            preferred && langs.indexOf(preferred) >= 0 ? preferred : (manifest.default_lang || langs[0])
        );

        var trackElements = video.querySelectorAll('track');
        if (!trackElements.length) {
            manifest.tracks.forEach(function (t) {
                var track = document.createElement('track');
                track.kind = 'subtitles';
                track.src = t.url;
                track.srclang = t.lang;
                track.label = t.label;
                track.default = true;
                bindTrackElement(video, track, episodeId, btnCc, activeLang);
                video.appendChild(track);
            });
            log('mounted track elements via JS', manifest.tracks[0].url);
        } else {
            trackElements.forEach(function (trackEl) {
                bindTrackElement(video, trackEl, episodeId, btnCc, activeLang);
            });
            log('using server-rendered track', trackElements[0].src);
        }

        renderCcMenu(menu, manifest, video, episodeId, btnCc);
        wireTextTrackEvents(video, episodeId, btnCc, activeLang);

        if (activeLang !== 'off') {
            applyChoice(video, activeLang, btnCc);
            persistLang(episodeId, activeLang);
        } else {
            applyChoice(video, 'off', btnCc);
        }

        if (menu) {
            menu.querySelectorAll('.cc-menu-item').forEach(function (b) {
                b.classList.toggle('is-active', b.dataset.lang === activeLang);
            });
        }

        if (btnCc) {
            btnCc.addEventListener('click', function (e) {
                e.stopPropagation();
                if (menu) {
                    menu.classList.toggle('is-open');
                }
            });
        }

        document.addEventListener('click', function () {
            closeMenu(menu);
            if (btnCc && menu && !menu.classList.contains('is-open')) {
                var showing = false;
                for (var j = 0; j < video.textTracks.length; j++) {
                    if (video.textTracks[j].mode === 'showing') {
                        showing = true;
                        break;
                    }
                }
                btnCc.classList.toggle('is-active', showing);
            }
        });
    }

    global.FlowPremiumSubtitles = { init: init };
})(window);
