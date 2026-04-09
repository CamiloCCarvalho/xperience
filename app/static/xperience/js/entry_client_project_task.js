/**
 * Filtros em cascata: Cliente → Projeto → Tarefa (apenas opções permitidas ao usuário).
 * Depende de data-client-id nas options de projeto e data-project-id / data-client-id nas de tarefa.
 */
(function () {
    const clientEl = document.getElementById("entry-client");
    const projectEl = document.getElementById("entry-project");
    const taskEl = document.getElementById("entry-task");

    if (!clientEl && !projectEl && !taskEl) {
        return;
    }

    function eachValueOption(select, fn) {
        if (!select) {
            return;
        }
        Array.from(select.options).forEach(function (opt) {
            if (opt.value === "") {
                return;
            }
            fn(opt);
        });
    }

    function applyProjectFilter() {
        if (!projectEl) {
            applyTaskFilter();
            return;
        }
        var cid = clientEl && clientEl.value ? clientEl.value : "";
        eachValueOption(projectEl, function (opt) {
            var oc = opt.getAttribute("data-client-id");
            opt.hidden = Boolean(cid && oc !== cid);
        });
        var sel = projectEl.selectedOptions[0];
        if (projectEl.value && sel && sel.hidden) {
            projectEl.value = "";
        }
        applyTaskFilter();
    }

    function applyTaskFilter() {
        if (!taskEl) {
            return;
        }
        var pid = projectEl && projectEl.value ? projectEl.value : "";
        var cid = clientEl && clientEl.value ? clientEl.value : "";
        eachValueOption(taskEl, function (opt) {
            var op = opt.getAttribute("data-project-id");
            var oc = opt.getAttribute("data-client-id");
            var show = true;
            if (pid) {
                show = op === pid;
            } else if (cid) {
                show = oc === cid;
            }
            opt.hidden = !show;
        });
        var tsel = taskEl.selectedOptions[0];
        if (taskEl.value && tsel && tsel.hidden) {
            taskEl.value = "";
        }
    }

    if (clientEl) {
        clientEl.addEventListener("change", applyProjectFilter);
    }
    if (projectEl) {
        projectEl.addEventListener("change", applyTaskFilter);
    }
    applyProjectFilter();
    applyTaskFilter();
})();
