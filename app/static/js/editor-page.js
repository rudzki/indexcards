(function() {
    var title = document.getElementById('title');
    var slug = document.getElementById('slug');
    if (!title || !slug || slug.dataset.isNew !== 'true') return;
    var manual = false;
    function makeSlug(s) {
        return s.toLowerCase().trim()
            .replace(/[^\w\s-]/g, '')
            .replace(/[\s_]+/g, '-')
            .replace(/-+/g, '-')
            .replace(/^-+|-+$/g, '');
    }
    title.addEventListener('input', function() {
        if (!manual) slug.value = makeSlug(title.value);
    });
    slug.addEventListener('input', function() { manual = true; });
    slug.addEventListener('blur', function() {
        if (!slug.value.trim()) { manual = false; slug.value = makeSlug(title.value); }
    });
})();

(function() {
    var showInNav = document.getElementById('show_in_nav');
    var navPositionField = document.getElementById('nav_position_field');
    var navPosition = document.getElementById('nav_position');
    if (!showInNav || !navPositionField) return;
    showInNav.addEventListener('change', function() {
        navPositionField.style.display = showInNav.checked ? '' : 'none';
        if (!showInNav.checked && navPosition) navPosition.value = '';
    });
})();

(function() {
    var form = document.querySelector('.editor-form');
    if (!form || !form.dataset.lockType || !form.dataset.lockId) return;
    var LOCK_URL = '/api/lock/' + form.dataset.lockType + '/' + form.dataset.lockId;
    var heartbeat = setInterval(function() {
        fetch(LOCK_URL, { method: 'POST', credentials: 'same-origin' });
    }, 30000);
    form.addEventListener('submit', function() {
        clearInterval(heartbeat);
        navigator.sendBeacon(LOCK_URL + '/release');
    });
    window.addEventListener('pagehide', function() {
        clearInterval(heartbeat);
        navigator.sendBeacon(LOCK_URL + '/release');
    });
})();
