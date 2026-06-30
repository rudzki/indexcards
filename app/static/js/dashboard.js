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
