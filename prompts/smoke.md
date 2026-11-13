# Run de humo (fase 1)

Este run no toca ninguna planilla ni ningún sistema real. Sirve para verificar
que la cadena completa funciona en GitHub Actions: API key de Command Code,
agente headless, y `agent-browser` levantando Chrome.

## Qué hacer

1. Verificá que `agent-browser` esté disponible (`agent-browser --version`).
2. Abrí `https://example.com`.
3. Guardá un screenshot en `artifacts/smoke.png` (creá el directorio si no existe).
4. Tomá un snapshot de accesibilidad y dejalo en `artifacts/smoke.txt`.
5. Cerrá el navegador.

## Qué no hacer

- No instales nada (si `agent-browser` falta, reportalo y terminá).
- No leas ni escribas la planilla. No uses `scripts/sheet.mjs`.
- No toques archivos fuera de `artifacts/`.
- No adivines: si algo falla, transcribí el error real.

## Salida

Un único objeto JSON, sin texto alrededor:

```json
{"navegador": "ok", "titulo": "Example Domain", "detalle": ""}
```

Si algo falla, `"navegador": "error"` y en `detalle` el motivo concreto.
