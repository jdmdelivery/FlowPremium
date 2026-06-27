(function () {
    var input = document.getElementById("episode-search");
    var btn = document.getElementById("episode-search-btn");
    var list = document.getElementById("episodes-list");
    var empty = document.getElementById("episodes-no-results");
    if (!input || !list) return;

    function filterEpisodes() {
        var q = (input.value || "").trim().toLowerCase();
        var cards = list.querySelectorAll(".dramawave-episode-card");
        var visible = 0;
        cards.forEach(function (card) {
            var hay = card.getAttribute("data-search") || "";
            var show = !q || hay.indexOf(q) !== -1;
            card.classList.toggle("hidden", !show);
            if (show) visible += 1;
        });
        if (empty) {
            empty.classList.toggle("hidden", visible > 0 || cards.length === 0);
        }
    }

    input.addEventListener("input", filterEpisodes);
    if (btn) {
        btn.addEventListener("click", filterEpisodes);
    }
    input.addEventListener("keydown", function (e) {
        if (e.key === "Enter") {
            e.preventDefault();
            filterEpisodes();
        }
    });
})();
