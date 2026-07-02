function csrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.content : '';
}

function showToast(category, message, duration) {
    var el = document.createElement('div');
    el.className = 'toast toast-' + category;
    if (category === 'error' || category === 'warn') el.setAttribute('role', 'alert');
    var span = document.createElement('span');
    span.textContent = message;
    var closeBtn = document.createElement('button');
    closeBtn.className = 'toast-close';
    closeBtn.innerHTML = '&times;';
    closeBtn.addEventListener('click', function() { el.remove(); });
    el.appendChild(span);
    el.appendChild(closeBtn);
    document.getElementById('toast-container').appendChild(el);
    requestAnimationFrame(function() { el.classList.add('toast-visible'); });
    setTimeout(function() {
        el.classList.remove('toast-visible');
        setTimeout(function() { el.remove(); }, 300);
    }, duration || 4000);
}

(function() {
    var el = document.getElementById('flash-data');
    if (!el) return;
    var flashes = JSON.parse(el.textContent);
    flashes.forEach(function(f) { showToast(f[0], f[1]); });
})();

function confirmDialog(message, label, onConfirm) {
    var trigger = document.activeElement;
    var overlay = document.createElement('div');
    overlay.className = 'confirm-overlay';
    var backdrop = document.createElement('div');
    backdrop.className = 'confirm-backdrop';
    var bubble = document.createElement('div');
    bubble.className = 'confirm-bubble';
    bubble.setAttribute('role', 'dialog');
    bubble.setAttribute('aria-modal', 'true');
    bubble.setAttribute('aria-labelledby', 'confirm-msg');
    var msg = document.createElement('p');
    msg.className = 'confirm-message';
    msg.id = 'confirm-msg';
    msg.textContent = message;
    var actions = document.createElement('div');
    actions.className = 'confirm-actions';
    var cancel = document.createElement('button');
    cancel.type = 'button';
    cancel.className = 'btn';
    cancel.textContent = 'Cancel';
    var ok = document.createElement('button');
    ok.type = 'button';
    ok.className = 'btn btn-danger';
    ok.textContent = label || 'Confirm';
    actions.appendChild(cancel);
    actions.appendChild(ok);
    bubble.appendChild(msg);
    bubble.appendChild(actions);
    overlay.appendChild(backdrop);
    overlay.appendChild(bubble);
    document.body.appendChild(overlay);
    function close() {
        overlay.remove();
        if (trigger && trigger.focus) trigger.focus();
    }
    bubble.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') { close(); return; }
        if (e.key === 'Tab') {
            e.preventDefault();
            (document.activeElement === ok ? cancel : ok).focus();
        }
    });
    backdrop.addEventListener('click', close);
    cancel.addEventListener('click', close);
    ok.addEventListener('click', function() { close(); onConfirm(); });
    cancel.focus();
}

(function() {
    var btn = document.getElementById('theme-toggle');
    if (!btn) return;
    btn.addEventListener('click', function() {
        var current = document.documentElement.getAttribute('data-theme');
        var isDark = current !== 'light';
        var next = isDark ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', next);
        localStorage.setItem('theme', next);
    });
})();

function askConfirm(e) {
    e.preventDefault();
    var el = e.currentTarget || e.target;
    var message = el.dataset.confirm;
    var label = el.dataset.confirmLabel;
    confirmDialog(message, label, function() {
        var formAttr = el.getAttribute && el.getAttribute('form');
        var form = (formAttr ? document.getElementById(formAttr) : null)
                   || el.form
                   || (el.closest ? el.closest('form') : null);
        if (!form && el.tagName === 'FORM') form = el;
        if (form) {
            if (el.tagName === 'BUTTON' && el.name) {
                var h = document.createElement('input');
                h.type = 'hidden'; h.name = el.name; h.value = el.value;
                form.appendChild(h);
            }
            form.submit();
        }
    });
    return false;
}
