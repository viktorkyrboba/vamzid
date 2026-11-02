/**
 * Сервер-посредник заказов «Все Для Дома» → Telegram.
 * Платформа: Cloudflare Workers (бесплатного тарифа достаточно).
 *
 * Зачем он нужен: токен Telegram-бота нельзя класть в код сайта — любой посетитель
 * увидит его и сможет рассылать сообщения от имени бота. Токен хранится только здесь,
 * в зашифрованных переменных Cloudflare.
 *
 * Переменные (Settings → Variables and Secrets):
 *   BOT_TOKEN       — секрет: токен бота от @BotFather
 *   CHAT_ID         — секрет: ваш chat id (куда присылать заказы)
 *   ALLOWED_ORIGIN  — адреса сайта без слэша в конце, через запятую, например
 *                     https://vamzid.pages.dev,https://viktorkyrboba.github.io
 * Необязательно: привязка Rate Limiting с именем RL (ограничение частоты по IP).
 *   REVIEWS         — привязка KV (Bindings → KV namespace): хранилище оценок и отзывов на сайте.
 *                     Без неё заказы работают, а отзывы просто отправляются в Telegram.
 *
 * Персональные данные заказа не сохраняются и не пишутся в логи: Worker только
 * проверяет их и пересылает одним сообщением в Telegram.
 */

const PAY = { cash: "Наличными при получении", card: "Картой при получении" };
const GET = { delivery: "Доставка", pickup: "Самовывоз из магазина" };
const MAX_BODY = 12000;

function json(data, status, cors) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store", ...cors },
  });
}

const str = (v, max) => (typeof v === "string" ? v.trim().replace(/\s+/g, " ").slice(0, max) : "");
// убираем управляющие символы, чтобы нельзя было «нарисовать» в сообщении поддельные строки
const clean = (v, max) => str(v, max).replace(/[\u0000-\u001f\u007f\u202a-\u202e\u2066-\u2069]/g, "");


// ---- отзывы и оценки (хранятся в KV, привязка REVIEWS) ----
const sha = async (s) => [...new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s)))].slice(0, 12).map((x) => x.toString(16).padStart(2, "0")).join("");
const keyOf = (v) => clean(v, 120);
const pub = (r) => ({ s: r.s, a: r.a, t: r.t, d: r.d });

async function getReviews(env, name) {
  try { const l = JSON.parse((await env.REVIEWS.get("r:" + name)) || "[]"); return Array.isArray(l) ? l : []; } catch { return []; }
}

function validate(o) {
  if (!o || typeof o !== "object") return "bad request";
  const first = clean(o.first, 60), last = clean(o.last, 60), phone = clean(o.phone, 20);
  const get = o.get, pay = o.pay;
  const addr = get === "delivery" ? clean(o.addr, 200) : "";
  const note = clean(o.note, 500);
  if (first.length < 2 || last.length < 2) return "name";
  if (!/^\+?[0-9][0-9 ()-]{5,18}$/.test(phone) || phone.replace(/\D/g, "").length < 6) return "phone";
  if (!Object.hasOwn(GET, get) || !Object.hasOwn(PAY, pay)) return "options";
  if (get === "delivery" && addr.length < 5) return "address";
  if (!Array.isArray(o.items) || o.items.length < 1 || o.items.length > 50) return "items";
  const items = [];
  for (const i of o.items) {
    const n = clean(i && i.n, 120), q = i && i.q;
    const p = i && typeof i.p === "number" && isFinite(i.p) && i.p >= 0 && i.p < 1e7 ? Math.round(i.p * 100) / 100 : null;
    if (!n || !Number.isInteger(q) || q < 1 || q > 99) return "items";
    items.push({ n, q, p });
  }
  return { first, last, phone, get, pay, addr, note, items };
}

function message(o, id) {
  const money = (v) => v.toLocaleString("ru-RU", { maximumFractionDigits: 2 }) + " лей";
  let sum = 0, unknown = false;
  const lines = o.items.map((i, k) => {
    if (i.p == null) unknown = true; else sum += i.p * i.q;
    return `${k + 1}. ${i.n} — ${i.q} шт.` + (i.p != null ? ` × ${money(i.p)}` : " (цена не указана)");
  });
  // сумма пересчитана на сервере; цены пришли из браузера — сверяйте с прайсом при подтверждении
  const total = sum ? money(Math.round(sum * 100) / 100) + (unknown ? " + товары без цены" : "") : "уточнить";
  return [
    `🛒 Новый заказ ${id}`,
    "",
    ...lines,
    "",
    `Итого (по ценам сайта): ${total}`,
    `Получение: ${GET[o.get]}`,
    ...(o.addr ? [`Адрес: ${o.addr}`] : []),
    `Оплата: ${PAY[o.pay]}`,
    "",
    `Имя: ${o.first} ${o.last}`,
    `Телефон: ${o.phone}`,
    ...(o.note ? [`Комментарий: ${o.note}`] : []),
  ].join("\n");
}

export default {
  async fetch(req, env) {
    const list = (env.ALLOWED_ORIGIN || "").split(",").map((s) => s.trim()).filter(Boolean);
    const origin = req.headers.get("Origin") || "";
    const allowed = list.includes(origin) ? origin : "";
    const cors = {
      "Access-Control-Allow-Origin": allowed,
      "Access-Control-Allow-Methods": "GET, POST",
      "Access-Control-Allow-Headers": "Content-Type",
      "Access-Control-Max-Age": "86400",
      Vary: "Origin",
    };
    if (!allowed) return json({ ok: false, error: "forbidden" }, 403, {});
    if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });
    const url = new URL(req.url);
    if (req.method === "GET" && url.pathname === "/reviews") {
      const name = keyOf(url.searchParams.get("p"));
      if (!env.REVIEWS || !name) return json({ ok: false, error: "disabled" }, 503, cors);
      return json({ ok: true, reviews: (await getReviews(env, name)).map(pub) }, 200, cors);
    }
    if (req.method !== "POST") return json({ ok: false, error: "method" }, 405, cors);
    if ((req.headers.get("Content-Type") || "").split(";")[0].trim() !== "application/json")
      return json({ ok: false, error: "type" }, 415, cors);

    if (env.RL) {
      const ip = req.headers.get("CF-Connecting-IP") || "unknown";
      const { success } = await env.RL.limit({ key: ip });
      if (!success) return json({ ok: false, error: "too many requests" }, 429, cors);
    }

    const raw = await req.text();
    if (raw.length > MAX_BODY) return json({ ok: false, error: "too large" }, 413, cors);
    let body;
    try { body = JSON.parse(raw); } catch { return json({ ok: false, error: "json" }, 400, cors); }

    // ловушка для ботов: скрытое поле заполняют только роботы — делаем вид, что всё хорошо
    if (typeof body.website === "string" && body.website !== "") return json({ ok: true, id: "" }, 200, cors);

    if (url.pathname === "/review") {
      const name = keyOf(body.p), s = body.s, a = clean(body.a, 40) || "Покупатель", t = clean(body.t, 500);
      if (!name || !Number.isInteger(s) || s < 1 || s > 5) return json({ ok: false, error: "review" }, 422, cors);
      if (!env.REVIEWS) return json({ ok: false, error: "disabled" }, 503, cors);
      const ip = req.headers.get("CF-Connecting-IP") || "unknown", day = new Date().toISOString().slice(0, 10);
      const dk = "d:" + (await sha(ip + "|" + name + "|" + day)), ik = "i:" + (await sha(ip + "|" + day));
      if (await env.REVIEWS.get(dk)) return json({ ok: false, error: "duplicate" }, 429, cors);
      const cnt = +((await env.REVIEWS.get(ik)) || 0);
      if (cnt >= 5) return json({ ok: false, error: "too many requests" }, 429, cors);
      await env.REVIEWS.put(dk, "1", { expirationTtl: 86400 });
      await env.REVIEWS.put(ik, String(cnt + 1), { expirationTtl: 86400 });
      const r = { s, a, t, d: day };
      const list = await getReviews(env, name);
      list.unshift(r);
      await env.REVIEWS.put("r:" + name, JSON.stringify(list.slice(0, 200)));
      // уведомление владельцу (не мешает публикации)
      try {
        await fetch(`https://api.telegram.org/bot${env.BOT_TOKEN}/sendMessage`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ chat_id: env.CHAT_ID, text: `⭐ Новый отзыв: ${name}\nОценка: ${s} из 5\nИмя: ${a}${t ? "\nОтзыв: " + t : ""}`, disable_web_page_preview: true }),
        });
      } catch {}
      return json({ ok: true, review: pub(r) }, 200, cors);
    }

    const o = validate(body);
    if (typeof o === "string") return json({ ok: false, error: o }, 422, cors);

    const id = "№" + crypto.randomUUID().slice(0, 6).toUpperCase();
    const tg = await fetch(`https://api.telegram.org/bot${env.BOT_TOKEN}/sendMessage`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      // без parse_mode: текст клиента не может превратиться в разметку или ссылки
      body: JSON.stringify({ chat_id: env.CHAT_ID, text: message(o, id), disable_web_page_preview: true }),
    });
    if (!tg.ok) return json({ ok: false, error: "telegram" }, 502, cors);
    return json({ ok: true, id }, 200, cors);
  },
};
