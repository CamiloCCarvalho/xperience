/**
 * Menu ⋯ dos cards de workspace (gestão): fecha ao clicar fora e mantém só um aberto.
 */
(function () {
    var menus = document.querySelectorAll(".workspace-card-menu");
    if (!menus.length) {
        return;
    }

    menus.forEach(function (root) {
        root.addEventListener("toggle", function () {
            if (!root.open) {
                return;
            }
            menus.forEach(function (other) {
                if (other !== root) {
                    other.open = false;
                }
            });
        });
    });

    document.addEventListener("click", function (ev) {
        var t = ev.target;
        menus.forEach(function (root) {
            if (!root.open) {
                return;
            }
            if (root.contains(t)) {
                return;
            }
            root.open = false;
        });
    });
})();
