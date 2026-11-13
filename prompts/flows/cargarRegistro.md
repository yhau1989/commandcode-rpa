# Flujo: cargar un registro en CM Ajustes

Receta validada contra el sitio real. Seguila en este orden; cada paso asume que
la página anterior terminó de cargar.

## 0. Preparación

- `BASE_URL` = `https://cmas.cmajustadores.com`
- Login: `BASE_URL/login`, campos `#email` y `#password`, botón "Iniciar sesión".
  Si el login falla → abortar el run completo.
- Alta: `BASE_URL/cmas-cloud/add`.
- Ojo: el navegador headless se cae con muchas interacciones seguidas. Si la
  pestaña queda en `about:blank`, reabrir la URL y **revisar qué campos ya tienen
  valor** antes de seguir (nunca asumir que el formulario está vacío).

## 1. Receta por tipo de control

| Control | Cómo se opera |
| --- | --- |
| Select | click en `div.ant-select:has(#<id>) .ant-select-selector` → `keyboard type "<filtro>"` → `press Enter` |
| Fecha (`dd/mm/aaaa`) | `focus "#<id>"` → `keyboard type "dd/mm/aaaa"` → `press Escape` |
| Texto / número | `fill "#<id>" "<valor>"` |
| Radio | `click 'input[name="<grupo>"][value="<valor>"]'` |

Los selects están **virtualizados**: solo renderizan 10 opciones. Si el valor no
aparece, hay que filtrar por texto; nunca hacer scroll buscándolo.

Las fechas fallan si el panel del datepicker quedó abierto: antes de cada fecha,
`press Escape` y click en un `h5` para cerrar.

## 2. Mapeo columna de la planilla → campo del formulario

| Columna | id del campo | Tipo |
| --- | --- | --- |
| Compañía asegurada | `nombre_compania_asegurada` | select |
| Sucursal | `sucursal` | texto |
| Ramo (`14` → `AGRICOLA`) | `ramo` | select |
| Póliza | `poliza` | texto |
| Certificado | `certificado` | texto |
| Inicio vigencia | `inicio_vigencia` | fecha |
| Fin vigencia | `fin_vigencia` | fecha |
| Cédula | `cedula` | texto |
| Nombre asegurado | `nombre_asegurado` | texto |
| N° siniestro | `numero_siniestro` | texto |
| N° aviso | `numero_aviso` | texto |
| Fecha aviso/notificación | `fecha_aviso_notificacion` | fecha |
| Fecha siniestro | `fecha_siniestro` | fecha |
| Fecha asignación | `fecha_asignacion_siniestro` | fecha |
| Fecha siniestro campo | `fecha_siniestro_campo` | fecha |
| Cobertura | `cobertura` | texto |
| Provincia | `provincia` | select (cascada) |
| Cantón | `canton` | select (depende de provincia) |
| Parroquia | `parroquia` | select (depende de cantón) |
| Sitio de inversión | `sitio_inversion` | texto |
| Coordenada X / Y | `coordenada_x` / `coordenada_y` | texto |
| Hectáreas aseguradas / sembradas / área afectada | `hectareas_aseguradas` / `hectareas_sembradas` / `area_afectada` | número |
| Cultivo | `cultivo` | texto |
| Ciclo | `ciclo` | texto |
| Fecha real de siembra | `fecha_real_siembra` | fecha |
| Tipo de evento | `tipo_evento` | select |
| Causa | `causa` | texto |
| Tipo de pérdida (`parcial`/`total`) | `_r_e_` | radio |
| Observaciones | `observaciones` | textarea |
| Fecha inspección | `fecha_inspeccion` | fecha |
| Fecha envío informe | `fecha_envio_informe` | fecha |
| Coord. X / Y de inspección | `coordenada_x_inspeccion` / `coordenada_y_inspeccion` | texto |
| Inspector asignado | `inspector_asignado` | texto |
| ¿Entregó factura de inversión? (Sí/No) | `_r_h_` | radio |
| Conclusiones del ajustador | `conclusiones_ajustador` | textarea |
| ¿Prestó facilidades? (Sí/No) | `_r_i_` | radio |
| ¿Aplica negativa? (Sí/No) | `_r_j_` | radio |
| Tipo de negativa | `tipo_negativa` | texto |
| Causas cerrado sin pago | `causas_cerrado_sin_pago` | texto |
| Observaciones indemnización | `observaciones_indemnizacion` | textarea |
| Precio ajuste (qq) | `precio_ajuste_qq` | número |
| Valor asegurado | `cantidad_x_qq` | número |
| Rendimiento qq/ha | `rendimiento_qq_por_hectarea` | número |
| Superficie a cosechar (ha) | `superficie_a_cosechar_ha` | número |
| Tipo Deducible | `deducible` | número |
| % deducible | `porcentaje_deducible` | número |

### Campos que NO se escriben (los calcula el sistema)

`rendimiento_total_qq`, `monto_perdida_salvamento` (Valor Salvamento),
`monto_asegurado_salvamento` (Total costo de inversión / valor de perdida),
`monto_deducible`, `monto_indemnizar`. Están deshabilitados.

## 3. Campo CMAS

1. Abrir el select `#cmas`.
2. La lista trae los códigos libres ordenados por id ascendente.
3. Elegir **el primero**. Es un código por caso: al guardar pasa a `used`.
4. Si el select dice "No data" → no hay códigos libres. Abortar el run con
   `"detalle": "sin códigos CMAS disponibles"`.

## 4. Verificación antes de guardar

Comprobar que estos valores coinciden con la fila de la planilla:

- `rendimiento_total_qq` ≈ `Rendimiento total (qq)`
- `monto_perdida_salvamento` ≈ `Valor Salvamento`
- `monto_asegurado_salvamento` ≈ `Total costo de inversión / valor de perdida`
- `monto_indemnizar` ≈ `Monto a indemnizar`

Si `monto_asegurado_salvamento` es negativo, el dato de origen viola
`pérdida = asegurado − salvamento`: no guardar, marcar `ERROR`.

Diferencias de ±0,02 son redondeo del sistema y se aceptan.

## 5. Guardar

- Click en "Guardar siniestro".
- Éxito: el formulario se limpia y el CMAS elegido desaparece de la lista.
- Si hay errores de validación, leer los `ant-form-item-explain-error` y marcar
  `ERROR` con el texto exacto.
- El link del registro: el sistema no expone una URL por siniestro en esta
  pantalla. Usar `BASE_URL/cmas-cloud/add` como referencia y el `N° siniestro`
  como identificador en la columna `link` mientras no exista una vista de detalle.
  `TODO(link)`: confirmar con el equipo si hay URL de detalle.
