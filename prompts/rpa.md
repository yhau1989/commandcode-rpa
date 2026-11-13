# Run RPA: cargar un caso pendiente

## Objetivo

Procesar **exactamente una** fila pendiente de la planilla y escribir el
resultado de vuelta. Si quedan pendientes, las toma la próxima corrida del cron.
Seguí `AGENTS.md` al pie de la letra: es el contrato del run.

## Flujo, en este orden

1. **Validar config.** Sin `SHEET_ID`, `BASE_URL`, `RPA_USER` o `RPA_PASS` no
   arranques: devolvé el JSON final con `detalle` nombrando las variables que
   faltan (nunca sus valores) y salí con error.
2. **Lock.** `node scripts/sheet.mjs lock`. Si sale con error de lock activo,
   abortá el run sin tocar nada.
3. **Leer la fila.** `node scripts/sheet.mjs next --limit 1`. El JSON que
   devuelve es la única fuente del caso: `casos[0].fields` trae las 57 columnas
   de carga. Si `casos` está vacío, liberá el lock y terminá con `procesados: 0`.
4. **Login.** Abrí `BASE_URL` con `agent-browser` y logueate con `RPA_USER` /
   `RPA_PASS`. Si el login falla: liberá el lock y abortá el run completo.
5. **Completar el caso.** Seguí `prompts/flows/cargarRegistro.md` al pie de la
   letra: mapeo columna → campo, receta por tipo de control, elección del CMAS y
   verificación de los montos calculados. Un dato faltante no se inventa:
   `SALTEADO`.
6. **Registrar el resultado, inmediato:**
   - Éxito: `node scripts/sheet.mjs commit --id <N° siniestro> --status OK --link <url>`
   - Falla: `node scripts/sheet.mjs commit --id <N° siniestro> --status ERROR --error "<motivo>"`
   - Dato inválido: `--status SALTEADO --error "<qué falta>"`
7. **Cierre.** `node scripts/sheet.mjs unlock` siempre, incluso si fallaste.
   Publicá el resumen final.

## Evidencia

Ante cualquier falla de navegación, guardá antes de continuar:

- `artifacts/<N° siniestro>-fail.png` (screenshot)
- `artifacts/<N° siniestro>-fail.txt` (snapshot de accesibilidad)

Sin evidencia el diagnóstico es adivinanza.

## Si el navegador se cae

La pestaña puede quedar en `about:blank`. Reabrí `BASE_URL/cmas-cloud/add`,
revisá qué campos ya tienen valor y continuá desde ahí. No reinicies el caso de
cero sin mirar: podés duplicar un alta ya guardada.

## Salida

Un único objeto JSON, sin texto alrededor, con el formato de `AGENTS.md`.
