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
 *   ALLOWED_ORIGIN  — адрес сайта без слэша в конце, например https://viktorkyrboba.github.io
 * Необязательно: привязка Rate Limiting с именем RL (ограничение частоты по IP).
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
    const allowed = env.ALLOWED_ORIGIN || "";
    const origin = req.headers.get("Origin") || "";
    const cors = {
      "Access-Control-Allow-Origin": allowed,
      "Access-Control-Allow-Methods": "POST",
      "Access-Control-Allow-Headers": "Content-Type",
      "Access-Control-Max-Age": "86400",
      Vary: "Origin",
    };
    if (!allowed || origin !== allowed) return json({ ok: false, error: "forbidden" }, 403, {});
    if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });
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
