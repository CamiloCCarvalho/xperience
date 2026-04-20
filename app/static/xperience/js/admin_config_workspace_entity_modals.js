/**
 * Modais criar/editar: clientes, projetos e tarefas (admin · configuração do workspace).
 */
(function () {
    function wireDialogPair(opts) {
        var createDialog = document.getElementById(opts.createDialogId);
        var editDialog = opts.editDialogId ? document.getElementById(opts.editDialogId) : null;

        if (createDialog && typeof createDialog.showModal === "function") {
            var createOpen = document.getElementById(opts.createOpenId);
            if (createOpen) {
                createOpen.addEventListener("click", function () {
                    createDialog.showModal();
                });
            }
            var createClose = document.getElementById(opts.createCloseId);
            if (createClose) {
                createClose.addEventListener("click", function () {
                    createDialog.close();
                });
            }
            createDialog.addEventListener("click", function (ev) {
                if (ev.target === createDialog) {
                    createDialog.close();
                }
            });
            if (createDialog.getAttribute("data-auto-open") === "1") {
                createDialog.showModal();
                createDialog.removeAttribute("data-auto-open");
            }
        }

        if (!editDialog || typeof editDialog.showModal !== "function") {
            return;
        }

        function wireEditOpen(openFromButton) {
            document.querySelectorAll(opts.editButtonSelector).forEach(function (btn) {
                btn.addEventListener("click", function () {
                    openFromButton(this);
                });
            });
        }

        var editClose = document.getElementById(opts.editCloseId);
        if (editClose) {
            editClose.addEventListener("click", function () {
                editDialog.close();
            });
        }
        editDialog.addEventListener("click", function (ev) {
            if (ev.target === editDialog) {
                editDialog.close();
            }
        });
        if (editDialog.getAttribute("data-auto-open") === "1") {
            editDialog.showModal();
            editDialog.removeAttribute("data-auto-open");
        }

        wireEditOpen(opts.openEditFromButton);
    }

    wireDialogPair({
        createDialogId: "admin-config-cli-create-dialog",
        createOpenId: "admin-config-cli-create-open",
        createCloseId: "admin-config-cli-create-close",
        editDialogId: "admin-config-cli-edit-dialog",
        editCloseId: "admin-config-cli-edit-close",
        editButtonSelector: "[data-admin-config-client-edit]",
        openEditFromButton: function (btn) {
            var d = btn.dataset;
            var dialog = document.getElementById("admin-config-cli-edit-dialog");
            var idInput = document.getElementById("admin-config-cli-edit-id");
            if (idInput) {
                idInput.value = d.clientId || "";
            }
            function setInput(id, key) {
                var el = document.getElementById(id);
                if (!el) {
                    return;
                }
                var raw = d[key];
                el.value = raw == null || raw === "" ? "" : String(raw);
            }
            setInput("id_cli_edit-name", "name");
            setInput("id_cli_edit-document", "document");
            setInput("id_cli_edit-email", "email");
            setInput("id_cli_edit-phone", "phone");
            setInput("id_cli_edit-budget", "budget");
            var cb = document.getElementById("id_cli_edit-is_active");
            if (cb) {
                cb.checked = d.isActive === "1";
            }
            if (dialog) {
                dialog.showModal();
            }
        },
    });

    wireDialogPair({
        createDialogId: "admin-config-prj-create-dialog",
        createOpenId: "admin-config-prj-create-open",
        createCloseId: "admin-config-prj-create-close",
        editDialogId: "admin-config-prj-edit-dialog",
        editCloseId: "admin-config-prj-edit-close",
        editButtonSelector: "[data-admin-config-project-edit]",
        openEditFromButton: function (btn) {
            var d = btn.dataset;
            var dialog = document.getElementById("admin-config-prj-edit-dialog");
            var idInput = document.getElementById("admin-config-prj-edit-id");
            if (idInput) {
                idInput.value = d.projectId || "";
            }
            var clientSel = document.getElementById("id_prj_edit-client");
            if (clientSel) {
                clientSel.value = d.clientId || "";
            }
            var nameEl = document.getElementById("id_prj_edit-name");
            if (nameEl) {
                nameEl.value = d.name || "";
            }
            var descEl = document.getElementById("id_prj_edit-description");
            if (descEl) {
                var desc = d.descriptionRaw;
                descEl.value = desc == null ? "" : String(desc);
            }
            var budgetEl = document.getElementById("id_prj_edit-budget");
            if (budgetEl) {
                budgetEl.value = d.budget != null && d.budget !== "" ? String(d.budget) : "";
            }
            var deadlineEl = document.getElementById("id_prj_edit-deadline");
            if (deadlineEl) {
                deadlineEl.value = d.deadline || "";
            }
            var hoursEl = document.getElementById("id_prj_edit-estimated_hours");
            if (hoursEl) {
                hoursEl.value = d.estimatedHours != null && d.estimatedHours !== "" ? String(d.estimatedHours) : "";
            }
            var activeCb = document.getElementById("id_prj_edit-is_active");
            if (activeCb) {
                activeCb.checked = d.isActive === "1";
            }
            if (dialog) {
                dialog.showModal();
            }
        },
    });

    wireDialogPair({
        createDialogId: "admin-config-tsk-create-dialog",
        createOpenId: "admin-config-tsk-create-open",
        createCloseId: "admin-config-tsk-create-close",
        editDialogId: "admin-config-tsk-edit-dialog",
        editCloseId: "admin-config-tsk-edit-close",
        editButtonSelector: "[data-admin-config-task-edit]",
        openEditFromButton: function (btn) {
            var d = btn.dataset;
            var dialog = document.getElementById("admin-config-tsk-edit-dialog");
            var idInput = document.getElementById("admin-config-tsk-edit-id");
            if (idInput) {
                idInput.value = d.taskId || "";
            }
            var projSel = document.getElementById("id_tsk_edit-project");
            if (projSel) {
                projSel.value = d.projectId || "";
            }
            var nameEl = document.getElementById("id_tsk_edit-name");
            if (nameEl) {
                nameEl.value = d.name || "";
            }
            var cb = document.getElementById("id_tsk_edit-is_active");
            if (cb) {
                cb.checked = d.isActive === "1";
            }
            if (dialog) {
                dialog.showModal();
            }
        },
    });
})();
