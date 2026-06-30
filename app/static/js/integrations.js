(function() {
    var btn = document.getElementById('copy-secret-btn');
    var input = document.getElementById('webhook-secret-input');
    if (!btn || !input) return;
    btn.addEventListener('click', function() {
        navigator.clipboard.writeText(input.value).then(function() {
            btn.textContent = 'Copied!';
            setTimeout(function() { btn.textContent = 'Copy'; }, 1500);
        });
    });
})();
