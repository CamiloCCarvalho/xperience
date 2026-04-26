/* register_admin_plan.js
   Formatação de validade, CPF e acordeão de planos
*/

/* -------------------------------------------------------
   Validade: formatação automática MM/AA
------------------------------------------------------- */
(function () {
    var el = document.getElementById('expiry_date');
    if (!el) return;
    el.setAttribute('inputmode', 'numeric');

    function onlyDigits(s) { return (s || '').replace(/\D/g, ''); }
    function fmt(d) { d = d.slice(0, 4); return d.length > 2 ? d.slice(0, 2) + '/' + d.slice(2) : d; }
    function cursorPos(formatted, nDigits) {
        var d = 0;
        for (var i = 0; i < formatted.length; i++) {
            if (/\d/.test(formatted[i])) d++;
            if (d === nDigits) return i + 1;
        }
        return formatted.length;
    }

    el.addEventListener('input', function () {
        var sel = el.selectionStart, left = el.value.slice(0, sel), ld = onlyDigits(left).length;
        var f = fmt(onlyDigits(el.value));
        el.value = f;
        var p = cursorPos(f, ld); el.setSelectionRange(p, p);
    });

    el.addEventListener('keydown', function (e) {
        if (e.key === 'Backspace' && el.selectionStart === 3 && el.value[2] === '/') {
            e.preventDefault();
            var d = onlyDigits(el.value).slice(0, 1);
            el.value = fmt(d);
            el.setSelectionRange(el.value.length, el.value.length);
        }
    });

    el.addEventListener('paste', function (e) {
        e.preventDefault();
        var t = (e.clipboardData || window.clipboardData).getData('text') || '';
        el.value = fmt(onlyDigits(t).slice(0, 4));
        el.setSelectionRange(el.value.length, el.value.length);
    });
})();

/* -------------------------------------------------------
   CPF: formatação automática
------------------------------------------------------- */
(function () {
    var el = document.getElementById('cpf');
    if (!el) return;

    function onlyDigits(s) { return (s || '').replace(/\D/g, ''); }
    function fmt(d) {
        d = d.slice(0, 11);
        if (d.length <= 3) return d;
        if (d.length <= 6) return d.slice(0, 3) + '.' + d.slice(3);
        if (d.length <= 9) return d.slice(0, 3) + '.' + d.slice(3, 6) + '.' + d.slice(6);
        return d.slice(0, 3) + '.' + d.slice(3, 6) + '.' + d.slice(6, 9) + '-' + d.slice(9);
    }
    function cursorPos(formatted, nDigits) {
        var d = 0;
        for (var i = 0; i < formatted.length; i++) {
            if (/\d/.test(formatted[i])) d++;
            if (d === nDigits) return i + 1;
        }
        return formatted.length;
    }

    el.addEventListener('input', function () {
        var sel = el.selectionStart, left = el.value.slice(0, sel), ld = onlyDigits(left).length;
        var f = fmt(onlyDigits(el.value));
        el.value = f;
        var p = cursorPos(f, ld); el.setSelectionRange(p, p);
    });

    el.addEventListener('paste', function (e) {
        e.preventDefault();
        var t = (e.clipboardData || window.clipboardData).getData('text') || '';
        el.value = fmt(onlyDigits(t));
        el.setSelectionRange(el.value.length, el.value.length);
    });
})();

/* -------------------------------------------------------
   Acordeão de planos
------------------------------------------------------- */
(function () {
    var entries = document.querySelectorAll('.rap-plan-entry');
    entries.forEach(function (entry) {
        var radio = entry.querySelector('.rap-plan-radio');
        var header = entry.querySelector('.rap-plan-header');

        function open() {
            entries.forEach(function (e) { e.classList.remove('is-open'); });
            entry.classList.add('is-open');
            if (radio) radio.checked = true;
        }

        header.addEventListener('click', function () { open(); });
        header.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); }
        });
        if (radio) {
            radio.addEventListener('change', function () { if (radio.checked) open(); });
        }
    });
})();
