document.addEventListener('DOMContentLoaded', function () {
    var prog = document.getElementById('sse-progress');
    if (!prog) return;  // solo en una búsqueda en curso

    var searchId = prog.getAttribute('data-search-id');
    var log = document.getElementById('sse-log');
    var ICON = { running: '⟳', done: '✓', error: '✗' };

    function reloadSoon() { setTimeout(function () { location.reload(); }, 600); }

    // Fallback si el navegador no soporta SSE: vuelve al polling de toda la vida
    if (!('EventSource' in window)) {
        setTimeout(function () { location.reload(); }, 5000);
        return;
    }

    function renderRow(ev) {
        var key = 'sse-node-' + ev.node;
        var li = document.getElementById(key);
        if (!li) {
            li = document.createElement('li');
            li.id = key;
            log.appendChild(li);
        }
        var extra = (typeof ev.found !== 'undefined') ? ' (' + ev.found + ')' : '';
        li.className = 'sse-item sse-' + ev.status;
        li.innerHTML = '<span class="sse-ico">' + (ICON[ev.status] || '•') + '</span>'
            + '<span>' + (ev.label || ev.node) + extra + '</span>';
    }

    var es = new EventSource('/events/search/' + searchId);

    es.onmessage = function (e) {
        var ev;
        try { ev = JSON.parse(e.data); } catch (_) { return; }

        if (ev.node === '_pipeline') {
            if (ev.status === 'completed' || ev.status === 'error') {
                es.close();
                reloadSoon();  // re-render del resultado completo (server-side)
            }
            return;
        }
        renderRow(ev);
    };

    es.onerror = function () {
        // El server cierra el stream al terminar; EventSource intentaría reconectar.
        // Si la búsqueda ya no está corriendo, el reload mostrará el resultado final.
    };
});
