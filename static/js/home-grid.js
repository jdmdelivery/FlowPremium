(function () {
    var searchInput = document.getElementById("home-search");
    var grid = document.getElementById("series-grid");
    var noResults = document.getElementById("home-no-results");
    var filterBar = document.getElementById("home-filters");
    var activeFilter = "popular";

    function readQueryFilter() {
        var params = new URLSearchParams(window.location.search);
        var f = params.get("filter");
        if (f && filterBar) {
            activeFilter = f;
            filterBar.querySelectorAll(".dramawave-filter-pill").forEach(function (btn) {
                btn.classList.toggle("is-active", btn.getAttribute("data-filter") === f);
            });
        }
    }

    function applyFilters() {
        if (!grid) return;
        var q = (searchInput && searchInput.value || "").trim().toLowerCase();
        var cards = grid.querySelectorAll(".dramawave-grid-card");
        var visible = 0;
        cards.forEach(function (card) {
            var hay = card.getAttribute("data-search") || "";
            var filters = (card.getAttribute("data-filters") || "").split(/\s+/);
            var matchSearch = !q || hay.indexOf(q) !== -1;
            var matchFilter = filters.indexOf(activeFilter) !== -1;
            var show = matchSearch && matchFilter;
            card.classList.toggle("hidden", !show);
            if (show) visible += 1;
        });
        if (noResults) {
            noResults.classList.toggle("hidden", visible > 0 || cards.length === 0);
        }
    }

    readQueryFilter();
    applyFilters();

    if (searchInput) {
        searchInput.addEventListener("input", applyFilters);
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
})();
