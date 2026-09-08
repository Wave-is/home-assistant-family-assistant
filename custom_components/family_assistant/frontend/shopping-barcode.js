/* Opt-in, browser-local scanning. No images or product queries leave this module. */
import { detectedGtin } from "./gtin.js";

export const BARCODE_COPY = {
  en: {label:"Barcode (optional GTIN)",hint:"Enter 8, 12, 13 or 14 digits, or scan. The code does not supply a product name; review the name and quantity yourself. No external product lookup.",scan:"Scan barcode",stop:"Stop camera",starting:"Opening camera…",scanning:"Point at one EAN / UPC-A / ITF-14 code. Scanning stops after one minute.",unsupported:"Camera scanning is unavailable in this browser. Enter the digits manually or with a handheld scanner.",failed:"Could not read the camera. Check permission or enter the digits manually.",invalid:"Check the barcode length and check digit.",found:"Barcode filled in. Check the item details before saving.",timeout:"Scanning stopped. Try again or enter the digits manually.",multiple:"Several codes found. Point at just one product."},
  ru: {label:"Штрихкод (необязательный GTIN)",hint:"Введите 8, 12, 13 или 14 цифр либо отсканируйте. Код не определяет название товара: проверьте название и количество сами. Внешнего поиска товаров нет.",scan:"Сканировать штрихкод",stop:"Выключить камеру",starting:"Открываю камеру…",scanning:"Наведите на один код EAN / UPC-A / ITF-14. Сканирование остановится через минуту.",unsupported:"Этот браузер не поддерживает сканирование камерой. Введите цифры вручную или ручным сканером.",failed:"Не удалось прочитать камеру. Проверьте разрешение или введите цифры вручную.",invalid:"Проверьте длину штрихкода и контрольную цифру.",found:"Штрихкод заполнен. Проверьте данные покупки перед сохранением.",timeout:"Сканирование остановлено. Повторите или введите цифры вручную.",multiple:"Найдено несколько кодов. Наведите камеру на один товар."},
  uk: {label:"Штрихкод (необов’язковий GTIN)",hint:"Введіть 8, 12, 13 або 14 цифр чи відскануйте. Код не визначає назву товару: перевірте назву й кількість самі. Зовнішнього пошуку товарів немає.",scan:"Сканувати штрихкод",stop:"Вимкнути камеру",starting:"Відкриваю камеру…",scanning:"Наведіть на один код EAN / UPC-A / ITF-14. Сканування зупиниться через хвилину.",unsupported:"Цей браузер не підтримує сканування камерою. Введіть цифри вручну або ручним сканером.",failed:"Не вдалося прочитати камеру. Перевірте дозвіл або введіть цифри вручну.",invalid:"Перевірте довжину штрихкоду та контрольну цифру.",found:"Штрихкод заповнено. Перевірте дані покупки перед збереженням.",timeout:"Сканування зупинено. Повторіть або введіть цифри вручну.",multiple:"Знайдено кілька кодів. Наведіть камеру на один товар."}
};

export function barcodeCopy(card) {
  const language = card._config?.language || card._hass?.language?.split("-")[0] || "en";
  return BARCODE_COPY[language] || BARCODE_COPY.en;
}

function stopTracks(stream) {
  for (const track of stream?.getTracks?.() || []) track.stop();
}

export function stopBarcodeCamera(card) {
  const session = card._barcodeCamera;
  card._barcodeCamera = null;
  session?.stop();
}

export function renderBarcodeCamera(card, host, {isCurrent, onRead}) {
  // This widget may be rebuilt by a polling refresh: stop old capture first.
  // It never restarts the camera without a fresh button click.
  stopBarcodeCamera(card);
  const copy = barcodeCopy(card);
  const panel = document.createElement("div");
  panel.className = "shopping-barcode-camera";
  const hint = document.createElement("p");
  hint.className = "sub";
  hint.textContent = copy.hint;
  const status = document.createElement("p");
  status.className = "sub";
  status.setAttribute("role", "status");
  const video = document.createElement("video");
  video.muted = true;
  video.playsInline = true;
  video.hidden = true;
  video.style.width = "100%";
  video.style.maxHeight = "240px";
  const start = card.button(copy.scan, async () => {
    if (card._writing || !isCurrent() || card._barcodeCamera) return;
    if (globalThis.isSecureContext !== true || !globalThis.navigator?.mediaDevices?.getUserMedia || typeof globalThis.BarcodeDetector?.getSupportedFormats !== "function") {
      status.textContent = copy.unsupported;
      return;
    }
    let stream;
    let timer;
    let deadline;
    let stopped = false;
    const session = {stop() {
      if (stopped) return;
      stopped = true;
      clearTimeout(timer);
      clearTimeout(deadline);
      stopTracks(stream);
      video.srcObject = null;
      video.hidden = true;
      start.disabled = Boolean(card._writing);
      stop.hidden = true;
      document.removeEventListener("visibilitychange", visibility);
      globalThis.window?.removeEventListener("pagehide", finish);
    }};
    const current = () => !stopped && card._barcodeCamera === session && isCurrent() && panel.isConnected && !document.hidden;
    const finish = () => {
      if (card._barcodeCamera === session) card._barcodeCamera = null;
      session.stop();
    };
    const visibility = () => { if (document.hidden) finish(); };
    card._barcodeCamera = session;
    panel.closest("form")?.querySelector('[name="barcode"]')?.focus();
    start.disabled = true;
    stop.hidden = false;
    status.textContent = copy.starting;
    deadline = setTimeout(() => { if (current()) status.textContent = copy.timeout; finish(); }, 60000);
    document.addEventListener("visibilitychange", visibility);
    globalThis.window?.addEventListener("pagehide", finish);
    try {
      const formats = (await globalThis.BarcodeDetector.getSupportedFormats()).filter(format => ["ean_8", "upc_a", "ean_13", "itf"].includes(format));
      if (!current()) { finish(); return; }
      if (!formats.length) { status.textContent = copy.unsupported; finish(); return; }
      const detector = new globalThis.BarcodeDetector({formats});
      stream = await globalThis.navigator.mediaDevices.getUserMedia({audio:false, video:{facingMode:{ideal:"environment"},width:{ideal:1280},height:{ideal:720}}});
      // Permission may resolve after cancellation. Release even a late stream.
      if (!current()) { stopTracks(stream); stream = null; finish(); return; }
      video.srcObject = stream;
      video.hidden = false;
      await video.play();
      if (!current()) { finish(); return; }
      status.textContent = copy.scanning;
      const poll = async () => {
        if (!current()) { finish(); return; }
        try {
          if (video.readyState >= 2) {
            const results = await detector.detect(video);
            if (!current()) { finish(); return; }
            const codes = new Set();
            for (const result of results) {
              try { codes.add(detectedGtin(result)); } catch { /* Ignore non-GTIN shapes. */ }
            }
            if (codes.size === 1) {
              finish();
              status.textContent = copy.found;
              onRead([...codes][0]);
              return;
            }
            status.textContent = codes.size > 1 ? copy.multiple : copy.scanning;
          }
          timer = setTimeout(poll, 300);
        } catch {
          if (current()) status.textContent = copy.failed;
          finish();
        }
      };
      await poll();
    } catch {
      if (current()) status.textContent = copy.failed;
      finish();
    }
  });
  const stop = card.button(copy.stop, () => stopBarcodeCamera(card));
  stop.hidden = true;
  panel.append(hint, start, stop, video, status);
  host.append(panel);
}
