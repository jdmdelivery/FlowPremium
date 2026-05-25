(function () {
    'use strict';

    var seriesSelect = document.getElementById('series-select');
    var seasonSelect = document.getElementById('season-select');
    var noSeasonsMsg = document.getElementById('no-seasons-msg');
    var addSeasonLink = document.getElementById('add-season-link');

    if (!seriesSelect || !seasonSelect) return;

    var allSeasonOptions = Array.from(seasonSelect.querySelectorAll('option[data-series-id]'));

    function filterSeasons() {
        var seriesId = seriesSelect.value;
        var currentValue = seasonSelect.value;
        var visibleCount = 0;
        var firstVisible = null;

        allSeasonOptions.forEach(function (opt) {
            var match = opt.getAttribute('data-series-id') === seriesId;
            opt.hidden = !match;
            opt.disabled = !match;
            if (match) {
                visibleCount += 1;
                if (!firstVisible) firstVisible = opt;
            }
        });

        var placeholder = seasonSelect.querySelector('option:not([data-series-id])');
        if (placeholder) {
            placeholder.selected = visibleCount === 0;
        }

        var stillValid = allSeasonOptions.some(function (opt) {
            return !opt.hidden && opt.value === currentValue;
        });

        if (stillValid) {
            seasonSelect.value = currentValue;
        } else if (firstVisible) {
            seasonSelect.value = firstVisible.value;
        } else {
            seasonSelect.value = '';
        }

        if (noSeasonsMsg) {
            noSeasonsMsg.hidden = visibleCount > 0 || !seriesId;
        }
        if (addSeasonLink && seriesId) {
            addSeasonLink.href = '/admin/streaming/series/' + seriesId + '/seasons';
        }
    }

    seriesSelect.addEventListener('change', filterSeasons);
    filterSeasons();
})();
