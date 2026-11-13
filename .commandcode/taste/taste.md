# Taste

## Security / Secrets
- Prefiere que todas las credenciales y también la configuración no sensible (API keys, credenciales del sitio, acceso a Google Drive, ids de planilla, modelo) vivan en GitHub Actions **secrets**, no en *Variables* ni hardcodeadas en el repo/YAML; corrige cuando el agente usa `vars.*`. Confidence: 0.72

## Workflow
- Prefiere que se escriba un plan y se revise/apruebe ANTES de crear un proyecto o scaffold de código ("un plan antes de crear el proyecto"). Confidence: 0.65
- Prefiere que las automatizaciones en GitHub Actions procesen UN solo elemento por corrida (cron frecuente, reintentos automáticos) en vez de lotes grandes por ejecución; corrige explícitamente cuando el agente propone un `limit`/lote. Confidence: 0.6
- Prefiere automatizar el sistema destino por el flujo normal de la UI (llenar el formulario campo por campo) en vez de atajos de importación masiva; rechaza explícitamente usar botones tipo "Carga masiva". Confidence: 0.65

## Communication
- Se comunica en español; responder en español (usa voseo rioplatense: "podés", "querés"). Confidence: 0.6
