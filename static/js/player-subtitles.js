/**
 * Multilingual CC selector (Netflix-style) — standard <track> elements.
 * Persists choice in localStorage; works on iOS Safari and Android Chrome.
 */
(function (global) {
    'use strict';

    var STORAGE_KEY = 'flowpremium_subtitle_lang';

    function readManifest() {
        var el = document.getElementById('player-subtitle-manifest');
        if (!el) return { show_cc: false, tracks: [] };
        try {
            return JSON.parse(el.textContent || '{}');
        } catch (e) {
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
            if (tt.language === lang) return tt;
        }
        return null;
    }

    function hideAllTracks(video) {
        for (var i = 0; i < video.textTracks.length; i++) {
            video.textTracks[i].mode = 'hidden';
        }
    }

    function applyChoice(video, lang, btnCc) {
        hideAllTracks(video);
        if (!lang || lang === 'off') {
            if (btnCc) btnCc.classList.remove('is-active');
            return;
        }
        var track = textTrackForLang(video, lang);
        if (track) {
            track.mode = 'showing';
            if (btnCc) btnCc.classList.add('is-active');
        } else if (btnCc) {
            btnCc.classList.remove('is-active');
        }
    }

    function closeMenu(menu) {
        if (menu) menu.classList.remove('is-open');
    }

    function renderCcMenu(menu, manifest, video, episodeId, btnCc) {
        if (!menu) return;
        menu.innerHTML = '';

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
    }

    function mountTracks(video, manifest) {
        manifest.tracks.forEach(function (t, idx) {
            var track = document.createElement('track');
            track.kind = 'captions';
            track.src = t.url;
            track.srclang = t.lang;
            track.label = t.label;
            if (idx === 0) track.default = true;
            video.appendChild(track);
        });
    }

    function init(video, episodeId, btnCc) {
        var manifest = readManifest();
        var menu = document.getElementById('cc-menu');

        if (!manifest.show_cc || !manifest.tracks || !manifest.tracks.length) {
            if (btnCc) btnCc.setAttribute('hidden', 'hidden');
            if (menu) menu.setAttribute('hidden', 'hidden');
            return;
        }

        if (btnCc) btnCc.removeAttribute('hidden');
        if (!video.querySelector('track')) {
            mountTracks(video, manifest);
        }
        renderCcMenu(menu, manifest, video, episodeId, btnCc);

        var preferred = savedLang(episodeId);
        var langs = manifest.tracks.map(function (t) { return t.lang; });
        if (preferred === 'off') {
            applyChoice(video, 'off', btnCc);
        } else if (preferred && langs.indexOf(preferred) >= 0) {
            applyChoice(video, preferred, btnCc);
        } else {
            var def = manifest.default_lang || langs[0];
            applyChoice(video, def, btnCc);
            persistLang(episodeId, def);
        }

        if (menu) {
            var active = preferred === 'off' ? 'off' : (preferred && langs.indexOf(preferred) >= 0 ? preferred : (manifest.default_lang || langs[0]));
            menu.querySelectorAll('.cc-menu-item').forEach(function (b) {
                b.classList.toggle('is-active', b.dataset.lang === active);
            });
        }

        if (btnCc) {
            btnCc.addEventListener('click', function (e) {
                e.stopPropagation();
                if (menu) {
                    menu.classList.toggle('is-open');
                    btnCc.classList.toggle('is-active', menu.classList.contains('is-open'));
                }
            });
        }

        document.addEventListener('click', function () {
            closeMenu(menu);
            if (btnCc && menu && !menu.classList.contains('is-open')) {
                var showing = false;
                for (var i = 0; i < video.textTracks.length; i++) {
                    if (video.textTracks[i].mode === 'showing') {
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
