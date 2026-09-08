/* Structural GTIN validation only; the number does not identify a product name. */
export function normalizeGtin(value) {
  if (typeof value !== "string") throw new Error("invalid_barcode");
  const raw = value.trim();
  if (!raw) return "";
  if (![8, 12, 13, 14].includes(raw.length) || /[^0-9]/.test(raw) || /^0+$/.test(raw)) throw new Error("invalid_barcode");
  let sum = 0;
  for (let index = raw.length - 2, weight = 3; index >= 0; index--, weight = 4 - weight) sum += Number(raw[index]) * weight;
  if ((10 - sum % 10) % 10 !== Number(raw.at(-1))) throw new Error("invalid_barcode");
  return raw.padStart(14, "0");
}

export function detectedGtin(result) {
  const lengths = {ean_8: 8, upc_a: 12, ean_13: 13, itf: 14};
  if (!result || typeof result !== "object" || !Object.hasOwn(lengths, result.format) || typeof result.rawValue !== "string" || result.rawValue.length !== lengths[result.format]) throw new Error("invalid_barcode");
  return normalizeGtin(result.rawValue);
}
