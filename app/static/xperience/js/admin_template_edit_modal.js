/**
 * Modais de template (admin home · Templates de apontamento): criar e editar.
 */
(function () {
    function wireTemplateCreate() {
        var dialog = document.getElementById("admin-tt-template-create-dialog");
        if (!dialog || typeof dialog.showModal !== "function") {
            return;
        }

        var openBtn = document.getElementById("admin-tt-template-create-open");
        if (openBtn) {
            openBtn.addEventListener("click", function () {
                dialog.showModal();
            });
        }

        var closeBtn = document.getElementById("admin-tt-template-create-close");
        if (closeBtn) {
            closeBtn.addEventListener("click", function () {
                dialog.close();
            });
        }

        dialog.addEventListener("click", function (ev) {
            if (ev.target === dialog) {
                dialog.close();
            }
        });

        if (dialog.getAttribute("data-auto-open") === "1") {
            dialog.showModal();
            dialog.removeAttribute("data-auto-open");
        }
    }

    function wireTemplateEdit() {
        var dialog = document.getElementById("admin-tt-template-edit-dialog");
        if (!dialog || typeof dialog.showModal !== "function") {
            return;
        }

        var idInput = document.getElementById("admin-tt-template-edit-id");
        var nameInput = document.getElementById("id_tpl_edit-name");

        function checkboxEl(fieldName) {
            return document.getElementById("id_tpl_edit-" + fieldName);
        }

        function openFromButton(btn) {
            var d = btn.dataset;
            if (idInput) {
                idInput.value = d.templateId || "";
            }
            if (nameInput) {
                nameInput.value = d.name || "";
            }
            var pairs = [
                ["useClient", "use_client"],
                ["useProject", "use_project"],
                ["useTask", "use_task"],
                ["useType", "use_type"],
                ["useDescription", "use_description"],
            ];
            pairs.forEach(function (p) {
                var el = checkboxEl(p[1]);
                if (!el) {
                    return;
                }
                var raw = d[p[0]];
                el.checked = raw === "1" || raw === "true";
            });
            dialog.showModal();
        }

        document.querySelectorAll("[data-admin-tt-template-edit]").forEach(function (btn) {
            btn.addEventListener("click", function () {
                openFromButton(this);
            });
        });

        var closeBtn = document.getElementById("admin-tt-template-edit-close");
        if (closeBtn) {
            closeBtn.addEventListener("click", function () {
                dialog.close();
            });
        }

        dialog.addEventListener("click", function (ev) {
            if (ev.target === dialog) {
                dialog.close();
            }
        });

        if (dialog.getAttribute("data-auto-open") === "1") {
            dialog.showModal();
            dialog.removeAttribute("data-auto-open");
        }
    }

    wireTemplateCreate();
    wireTemplateEdit();
})();
