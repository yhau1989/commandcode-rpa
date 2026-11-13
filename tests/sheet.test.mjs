import test from "node:test";
import assert from "node:assert/strict";

import {
  columnLetter,
  findControlColumns,
  isPending,
  mapRow,
  rowId,
} from "../scripts/sheet.mjs";

const HEADER = ["Compañía asegurada", "N° siniestro", "estado", "link", "intentos", "actualizado_en", "error"];

test("columnLetter mapea índices a letras de Excel", () => {
  assert.equal(columnLetter(0), "A");
  assert.equal(columnLetter(25), "Z");
  assert.equal(columnLetter(26), "AA");
  assert.equal(columnLetter(56), "BE");
  assert.equal(columnLetter(57), "BF");
});

test("findControlColumns las encuentra sin importar mayúsculas", () => {
  const controls = findControlColumns(["a", "Estado", "LINK", "intentos", "actualizado_en", "error"]);
  assert.deepEqual(controls, {
    estado: 1,
    link: 2,
    intentos: 3,
    actualizado_en: 4,
    error: 5,
  });
});

test("findControlColumns devuelve null si falta alguna", () => {
  assert.equal(findControlColumns(["estado", "link", "intentos"]), null);
});

test("rowId toma el N° siniestro y descarta vacíos", () => {
  assert.equal(rowId(HEADER, ["x", " 20260000000943 ", ""]), "20260000000943");
  assert.equal(rowId(HEADER, ["x", "", ""]), null);
});

test("isPending respeta estados y reintentos", () => {
  assert.equal(isPending("", 0), true);
  assert.equal(isPending("PENDIENTE", 0), true);
  assert.equal(isPending("ERROR", 2), true);
  assert.equal(isPending("ERROR", 3), false);
  assert.equal(isPending("OK", 0), false);
  assert.equal(isPending("SALTEADO", 0), false);
});

test("isPending reintenta un EN_PROCESO abandonado pasado el TTL", () => {
  const old = new Date(Date.now() - 20 * 60000).toISOString();
  const fresh = new Date(Date.now() - 1 * 60000).toISOString();
  assert.equal(isPending("EN_PROCESO", 0, old), true);
  assert.equal(isPending("EN_PROCESO", 0, fresh), false);
});

test("mapRow arma el caso con campos y control", () => {
  const controls = findControlColumns(HEADER);
  const row = ["Seguros del Pichincha", "20260000000943", "", "", "", "", ""];
  const mapped = mapRow(HEADER, row, controls);

  assert.equal(mapped.id, "20260000000943");
  assert.equal(mapped.intentos, 0);
  assert.equal(mapped.fields["Compañía asegurada"], "Seguros del Pichincha");
  assert.equal(mapped.fields["N° siniestro"], "20260000000943");
});
