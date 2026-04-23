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

    function setSelectValueById(selectId, value) {
        var el = document.getElementById(selectId);
        if (!el) {
            return;
        }
        el.value = value == null || value === "" ? "" : String(value);
    }

    wireDialogPair({
        createDialogId: "admin-config-cash-create-dialog",
        createOpenId: "admin-config-cash-create-open",
        createCloseId: "admin-config-cash-create-close",
    });

    wireDialogPair({
        createDialogId: "admin-config-goal-create-dialog",
        createOpenId: "admin-config-goal-create-open",
        createCloseId: "admin-config-goal-create-close",
        editDialogId: "admin-config-goal-edit-dialog",
        editCloseId: "admin-config-goal-edit-close",
        editButtonSelector: "[data-admin-config-goal-edit]",
        openEditFromButton: function (btn) {
            var d = btn.dataset;
            var dialog = document.getElementById("admin-config-goal-edit-dialog");
            var idInput = document.getElementById("admin-config-goal-edit-id");
            if (idInput) {
                idInput.value = d.goalId || "";
            }
            setSelectValueById("id_goal_edit-client", d.clientId);
            setSelectValueById("id_goal_edit-project", d.projectId);
            setSelectValueById("id_goal_edit-visibility", d.visibility);
            var minAmount = document.getElementById("id_goal_edit-minimum_target_amount");
            if (minAmount) {
                minAmount.value =
                    d.minimumTargetAmount != null && d.minimumTargetAmount !== ""
                        ? String(d.minimumTargetAmount)
                        : "";
            }
            var minDate = document.getElementById("id_goal_edit-minimum_target_date");
            if (minDate) {
                minDate.value = d.minimumTargetDate || "";
            }
            var desiredAmount = document.getElementById("id_goal_edit-desired_target_amount");
            if (desiredAmount) {
                desiredAmount.value =
                    d.desiredTargetAmount != null && d.desiredTargetAmount !== ""
                        ? String(d.desiredTargetAmount)
                        : "";
            }
            var desiredDate = document.getElementById("id_goal_edit-desired_target_date");
            if (desiredDate) {
                desiredDate.value = d.desiredTargetDate || "";
            }
            var description = document.getElementById("id_goal_edit-description");
            if (description) {
                var desc = d.descriptionRaw;
                description.value = desc == null ? "" : String(desc);
            }
            if (dialog) {
                dialog.showModal();
            }
        },
    });

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

    wireDialogPair({
        createDialogId: "admin-config-ep-create-dialog",
        createOpenId: "admin-config-ep-create-open",
        createCloseId: "admin-config-ep-create-close",
        editDialogId: "admin-config-ep-edit-dialog",
        editCloseId: "admin-config-ep-edit-close",
        editButtonSelector: "[data-admin-config-ep-edit]",
        openEditFromButton: function (btn) {
            var d = btn.dataset;
            var dialog = document.getElementById("admin-config-ep-edit-dialog");
            var pkInput = document.getElementById("admin-config-ep-edit-pk");
            if (pkInput) {
                pkInput.value = d.epId || "";
            }
            setSelectValueById("id_ep_edit-user", d.userId);
            setSelectValueById("id_ep_edit-employment_status", d.employmentStatus);
            var hire = document.getElementById("id_ep_edit-hire_date");
            if (hire) {
                hire.value = d.hireDate || "";
            }
            var term = document.getElementById("id_ep_edit-termination_date");
            if (term) {
                term.value = d.terminationDate || "";
            }
            var titleEl = document.getElementById("id_ep_edit-current_job_title");
            if (titleEl) {
                titleEl.value = d.currentJobTitle || "";
            }
            if (dialog) {
                dialog.showModal();
            }
        },
    });

    wireDialogPair({
        createDialogId: "admin-config-jh-create-dialog",
        createOpenId: "admin-config-jh-create-open",
        createCloseId: "admin-config-jh-create-close",
        editDialogId: "admin-config-jh-edit-dialog",
        editCloseId: "admin-config-jh-edit-close",
        editButtonSelector: "[data-admin-config-jh-edit]",
        openEditFromButton: function (btn) {
            var d = btn.dataset;
            var dialog = document.getElementById("admin-config-jh-edit-dialog");
            var pkInput = document.getElementById("admin-config-jh-edit-pk");
            if (pkInput) {
                pkInput.value = d.jhId || "";
            }
            setSelectValueById("id_jh_edit-employee_profile", d.employeeProfileId);
            var titleEl = document.getElementById("id_jh_edit-job_title");
            if (titleEl) {
                titleEl.value = d.jobTitle || "";
            }
            var sd = document.getElementById("id_jh_edit-start_date");
            if (sd) {
                sd.value = d.startDate || "";
            }
            var ed = document.getElementById("id_jh_edit-end_date");
            if (ed) {
                ed.value = d.endDate || "";
            }
            if (dialog) {
                dialog.showModal();
            }
        },
    });

    wireDialogPair({
        createDialogId: "admin-config-ch-create-dialog",
        createOpenId: "admin-config-ch-create-open",
        createCloseId: "admin-config-ch-create-close",
        editDialogId: "admin-config-ch-edit-dialog",
        editCloseId: "admin-config-ch-edit-close",
        editButtonSelector: "[data-admin-config-ch-edit]",
        openEditFromButton: function (btn) {
            var d = btn.dataset;
            var dialog = document.getElementById("admin-config-ch-edit-dialog");
            var pkInput = document.getElementById("admin-config-ch-edit-pk");
            if (pkInput) {
                pkInput.value = d.chId || "";
            }
            setSelectValueById("id_ch_edit-employee_profile", d.employeeProfileId);
            setSelectValueById("id_ch_edit-compensation_type", d.compensationType);
            var ms = document.getElementById("id_ch_edit-monthly_salary");
            if (ms) {
                ms.value = d.monthlySalary != null && d.monthlySalary !== "" ? String(d.monthlySalary) : "";
            }
            var hr = document.getElementById("id_ch_edit-hourly_rate");
            if (hr) {
                hr.value = d.hourlyRate != null && d.hourlyRate !== "" ? String(d.hourlyRate) : "";
            }
            var mrh = document.getElementById("id_ch_edit-monthly_reference_hours");
            if (mrh) {
                mrh.value =
                    d.monthlyReferenceHours != null && d.monthlyReferenceHours !== ""
                        ? String(d.monthlyReferenceHours)
                        : "";
            }
            var fixedSel = document.getElementById("id_ch_edit-monthly_salary_is_fixed");
            if (fixedSel) {
                var fx = d.monthlySalaryIsFixed;
                if (fx === "true") {
                    fixedSel.value = "true";
                } else if (fx === "false") {
                    fixedSel.value = "false";
                } else {
                    fixedSel.value = "unknown";
                }
            }
            var sdt = document.getElementById("id_ch_edit-start_date");
            if (sdt) {
                sdt.value = d.startDate || "";
            }
            var edt = document.getElementById("id_ch_edit-end_date");
            if (edt) {
                edt.value = d.endDate || "";
            }
            if (dialog) {
                dialog.showModal();
            }
        },
    });
})();
