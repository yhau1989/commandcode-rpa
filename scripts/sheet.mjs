#!/usr/bin/env node
/**
 * Única vía de lectura/escritura de la planilla.
 *
 * La hoja es la de carga (57 columnas A..BE) con 5 columnas de control
 * agregadas al final: estado, link, intentos, actualizado_en, error.
 * El id de cada fila es la columna "N° siniestro".
 *
 * Comandos:
 *   node scripts/sheet.mjs init
 *   node scripts/sheet.mjs next [--limit 1] [--dry-run]
 *   node scripts/sheet.mjs commit --id X --status OK [--link URL] [--error MSG]
 *   node scripts/sheet.mjs lock
 *   node scripts/sheet.mjs unlock
 *   node scripts/sheet.mjs status
 *
 * Variables de entorno:
 *   GOOGLE_APPLICATION_CREDENTIALS  ruta al JSON de la service account
 *   SHEET_ID                        id de la planilla
 *   SHEET_TAB                       nombre de la hoja (default: Casos)
 */

import { GoogleAuth } from "google-auth-library";
import { pathToFileURL } from "node:url";
import { resolve } from "node:path";

const API = "https://sheets.googleapis.com/v4/spreadsheets";
const CONTROL_COLUMNS = [
  "estado",
  "link",
  "intentos",
  "actualizado_en",
  "error",
];
const ID_COLUMN = "N° siniestro";
const LOCK_SHEET = "_lock";
const LOCK_TTL_MINUTES = 15;
const MAX_ATTEMPTS = 3;

// --- Helpers puros (testeables) ---------------------------------------------

export function columnLetter(index) {
  let n = index + 1;
  let out = "";
  while (n > 0) {
    const rem = (n - 1) % 26;
    out = String.fromCharCode(65 + rem) + out;
    n = Math.floor((n - 1) / 26);
  }
  return out;
}

export function findControlColumns(header) {
  const positions = {};
  for (const name of CONTROL_COLUMNS) {
    const index = header.findIndex(
      (cell) => String(cell ?? "").trim().toLowerCase() === name,
    );
    if (index === -1) return null;
    positions[name] = index;
  }
  return positions;
}

export function rowId(header, row) {
  const index = header.findIndex(
    (cell) => String(cell ?? "").trim() === ID_COLUMN,
  );
  if (index === -1) return null;
  const value = String(row[index] ?? "").trim();
  return value === "" ? null : value;
}

export function isPending(estado, intentos, actualizadoEn = "") {
  const state = String(estado ?? "").trim().toUpperCase();
  if (state === "" || state === "PENDIENTE") return true;
  if (state === "ERROR") return Number(intentos ?? 0) < MAX_ATTEMPTS;
  if (state === "EN_PROCESO") {
    // Un run que murió a mitad deja la fila así: se reintenta pasado el TTL.
    const stamp = new Date(String(actualizadoEn ?? "")).getTime();
    if (!Number.isFinite(stamp)) return true;
    return Date.now() - stamp > LOCK_TTL_MINUTES * 60000;
  }
  return false;
}

export function mapRow(header, row, controls) {
  const fields = {};
  header.forEach((name, index) => {
    const key = String(name ?? "").trim();
    if (key) fields[key] = row[index] ?? null;
  });
  return {
    id: rowId(header, row),
    estado: String(row[controls["estado"]] ?? "").trim(),
    link: row[controls["link"]] ?? "",
    intentos: Number(row[controls["intentos"]] ?? 0) || 0,
    error: row[controls["error"]] ?? "",
    actualizado_en: row[controls["actualizado_en"]] ?? "",
    fields,
  };
}

// --- Acceso a la API ---------------------------------------------------------

function requiredEnv(name) {
  const value = process.env[name];
  if (!value) throw new Error(`Falta la variable de entorno ${name}`);
  return value;
}

async function authToken() {
  requiredEnv("GOOGLE_APPLICATION_CREDENTIALS");
  requiredEnv("SHEET_ID");
  const auth = new GoogleAuth({
    scopes: ["https://www.googleapis.com/auth/spreadsheets"],
  });
  const client = await auth.getClient();
  const token = await client.getAccessToken();
  if (!token.token) throw new Error("No se pudo obtener el token de Google");
  return token.token;
}

async function api(path, options = {}) {
  const token = options.token ?? (await authToken());
  const response = await fetch(`${API}/${process.env.SHEET_ID}${path}`, {
    ...options,
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      ...(options.headers ?? {}),
    },
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Sheets API ${response.status}: ${body.slice(0, 400)}`);
  }
  return response.json();
}

function tab() {
  const name = process.env.SHEET_TAB || "Casos";
  return `'${name.replace(/'/g, "''")}'`;
}

async function readAll(token) {
  const data = await api(
    `/values/${encodeURIComponent(`${tab()}!A1:BZ2000`)}?majorDimension=ROWS`,
    { token },
  );
  const values = data.values ?? [];
  if (values.length === 0) throw new Error("La hoja está vacía");
  const header = values[0];
  const controls = findControlColumns(header);
  if (!controls) {
    throw new Error(
      `Faltan columnas de control (${CONTROL_COLUMNS.join(", ")}). Corré: node scripts/sheet.mjs init`,
    );
  }
  return { header, controls, rows: values.slice(1) };
}

async function writeRow(token, rowNumber, updates) {
  const data = Object.entries(updates).map(([index, value]) => ({
    range: `${tab()}!${columnLetter(index)}${rowNumber}`,
    values: [[value]],
  }));
  if (data.length === 0) return;
  await api("/values:batchUpdate", {
    token,
    method: "POST",
    body: JSON.stringify({ valueInputOption: "RAW", data }),
  });
}

// --- Comandos ---------------------------------------------------------------

async function cmdInit(token) {
  const data = await api(
    `/values/${encodeURIComponent(`${tab()}!A1:BZ1`)}?majorDimension=ROWS`,
    { token },
  );
  const header = (data.values ?? [[]])[0] ?? [];
  if (header.length === 0) throw new Error("La hoja no tiene encabezados");

  const existing = findControlColumns(header);
  if (existing) {
    console.log("Las columnas de control ya existen.");
    return;
  }
  const start = header.length;
  await writeRow(
    token,
    1,
    Object.fromEntries(
      CONTROL_COLUMNS.map((name, offset) => [start + offset, name]),
    ),
  );
  console.log(
    `Columnas de control creadas en ${columnLetter(start)}1:${columnLetter(start + CONTROL_COLUMNS.length - 1)}1`,
  );
}

async function cmdNext(token, { limit, dryRun }) {
  const { header, controls, rows } = await readAll(token);
  const pending = [];

  rows.forEach((row, index) => {
    const mapped = mapRow(header, row, controls);
    if (!mapped.id) return;
    if (!isPending(mapped.estado, mapped.intentos, mapped.actualizado_en)) return;
    pending.push({ rowNumber: index + 2, ...mapped });
  });

  const selected = pending.slice(0, limit);
  if (!dryRun && selected.length > 0) {
    const stamp = new Date().toISOString();
    for (const item of selected) {
      await writeRow(token, item.rowNumber, {
        [controls["estado"]]: "EN_PROCESO",
        [controls["actualizado_en"]]: stamp,
      });
    }
  }

  console.log(
    JSON.stringify(
      {
        pendientes: pending.length,
        seleccionados: selected.length,
        dry_run: Boolean(dryRun),
        casos: selected,
      },
      null,
      2,
    ),
  );
}

async function cmdCommit(token, { id, status, link, error }) {
  const { header, controls, rows } = await readAll(token);
  const index = rows.findIndex((row) => rowId(header, row) === id);
  if (index === -1) throw new Error(`No existe la fila con id ${id}`);

  const row = rows[index];
  const rowNumber = index + 2;
  const previousAttempts = Number(row[controls["intentos"]] ?? 0) || 0;
  const attempts = status === "ERROR" ? previousAttempts + 1 : previousAttempts;

  await writeRow(token, rowNumber, {
    [controls["estado"]]: status,
    [controls["link"]]: status === "OK" ? (link ?? "") : (row[controls["link"]] ?? ""),
    [controls["intentos"]]: attempts,
    [controls["actualizado_en"]]: new Date().toISOString(),
    [controls["error"]]: status === "OK" ? "" : (error ?? ""),
  });

  console.log(
    JSON.stringify(
      { id, rowNumber, estado: status, intentos: attempts },
      null,
      2,
    ),
  );
}

async function ensureLockSheet(token) {
  const meta = await api("", { token });
  const exists = (meta.sheets ?? []).some(
    (sheet) => sheet.properties?.title === LOCK_SHEET,
  );
  if (exists) return;
  await api(":batchUpdate", {
    token,
    method: "POST",
    body: JSON.stringify({
      requests: [{ addSheet: { properties: { title: LOCK_SHEET } } }],
    }),
  });
}

async function readLock(token) {
  const data = await api(
    `/values/${encodeURIComponent(`'${LOCK_SHEET}'!A1`)}?majorDimension=ROWS`,
    { token },
  );
  return String((data.values ?? [])[0]?.[0] ?? "").trim();
}

async function cmdLock(token) {
  await ensureLockSheet(token);
  const current = await readLock(token);
  if (current) {
    const ageMinutes = (Date.now() - new Date(current).getTime()) / 60000;
    if (Number.isFinite(ageMinutes) && ageMinutes < LOCK_TTL_MINUTES) {
      console.error(
        `Lock activo desde ${current} (${Math.round(ageMinutes)} min). Otro run está trabajando.`,
      );
      process.exit(3);
    }
    console.error(`Lock vencido (${Math.round(ageMinutes)} min): se toma igual.`);
  }
  const stamp = new Date().toISOString();
  await api(
    `/values/${encodeURIComponent(`'${LOCK_SHEET}'!A1`)}?valueInputOption=RAW`,
    { token, method: "PUT", body: JSON.stringify({ values: [[stamp]] }) },
  );
  console.log(stamp);
}

async function cmdUnlock(token) {
  await ensureLockSheet(token);
  await api(`/values/${encodeURIComponent(`'${LOCK_SHEET}'!A1:Z10`)}:clear`, {
    token,
    method: "POST",
    body: "{}",
  });
  console.log("lock liberado");
}

async function cmdStatus(token) {
  const { header, controls, rows } = await readAll(token);
  const counts = {};
  for (const row of rows) {
    const mapped = mapRow(header, row, controls);
    if (!mapped.id) continue;
    const state = mapped.estado || "PENDIENTE";
    counts[state] = (counts[state] ?? 0) + 1;
  }
  console.log(
    JSON.stringify(
      {
        hoja: process.env.SHEET_TAB || "Casos",
        columnas: header.length,
        filas: rows.length,
        estados: counts,
        lock: await readLock(token).catch(() => ""),
      },
      null,
      2,
    ),
  );
}

// --- CLI --------------------------------------------------------------------

function parseArgs(argv) {
  const args = { _: [] };
  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i];
    if (token.startsWith("--")) {
      const name = token.slice(2);
      const next = argv[i + 1];
      if (next === undefined || next.startsWith("--")) {
        args[name] = true;
      } else {
        args[name] = next;
        i += 1;
      }
    } else {
      args._.push(token);
    }
  }
  return args;
}

function usage() {
  console.error(
    [
      "Uso: node scripts/sheet.mjs <comando> [opciones]",
      "",
      "  init                                   crea las columnas de control",
      "  next [--limit N] [--dry-run]           devuelve las filas pendientes",
      "  commit --id X --status OK|ERROR|SALTEADO [--link URL] [--error MSG]",
      "  lock | unlock                          bloqueo de corrida (15 min)",
      "  status                                 conteo por estado",
    ].join("\n"),
  );
  process.exit(1);
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const command = args._[0];
  if (!command) usage();

  try {
    const token = await authToken();
    switch (command) {
      case "init":
        await cmdInit(token);
        break;
      case "next":
        await cmdNext(token, {
          limit: Number(args.limit ?? 1),
          dryRun: Boolean(args["dry-run"]),
        });
        break;
      case "commit":
        if (!args.id || !args.status) usage();
        await cmdCommit(token, {
          id: String(args.id),
          status: String(args.status).toUpperCase(),
          link: args.link,
          error: args.error,
        });
        break;
      case "lock":
        await cmdLock(token);
        break;
      case "unlock":
        await cmdUnlock(token);
        break;
      case "status":
        await cmdStatus(token);
        break;
      default:
        usage();
    }
  } catch (error) {
    console.error(`✗ ${error.message}`);
    process.exit(2);
  }
}

const isMain =
  process.argv[1] !== undefined &&
  import.meta.url === pathToFileURL(resolve(process.argv[1])).href;
if (isMain) main();
