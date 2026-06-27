(function () {
    'use strict';

  /* ── Page skeleton → content reveal ── */
    var skeleton = document.getElementById('page-skeleton');
    var content = document.getElementById('page-content');

    function revealContent() {
        if (content) {
            content.classList.remove('hidden-until-loaded');
            content.classList.add('is-ready');
        }
        if (skeleton) {
            skeleton.classList.add('is-hidden');
            setTimeout(function () { skeleton.style.display = 'none'; }, 400);
        }
    }

    if (content) {
        if (document.readyState === 'complete') {
            setTimeout(revealContent, 350);
        } else {
            window.addEventListener('load', function () { setTimeout(revealContent, 350); });
        }
    }

    /* ── Sticky nav scroll state ── */
    var nav = document.getElementById('main-nav');
    if (nav) {
        window.addEventListener('scroll', function () {
            nav.classList.toggle('nav-scrolled', window.scrollY > 8);
        }, { passive: true });
    }

    /* ── Mobile nav drawer ── */
    var navToggle = document.getElementById('nav-toggle');
    var navDrawer = document.getElementById('nav-drawer');
    var navBackdrop = document.getElementById('nav-backdrop');

    function setDrawerOpen(open) {
        if (!navDrawer || !navToggle) return;
        navDrawer.classList.toggle('is-open', open);
        navToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
        if (navBackdrop) {
            navBackdrop.hidden = !open;
            navBackdrop.classList.toggle('is-visible', open);
            navBackdrop.setAttribute('aria-hidden', open ? 'false' : 'true');
        }
        document.body.style.overflow = open ? 'hidden' : '';
    }

    function closeDrawer() {
        setDrawerOpen(false);
    }

    if (navToggle && navDrawer) {
        navToggle.addEventListener('click', function () {
            var open = !navDrawer.classList.contains('is-open');
            setDrawerOpen(open);
        });

        navDrawer.querySelectorAll('a').forEach(function (link) {
            link.addEventListener('click', closeDrawer);
        });
    }

    if (navBackdrop) {
        navBackdrop.addEventListener('click', closeDrawer);
    }

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
            closeDrawer();
        }
    });

    /* ── Horizontal row scroll arrows (legacy rows) ── */
    document.querySelectorAll('.row-scroll-wrap').forEach(function (wrap) {
        var track = wrap.querySelector('.row-track');
        var left = wrap.querySelector('.row-arrow-left');
        var right = wrap.querySelector('.row-arrow-right');
        if (!track) return;

        var scrollAmount = function () { return Math.max(track.clientWidth * 0.75, 280); };

        if (left) {
            left.addEventListener('click', function () {
                track.scrollBy({ left: -scrollAmount(), behavior: 'smooth' });
            });
        }
        if (right) {
            right.addEventListener('click', function () {
                track.scrollBy({ left: scrollAmount(), behavior: 'smooth' });
            });
        }

        var isDown = false, startX, scrollLeft;
        track.addEventListener('mousedown', function (e) {
            isDown = true;
            startX = e.pageX - track.offsetLeft;
            scrollLeft = track.scrollLeft;
            track.style.cursor = 'grabbing';
        });
        track.addEventListener('mouseleave', function () { isDown = false; track.style.cursor = ''; });
        track.addEventListener('mouseup', function () { isDown = false; track.style.cursor = ''; });
        track.addEventListener('mousemove', function (e) {
            if (!isDown) return;
            e.preventDefault();
            var x = e.pageX - track.offsetLeft;
            track.scrollLeft = scrollLeft - (x - startX) * 1.5;
        });
    });

    document.querySelectorAll('.content-row').forEach(function (row, ri) {
        row.style.animationDelay = (ri * 0.08) + 's';
        row.querySelectorAll('.premium-card, .continue-card').forEach(function (card, ci) {
            card.style.animationDelay = (ri * 0.08 + ci * 0.04) + 's';
        });
    });
})();
