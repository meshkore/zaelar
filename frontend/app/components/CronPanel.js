// CronPanel — manage zaelar's proactive tasks (loop orquestador PROPIO, nucleo/scheduler.py). Toggled by the ⏰
// button in the TopBar (store.cronOpen). Lists scheduled jobs with delete, and a small form to add one by hand.
// The brain also creates these by voice ("recuérdame…", "avísame cuando…") via the [[cron.create]] tag — this
// panel is just the manual surface over the SAME store (tasks persisted in memory.journal).
import { h, raw } from "../core/dom.js?v=2";
import { createEffect } from "../core/reactive.js?v=2";
import * as store from "../core/store.js?v=2";
import * as api from "../services/api.js?v=2";
import { CLOCK_ICON, REFRESH_ICON, CLOSE_ICON, TRASH_ICON } from "../lib/icons.js?v=1";

async function refresh() { const r = await api.cronList(); store.setCronJobs(r.jobs || []); }

export function CronPanel() {
  let schedEl, promptEl, nameEl;

  createEffect(() => { if (store.cronOpen()) refresh(); });   // load whenever it opens

  const act = async (action, ref) => { await api.cronAction(action, ref); await refresh(); };
  const add = async () => {
    const schedule = (schedEl.value || "").trim(); if (!schedule) return;
    await api.cronCreate({ schedule, prompt: (promptEl.value || "").trim(), name: (nameEl.value || "").trim() });
    schedEl.value = promptEl.value = nameEl.value = "";
    await refresh();
  };

  const row = (j) => h("div", { class: "cron-row" },
    h("div", { class: "cron-main" },
      h("div", { class: "cron-name" }, j.name || j.id),
      h("div", { class: "cron-meta" }, `${j.schedule || "?"} · ${j.paused ? "pausado" : (j.state || "activo")}` +
        (j.last_status ? ` · última: ${j.last_status}` : "")),
      j.prompt ? h("div", { class: "cron-prompt" }, j.prompt) : null,
    ),
    h("div", { class: "cron-btns" },
      h("button", { class: "cron-b hb-icbtn danger", title: "Eliminar", onClick: () => act("remove", j.id) }, raw(TRASH_ICON)),
    ),
  );

  return h("div", { class: () => "cronpanel" + (store.cronOpen() ? " open" : "") },
    h("div", { class: "cw-head" },
      h("span", { class: "cw-title" }, raw(CLOCK_ICON), "Tareas programadas"),
      h("button", { class: "cw-x hb-icbtn", title: "Refrescar", onClick: refresh }, raw(REFRESH_ICON)),
      h("button", { class: "cw-x hb-icbtn", title: "Cerrar", onClick: () => store.setCronOpen(false) }, raw(CLOSE_ICON)),
    ),
    h("div", { class: "cron-list" },
      () => (store.cronJobs().length
        ? store.cronJobs().map(row)
        : h("div", { class: "cron-empty" }, "No hay tareas. Dile a zaelar «recuérdame…» o «avísame cuando…», o crea una abajo.")),
    ),
    h("div", { class: "cron-add" },
      h("input", { ref: el => (schedEl = el), class: "cron-in", placeholder: "cuándo (30m · every 2h · 0 9 * * *)" }),
      h("input", { ref: el => (nameEl = el), class: "cron-in", placeholder: "nombre (opcional)" }),
      h("textarea", { ref: el => (promptEl = el), class: "cron-in", rows: 2,
        placeholder: "qué hacer/comprobar y qué avisarme (para condiciones, que responda [SILENT] si no toca)" }),
      h("button", { class: "cron-create", onClick: add }, "Programar"),
    ),
  );
}
