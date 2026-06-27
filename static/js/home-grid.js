(function () {
    "use strict";

    var DEBOUNCE_MS = 250;

    function normalizeText(text) {
        return (text || "")
            .toString()
            .toLowerCase()
            .normalize("NFD")
            .replace(/[\u0300-\u036f]/g, "")
            .trim();
    }

    var searchInput = document.getElementById("home-search");
    var searchClear = document.getElementById("home-search-clear");
    var searchWrap = document.getElementById("home-search-wrap");
    var grid = document.getElementById("series-grid");
    var noResults = document.getElementById("home-no-results");
    var noResultsQuery = document.getElementById("home-no-results-query");
    var filterBar = document.getElementById("home-filters");
    var activeFilter = "discover";
    var debounceTimer = null;
    var allCards = [];

    function readQueryFilter() {
        var params = new URLSearchParams(window.location.search);
        var f = params.get("filter");
        if (!f || !filterBar) return;
        if (["popular", "new", "exclusive", "discover"].indexOf(f) === -1) return;
        activeFilter = f;
        filterBar.querySelectorAll(".dramawave-filter-pill").forEach(function (btn) {
            btn.classList.toggle("is-active", btn.getAttribute("data-filter") === f);
        });
    }

    function cacheCards() {
        if (!grid) return;
        allCards = Array.prototype.slice.call(
            grid.querySelectorAll(".dramawave-grid-card")
        );
    }

    function matchesSearch(card, normalizedQuery) {
        if (!normalizedQuery) return true;
        var hay = normalizeText(card.getAttribute("data-search") || "");
        return hay.indexOf(normalizedQuery) !== -1;
    }

    function matchesFilter(card, hasSearch) {
        if (hasSearch) return true;
        var filters = (card.getAttribute("data-filters") || "").split(/\s+/).filter(Boolean);
        return filters.indexOf(activeFilter) !== -1;
    }

    function firstVisibleCard() {
        for (var i = 0; i < allCards.length; i += 1) {
            if (!allCards[i].classList.contains("hidden")) {
                return allCards[i];
            }
        }
        return null;
    }

    function updateClearButton() {
        if (!searchClear || !searchInput) return;
        var hasText = Boolean((searchInput.value || "").trim());
        searchClear.classList.toggle("hidden", !hasText);
        searchClear.hidden = !hasText;
    }

    function applyFilters() {
        if (!grid) return;

        var rawQuery = (searchInput && searchInput.value) || "";
        var normalizedQuery = normalizeText(rawQuery);
        var visible = 0;

        var hasSearch = Boolean(normalizedQuery);

        allCards.forEach(function (card) {
            var show = matchesFilter(card, hasSearch) && matchesSearch(card, normalizedQuery);
            card.classList.toggle("hidden", !show);
            if (show) visible += 1;
        });

        if (noResults) {
            var showEmpty = allCards.length > 0 && visible === 0;
            noResults.classList.toggle("hidden", !showEmpty);
            if (noResultsQuery) {
                noResultsQuery.textContent = rawQuery.trim();
            }
        }

        updateClearButton();
    }

    function scheduleApply() {
        if (debounceTimer) clearTimeout(debounceTimer);
        debounceTimer = setTimeout(applyFilters, DEBOUNCE_MS);
    }

    function clearSearch() {
        if (!searchInput) return;
        searchInput.value = "";
        updateClearButton();
        applyFilters();
        searchInput.focus();
    }

    readQueryFilter();
    cacheCards();
    applyFilters();

    if (searchInput) {
        searchInput.addEventListener("input", scheduleApply);
        searchInput.addEventListener("focus", function () {
            if (searchWrap) searchWrap.classList.add("is-focused");
        });
        searchInput.addEventListener("blur", function () {
            if (searchWrap) searchWrap.classList.remove("is-focused");
        });
        searchInput.addEventListener("keydown", function (e) {
            if (e.key === "Enter") {
                e.preventDefault();
                var first = firstVisibleCard();
                if (first && first.href) {
                    window.location.href = first.href;
                }
            }
            if (e.key === "Escape") {
                clearSearch();
            }
        });
    }

    if (searchClear) {
        searchClear.addEventListener("click", function (e) {
            e.preventDefault();
            clearSearch();
        });
    }

    if (filterBar) {
        filterBar.addEventListener("click", function (e) {
            var btn = e.target.closest(".dramawave-filter-pill");
            if (!btn) return;
            activeFilter = btn.getAttribute("data-filter") || "discover";
            filterBar.querySelectorAll(".dramawave-filter-pill").forEach(function (pill) {
                pill.classList.toggle("is-active", pill === btn);
            });
            applyFilters();
        });
    }

    window.FlowHomeSearch = {
        normalizeText: normalizeText,
        applyFilters: applyFilters,
    };
})();
