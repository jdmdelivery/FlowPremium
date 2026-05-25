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

    /* ── Nav scroll + mobile toggle ── */
    var nav = document.getElementById('main-nav');
    var navToggle = document.getElementById('nav-toggle');
    var navLinks = document.getElementById('nav-links');

    if (nav) {
        window.addEventListener('scroll', function () {
            nav.classList.toggle('nav-scrolled', window.scrollY > 40);
        }, { passive: true });
    }

    if (navToggle && navLinks) {
        navToggle.addEventListener('click', function () {
            navLinks.classList.toggle('is-open');
        });
        navLinks.querySelectorAll('a').forEach(function (link) {
            link.addEventListener('click', function () {
                navLinks.classList.remove('is-open');
            });
        });
    }

    /* ── Horizontal row scroll arrows ── */
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

        /* Touch momentum hint */
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

    /* ── Stagger card animations ── */
    document.querySelectorAll('.content-row').forEach(function (row, ri) {
        row.style.animationDelay = (ri * 0.08) + 's';
        row.querySelectorAll('.premium-card, .continue-card').forEach(function (card, ci) {
            card.style.animationDelay = (ri * 0.08 + ci * 0.04) + 's';
        });
    });
})();
