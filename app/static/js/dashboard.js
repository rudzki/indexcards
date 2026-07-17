// Below 700px the visibility/type sub-navs are hidden by CSS (see the
// max-width: 700px media query in style.css). Those filters are server-side
// query params, so hiding the controls leaves the filter silently in effect
// with no way to clear it. On load below that breakpoint, reset them to their
// defaults by stripping the params and re-fetching, so a filtered URL opened on
// a phone isn't narrowed by a control the viewer can't see. Keep the threshold
// in sync with the CSS. (Intentionally on-load only: a filter set on a wide
// screen survives a resize rather than being wiped mid-session.)
(function() {
    var mobile = window.matchMedia('(max-width: 700px)');

    function resetHiddenFilters() {
        if (!mobile.matches) return;
        var url = new URL(window.location.href);
        // 'all' (or absent) is already the default — only redirect when a filter
        // is actually narrowing the list, so status-filter taps on mobile (which
        // carry listed=all&stub=all in their links) don't trigger a needless reload.
        var listed = url.searchParams.get('listed');
        var stub = url.searchParams.get('stub');
        var narrowed = (listed && listed !== 'all') || (stub && stub !== 'all');
        if (!narrowed) return;
        url.searchParams.delete('listed');
        url.searchParams.delete('stub');
        window.location.replace(url.toString());  // re-runs the query with defaults
    }

    resetHiddenFilters();  // filtered URL opened on mobile
})();

(function() {
    var selectAll = document.getElementById('select-all');
    if (!selectAll) return;
    var checkboxes = document.querySelectorAll('.entry-checkbox');
    selectAll.addEventListener('change', function() {
        checkboxes.forEach(function(cb) { cb.checked = selectAll.checked; });
    });
    checkboxes.forEach(function(cb) {
        cb.addEventListener('change', function() {
            selectAll.checked = Array.from(checkboxes).every(function(c) { return c.checked; });
        });
    });
})();
