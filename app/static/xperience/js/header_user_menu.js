/**
 * Fecha o menu do usuário (details#header-user-menu) ao clicar fora ou ao pressionar Escape.
 */
(function () {
    var root = document.getElementById("header-user-menu");
    if (!root || typeof root.open === "undefined") {
        return;
    }

    document.addEventListener("click", function (ev) {
        if (!root.open) {
            return;
        }
        var t = ev.target;
        if (root.contains(t)) {
            return;
        }
        root.open = false;
    });

    document.addEventListener("keydown", function (ev) {
        if (ev.key === "Escape" && root.open) {
            root.open = false;
        }
    });
})();
