(function () {
    'use strict';

    var statusEl = document.getElementById('storage-status-text');
    var detailsEl = document.getElementById('storage-details');
    var testBtn = document.getElementById('btn-test-r2');
    var testResultEl = document.getElementById('storage-test-result');

    if (!statusEl) return;

    function renderStatus(data) {
        var connected = data.r2_connected || (data.connected && data.bucket_active);
        statusEl.textContent = connected
            ? '✅ R2 conectado'
            : (data.configured ? '❌ ' + (data.message || 'R2 no conectado') : 'Almacenamiento local (STORAGE_PROVIDER≠r2)');

        detailsEl.innerHTML = '';
        var rows = [
            ['Bucket', data.bucket || '—'],
            ['Bucket activo', data.bucket_active ? 'Sí' : 'No'],
            ['Total series', String(data.total_series != null ? data.total_series : data.series_count || 0)],
            ['Total episodios', String(data.total_episodes != null ? data.total_episodes : data.episodes_count || 0)],
        ];
        rows.forEach(function (row) {
            var dt = document.createElement('dt');
            dt.textContent = row[0];
            var dd = document.createElement('dd');
            dd.textContent = row[1];
            detailsEl.appendChild(dt);
            detailsEl.appendChild(dd);
        });
    }

    function loadStatus() {
        fetch('/admin/storage-status', { credentials: 'same-origin' })
            .then(function (res) {
                if (!res.ok) throw new Error('HTTP ' + res.status);
                return res.json();
            })
            .then(renderStatus)
            .catch(function () {
                statusEl.textContent = '❌ No se pudo cargar el estado de almacenamiento';
            });
    }

    if (testBtn) {
        testBtn.addEventListener('click', function () {
            testResultEl.textContent = 'Probando…';
            fetch('/admin/storage/test-r2', {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'X-Requested-With': 'XMLHttpRequest' },
            })
                .then(function (res) {
                    if (!res.ok) throw new Error('HTTP ' + res.status);
                    return res.json();
                })
                .then(function (data) {
                    testResultEl.textContent = data.message || (data.ok ? '✅ Conectado' : '❌ Error de conexión');
                    loadStatus();
                })
                .catch(function () {
                    testResultEl.textContent = '❌ Error de conexión';
                });
        });
    }

    loadStatus();
})();
