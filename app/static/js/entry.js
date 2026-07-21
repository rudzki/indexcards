function copyEntryLink(btn) {
    navigator.clipboard.writeText(window.location.href).then(function() {
        var icon = btn.querySelector('i');
        icon.className = 'bi bi-check';
        setTimeout(function() { icon.className = 'bi bi-link-45deg'; }, 1500);
    });
}

(function() {
    var cache = {};
    var card = null;
    var showTimer = null;
    var hideTimer = null;

    function esc(s) {
        return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    function getCard() {
        if (!card) {
            card = document.createElement('div');
            card.className = 'link-preview-card';
            document.body.appendChild(card);
            card.addEventListener('mouseenter', function() { clearTimeout(hideTimer); });
            card.addEventListener('mouseleave', scheduleHide);
        }
        return card;
    }

    function showCard(anchor, data) {
        var c = getCard();
        c.innerHTML = '<strong class="lpc-title">' + esc(data.title) + '</strong>'
            + (data.summary ? '<p class="lpc-summary">' + esc(data.summary) + '</p>' : '');

        var rect = anchor.getBoundingClientRect();
        c.style.top = '-9999px';
        c.style.left = '-9999px';
        c.classList.add('lpc-visible');
        var cw = Math.min(c.offsetWidth, window.innerWidth - 32);
        var ch = c.offsetHeight;

        var top = rect.bottom + 8;
        if (top + ch > window.innerHeight - 8) top = rect.top - ch - 8;
        var left = rect.left;
        if (left + cw > window.innerWidth - 8) left = window.innerWidth - cw - 8;
        if (left < 8) left = 8;

        c.style.top = top + 'px';
        c.style.left = left + 'px';
    }

    function scheduleHide() {
        clearTimeout(hideTimer);
        hideTimer = setTimeout(function() {
            if (card) card.classList.remove('lpc-visible');
        }, 150);
    }

    var internal = /^\/(\w[\w-]*)\/$/;

    document.querySelectorAll('.entry-body a[href]').forEach(function(anchor) {
        var m = anchor.getAttribute('href').match(internal);
        if (!m) return;
        var slug = m[1];

        anchor.addEventListener('mouseenter', function() {
            clearTimeout(hideTimer);
            clearTimeout(showTimer);
            showTimer = setTimeout(function() {
                if (slug in cache) {
                    if (cache[slug]) showCard(anchor, cache[slug]);
                    return;
                }
                fetch('/api/entry/' + slug + '/preview')
                    .then(function(r) { return r.ok ? r.json() : null; })
                    .then(function(data) {
                        cache[slug] = data || false;
                        if (data && data.title) showCard(anchor, data);
                    });
            }, 250);
        });

        anchor.addEventListener('mouseleave', function() {
            clearTimeout(showTimer);
            scheduleHide();
        });
    });
})();

document.querySelectorAll('.footnote-ref a[data-footnote]').forEach(function(el) {
    var tip = document.createElement('span');
    tip.className = 'footnote-tooltip';
    tip.textContent = el.getAttribute('data-footnote');
    el.parentNode.appendChild(tip);
    el.addEventListener('mouseenter', function() { tip.classList.add('visible'); });
    el.addEventListener('mouseleave', function() { tip.classList.remove('visible'); });
});

(function() {
    document.querySelectorAll('.author-name[data-bio]').forEach(function(el) {
        el.addEventListener('click', function(e) {
            e.stopPropagation();
            var existing = document.querySelector('.bio-popup');
            if (existing) { existing.remove(); return; }
            var popup = document.createElement('div');
            popup.className = 'bio-popup';
            var avatar = el.getAttribute('data-avatar');
            if (avatar) {
                var avatarImg = document.createElement('img');
                avatarImg.className = 'bio-popup-avatar';
                avatarImg.src = avatar;
                avatarImg.alt = '';
                popup.appendChild(avatarImg);
            }
            var bio = el.getAttribute('data-bio');
            if (bio) {
                var bioText = document.createElement('div');
                bioText.className = 'bio-popup-text';
                bioText.textContent = bio;
                popup.appendChild(bioText);
            }
            var link = el.getAttribute('data-link');
            if (link) {
                var linkEl = document.createElement('a');
                linkEl.className = 'bio-popup-link';
                linkEl.href = link;
                linkEl.textContent = link.replace(/^https?:\/\//i, '');
                linkEl.target = '_blank';
                linkEl.rel = 'noopener noreferrer';
                popup.appendChild(linkEl);
            }
            var rect = el.getBoundingClientRect();
            popup.style.left = (rect.left + window.scrollX) + 'px';
            popup.style.top = '-9999px';
            popup.style.setProperty('--arrow-left', Math.round(rect.width / 2) + 'px');
            document.body.appendChild(popup);
            popup.style.top = (rect.top + window.scrollY - popup.offsetHeight - 8) + 'px';
            document.addEventListener('click', function dismiss() {
                popup.remove();
                document.removeEventListener('click', dismiss);
            });
        });
    });
})();
