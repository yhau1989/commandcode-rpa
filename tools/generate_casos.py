#!/usr/bin/env python3
"""Genera registros sintéticos para cmas-cloud-casos.xlsx aprendiendo del export real.

Lee siniestros-agricolas_*.xlsx (datos reales del sistema) y produce N filas
nuevas, coherentes entre sí, en el esquema de 57 columnas de cmas-cloud-casos.xlsx.

Reglas aprendidas del export (ver README, sección "Datos de ejemplo"):

  - Compañía Seguros del Pichincha, Sucursal PVO, Ramo 14.
  - Póliza 0000000010 → USD 1000/ha asegurados; 0000000012 → USD 1200/ha.
  - Rendimiento total (qq) = rendimiento qq/ha × superficie a cosechar.
  - Valor salvamento = rendimiento total × precio (USD 15/qq) en pérdidas parciales;
    en pérdidas totales el cultivo no se cosecha y ambos van en 0.
  - Valor de pérdida = valor asegurado − valor salvamento (127/127 filas del export
    lo cumplen). En pérdidas totales el salvamento es 0, así que la pérdida iguala
    el valor asegurado.
  - Monto deducible = valor de pérdida × % deducible (15% en la mayoría de filas).
  - Monto a indemnizar = valor de pérdida − monto deducible.

El generador es determinístico: con la misma semilla produce el mismo archivo.

Uso:
    python3 tools/generate_casos.py \
        --source files_examples/siniestros-agricolas_2026-11-13.xlsx \
        --target files_examples/cmas-cloud-casos.xlsx \
        --rows 20 --seed 20261113
"""

from __future__ import annotations

import argparse
import datetime as dt
import random
from collections import Counter, defaultdict
from pathlib import Path

import openpyxl

# --- Pools de nombres (costa ecuatoriana / Manabí) ---------------------------

SURNAMES = [
    "CEDEÑO", "ZAMBRANO", "VÉLEZ", "MACÍAS", "MENDOZA", "VERA", "LOOR",
    "PALACIOS", "CHÁVEZ", "SANTANA", "INTRIAGO", "MOREIRA", "ALCÍVAR", "BRAVO",
    "CANTOS", "DELGADO", "ESPINALES", "GILER", "HIDALGO", "LANDAZURI",
    "MEDRANDA", "NAVARRETE", "ORTIZ", "PÁRRAGA", "QUIJIJE", "RAMÍREZ",
    "SALTOS", "TAPIA", "URDANIGO", "VILLACÍS", "BAZURTO", "MERO", "PINARGOTE",
]

GIVEN_NAMES_F = [
    "MERCEDES", "CINTHYA", "GLADYS", "MARTHA", "NANCY", "ROSA", "SANDRA",
    "MARÍA", "ELENA", "JESSICA", "MARIUXI", "LILIANA", "VERÓNICA", "ANDREA",
]

GIVEN_NAMES_M = [
    "SEGUNDO", "JOSÉ", "LUIS", "ÁNGEL", "WILMER", "JORGE", "FREDDY", "JOHNNY",
    "KLEBER", "MARCO", "VÍCTOR", "BYRON", "ELVIS", "WALTER", "JIMMY", "GALO",
    "RAMIRO", "OSCAR",
]

TOPONYM = [
    "LA BRASILIA", "EL GUABITO", "SANTA TERESA", "LOS ALGODONES", "EL ENCUENTRO",
    "LA LOMA", "EL TORO", "LAS GUACHARACAS", "EL MOTETE", "LA VICHOLA",
    "SAN IGNACIO", "LOS CEIBOS", "EL PARAÍSO", "LA FLORIDA", "SAN RAMÓN",
]

VIAS = [
    "VIA SAN CLEMENTE", "VIA AL CHADE", "VIA PROCEL", "VIA LA PLAYA",
    "VIA A ROCAFUERTE", "VIA AL ENCUENTRO", "VIA A CHARAPOTO",
]

SECTORS = [
    "LA LOMA DE LAS CORONAS", "ESTERO MARACUYA", "LOS PECHICHES",
    "LA QUEBRADA DE MARCOS CHAVEZ", "ZONA ALTA DE RESBALON",
]

INSPECTORS = ["Ing. Angel Pin", "Ing. José Elao", "Ing. Jaime Baque", "Ing. Byron Mera"]

CONCLUSION = (
    "Este informe representa nuestro punto de vista en el reclamo asignado, y lo "
    "sometemos a consideración de la Aseguradora, sin perjuicio de los términos y "
    "condiciones de la Póliza de Seguros contratada, para su definición final."
)

OBS_PARCIAL = [
    (
        "Mediante un muestreo sistemático al azar se tomaron {muestras} muestras "
        "representativas, evaluándose un total de {plantas} plantas. Como resultado "
        "del análisis se obtuvo un peso acumulado de {libras} libras, equivalente a "
        "{lbpm} Lb/Pm. Al extrapolar estos datos sobre la población del cultivo, se "
        "determinó un rendimiento estimado de {qq} qq/ha, libre del {humedad} % de "
        "humedad y con un 2 % de impurezas. Con un total a cosechar de {total} qq en "
        "toda el área sembrada asegurada."
    ),
    (
        "Se realizó inspección de campo con muestreo al azar en el lote asegurado. "
        "El cultivo de maíz duro mancheno presenta afectación por déficit hídrico, "
        "evidenciada en mazorcas pequeñas y de llenado irregular. El rendimiento "
        "estimado asciende a {qq} qq/ha sobre {ha} hectárea(s) sembrada(s), para un "
        "total de {total} qq, con un contenido de humedad del {humedad} %."
    ),
    (
        "La siembra se encuentra establecida en condiciones de ladera y zonas bajas, "
        "lo cual influye en la retención de humedad del suelo y acentúa el déficit "
        "hídrico. Según la evaluación en campo sobre {plantas} plantas, se estima un "
        "rendimiento de {qq} qq/ha ({total} qq en total), inferior al esperado para el "
        "ciclo INVIERNO 2026. Se determina pérdida parcial."
    ),
]

OBS_TOTAL = [
    (
        "En función de lo observado, no es viable continuar con las labores "
        "agronómicas, por lo que se determina una pérdida total del cultivo. Se "
        "procede al ajuste de los costos de inversión conforme a lo manifestado por "
        "el asegurado y al estado fenológico alcanzado. El productor indica que no se "
        "han registrado precipitaciones desde el {desde} hasta la fecha de la "
        "inspección, lo cual respalda técnicamente la magnitud de la afectación."
    ),
    (
        "El cultivo presenta afectación severa por estrés hídrico en toda el área "
        "sembrada, sin posibilidad de recuperación. Se verifica en campo que las "
        "plantas se encuentran en estado de marchitez permanente y las mazorcas no "
        "alcanzaron desarrollo productivo. Se determina pérdida total de las {ha} "
        "hectárea(s) aseguradas del sitio {sitio}."
    ),
]


# --- Utilidades -------------------------------------------------------------


def parse_num(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", "."))
    except ValueError:
        return None


def ecuadorian_id(rng: random.Random) -> int:
    """Cédula de 10 dígitos con dígito verificador válido (provincia 13, Manabí)."""
    first_nine = [1, 3] + [rng.randint(0, 9) for _ in range(7)]
    weights = [2, 1, 2, 1, 2, 1, 2, 1, 2]
    total = 0
    for digit, weight in zip(first_nine, weights):
        product = digit * weight
        total += product - 9 if product > 9 else product
    check = (10 - total % 10) % 10
    return int("".join(map(str, first_nine)) + str(check))


def person_name(rng: random.Random) -> str:
    first, second = rng.sample(SURNAMES, 2)
    given = rng.sample(GIVEN_NAMES_F if rng.random() < 0.3 else GIVEN_NAMES_M, 2)
    return f"{first} {second} {given[0]} {given[1]}"


def site_text(rng: random.Random, x: float, y: float) -> str:
    topo = rng.choice(TOPONYM)
    template = rng.randint(0, 3)
    if template == 0:
        text = f"SITIO {topo} A {rng.randint(150, 900)} MTS DE LA CASA DEL AGRICULTOR"
    elif template == 1:
        text = f"EN LA ENTRADA {topo} - EN EL SITIO {rng.choice(TOPONYM)} QUEDA SU LUGAR DE SIEMBRA"
    elif template == 2:
        text = f"{topo} - {rng.choice(VIAS)} - A {rng.randint(1, 8)} KM DEL CENTRO DE ACOPIO"
    else:
        text = f"{topo} - SECTOR {rng.choice(SECTORS)}"
    if rng.random() < 0.6:
        text += f" - Altitud:m/{int(x) if rng.random() < 0.5 else x}/{int(y)}"
    return text


def iso(day: dt.date) -> str:
    return day.isoformat()


def typical_range(values: list[float]) -> tuple[float, float]:
    """Rango p5-p95: el export tiene filas con errores de carga (valores 10x)."""
    ordered = sorted(values)
    low = ordered[max(0, int(len(ordered) * 0.05) - 1)]
    high = ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]
    return (low, high)


# --- Aprendizaje desde el export real --------------------------------------


def learn(source: Path) -> dict:
    wb = openpyxl.load_workbook(source, data_only=True)
    ws = wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    header, data = rows[0], [r for r in rows[1:] if any(v is not None for v in r)]
    idx = {name: i for i, name in enumerate(header)}

    def column(name: str) -> list:
        return [r[idx[name]] for r in data]

    locations = Counter(
        (r[idx["Provincia"]], r[idx["Cantón"]], r[idx["Parroquia"]]) for r in data
    )
    inspectors = Counter(r[idx["Inspector Asignado"]] for r in data)
    loss_types = Counter(r[idx["Tipo Pérdida"]] for r in data)
    policies = Counter(
        (
            str(r[idx["Póliza"]]).zfill(10),
            round(parse_num(r[idx["Cantidad x qq"]]) / parse_num(r[idx["Has Aseguradas"]])),
        )
        for r in data
        if parse_num(r[idx["Has Aseguradas"]]) and parse_num(r[idx["Cantidad x qq"]])
    )
    # Tarifa vigente por póliza: la moda, para no arrastrar filas con valores atípicos.
    rate_per_policy = {}
    for policy in {p for p, _ in policies}:
        rates = Counter()
        for (p, rate), weight in policies.items():
            if p == policy:
                rates[rate] = weight
        rate_per_policy[policy] = rates.most_common(1)[0][0]
    hectares = Counter(
        int(parse_num(r[idx["Has Aseguradas"]]))
        for r in data
        if parse_num(r[idx["Has Aseguradas"]]) and parse_num(r[idx["Has Aseguradas"]]) < 10
    )
    yields_ = [
        parse_num(r[idx["Rendimiento qq/ha"]])
        for r in data
        if r[idx["Tipo Pérdida"]] == "parcial"
        and parse_num(r[idx["Rendimiento qq/ha"]])
        and parse_num(r[idx["Rendimiento qq/ha"]]) > 10
    ]
    partial_ratios = [
        parse_num(r[idx["Monto Pérdida Salvamento"]]) / parse_num(r[idx["Cantidad x qq"]])
        for r in data
        if r[idx["Tipo Pérdida"]] == "parcial"
        and parse_num(r[idx["Monto Pérdida Salvamento"]])
        and parse_num(r[idx["Cantidad x qq"]])
        and 0 < parse_num(r[idx["Monto Pérdida Salvamento"]]) < parse_num(r[idx["Cantidad x qq"]])
    ]
    invoice = Counter(r[idx["Entregó Factura Inversión"]] for r in data)

    return {
        "locations": list(locations.keys()),
        "location_weights": list(locations.values()),
        "inspectors": list(inspectors.keys()),
        "inspector_weights": list(inspectors.values()),
        "loss_types": list(loss_types.keys()),
        "loss_type_weights": list(loss_types.values()),
        "policies": sorted({p for p, _ in policies}),
        "rate_per_policy": rate_per_policy,
        "hectares": list(hectares.keys()),
        "hectare_weights": list(hectares.values()),
        "yield_range": typical_range(yields_),
        "salvage_ratio": typical_range(partial_ratios),
        "invoice_weights": invoice,
    }


# --- Generación -------------------------------------------------------------


def build_rows(profile: dict, count: int, rng: random.Random) -> list[dict]:
    rows = []
    used_ids = set()
    seq = 900

    for _ in range(count):
        policy = rng.choice(profile["policies"])
        rate = profile["rate_per_policy"][policy]
        hectares = rng.choices(profile["hectares"], weights=profile["hectare_weights"])[0]
        loss_type = rng.choices(profile["loss_types"], weights=profile["loss_type_weights"])[0]
        province, canton, parish = rng.choices(
            profile["locations"], weights=profile["location_weights"]
        )[0]

        # Fechas coherentes: siembra → siniestro → aviso → asignación → inspección → informe
        sowing = dt.date(2026, 1, 2) + dt.timedelta(days=rng.randint(0, 45))
        event = sowing + dt.timedelta(days=rng.randint(130, 190))
        notice = event + dt.timedelta(days=rng.randint(0, 20))
        assignment = notice + dt.timedelta(days=rng.randint(1, 10))
        site_inspection = assignment + dt.timedelta(days=rng.randint(5, 25))
        report = site_inspection + dt.timedelta(days=rng.randint(1, 5))
        validity_start = sowing - dt.timedelta(days=rng.randint(2, 10))
        validity_end = validity_start + dt.timedelta(days=rng.randint(133, 137))

        # Coordenadas UTM 17S (Manabí / Guayas)
        x = float(rng.randint(550_000, 640_000))
        y = float(rng.randint(9_790_000, 9_920_000))
        insp_x = x + rng.randint(-900, 900)
        insp_y = y + rng.randint(-900, 900)

        insured_value = int(hectares * rate)  # valor asegurado (cantidad x qq)
        price = 15.0

        if loss_type == "parcial":
            # El export cumple en 127/127 filas: pérdida = valor asegurado − salvamento.
            salvage = round(insured_value * rng.uniform(*profile["salvage_ratio"]), 2)
            yield_per_ha = round(salvage / (price * hectares), 2)
            total_qq = round(yield_per_ha * hectares, 2)
            salvage = round(total_qq * price, 2)
            loss_value = round(insured_value - salvage, 2)
            adjusted_per_ha = 0.0
            invested_total = 0.0
        else:
            # Pérdida total: no hay cosecha, se indemniza el valor asegurado.
            yield_per_ha = 0.0
            total_qq = 0.0
            price = 0.0
            salvage = 0.0
            loss_value = float(insured_value)
            adjusted_per_ha = float(rate)
            invested_total = float(insured_value)

        deductible_pct = 15 if rng.random() < 0.85 else 0
        deductible = round(loss_value * deductible_pct / 100, 2)
        indemnity = round(loss_value - deductible, 2)

        seq += rng.randint(1, 4)
        while seq in used_ids:
            seq += 1
        used_ids.add(seq)

        sitio = site_text(rng, x, y)
        obs_parcial = rng.choice(OBS_PARCIAL).format(
            muestras=rng.randint(4, 12),
            plantas=rng.randint(24, 96),
            libras=round(rng.uniform(3.0, 12.0), 2),
            lbpm=round(rng.uniform(0.09, 0.15), 3),
            qq=yield_per_ha,
            humedad=round(rng.uniform(15.0, 18.5), 1),
            total=total_qq,
            ha=hectares,
        )
        obs_total = rng.choice(OBS_TOTAL).format(
            desde=iso(event - dt.timedelta(days=rng.randint(20, 60))),
            ha=hectares,
            sitio=sitio.split(" - ")[0],
        )

        rows.append({
            "Compañía asegurada": "Seguros del Pichincha",
            "Sucursal": "PVO",
            "Ramo": "14",
            "Póliza": policy,
            "Certificado": int(rng.randint(100, 4200)),
            "Inicio vigencia": iso(validity_start),
            "Fin vigencia": iso(validity_end),
            "Cédula": ecuadorian_id(rng),
            "Nombre asegurado": person_name(rng),
            "N° siniestro": f"2026{seq:010d}",
            "N° aviso": f"SDP5_PDS_{11_200_000 + seq:012d}",
            "Fecha aviso/notificación": iso(notice),
            "Fecha siniestro": iso(event),
            "Fecha asignación": iso(assignment),
            "Fecha siniestro campo": iso(event),
            "Cobertura": "00 SEQUIA O DEFICIENCIA DE LLUVIA",
            "Provincia": province,
            "Cantón": canton,
            "Parroquia": parish,
            "Sitio de inversión": sitio,
            "Coordenada X": str(int(x)),
            "Coordenada Y": str(int(y)),
            "Hectáreas aseguradas": hectares,
            "Hectáreas sembradas": hectares,
            "Área afectada": hectares,
            "Cultivo": "CULTIVO DE MAIZ DURO MANCHENO",
            "Ciclo": "INVIERNO 2026",
            "Fecha real de siembra": iso(sowing),
            "Tipo de evento": "Siniestro",
            "Causa": "00 SEQUIA O DEFICIENCIA DE LLUVIA",
            "Tipo de pérdida": loss_type,
            "Observaciones": obs_total if loss_type == "total" else obs_parcial,
            "Fecha inspección": iso(site_inspection),
            "Fecha envío informe": iso(report),
            "Coord. X inspección": str(int(insp_x)),
            "Coord. Y inspección": str(int(insp_y)),
            "Inspector asignado": rng.choices(
                profile["inspectors"], weights=profile["inspector_weights"]
            )[0],
            "¿Entregó factura de inversión?": "Sí" if rng.random() < 0.12 else "No",
            "Conclusiones ajustador": CONCLUSION,
            "¿Prestó facilidades?": "Sí",
            "¿Aplica negativa?": "No",
            "Tipo de negativa": "No aplica",
            "Causas cerrado sin pago": "No aplica",
            "Observaciones indemnización": "Sin observaciones" if rng.random() < 0.4 else CONCLUSION,
            "Precio ajuste (qq)": price,
            "Valor asegurado": insured_value,
            "Rendimiento qq/ha": yield_per_ha,
            "Superficie a cosechar (ha)": hectares,
            "Rendimiento total (qq)": total_qq,
            "Valor Salvamento": salvage,
            "Total costo de inversión / valor de perdida": loss_value,
            "Valor de pérdida por hectárea ajustada": adjusted_per_ha,
            "Valor invertido en total de hectáreas": invested_total,
            "Tipo Deducible": 5,
            "% deducible": deductible_pct,
            "Monto deducible": deductible,
            "Monto a indemnizar": indemnity,
        })

        rows[-1]["_sort_key"] = (event, seq)

    rows.sort(key=lambda r: r.pop("_sort_key"), reverse=True)
    return rows


# --- Escritura y validación -------------------------------------------------


def write_cases(target: Path, rows: list[dict]) -> None:
    wb = openpyxl.load_workbook(target)
    ws = wb.worksheets[0]
    header = [cell.value for cell in ws[1]]

    if ws.max_row > 1:
        ws.delete_rows(2, ws.max_row - 1)

    for offset, row in enumerate(rows, start=2):
        for column, name in enumerate(header, start=1):
            ws.cell(row=offset, column=column, value=row[name])

    wb.save(target)


def validate(rows: list[dict], profile: dict) -> list[str]:
    problems = []
    seen = set()
    for row in rows:
        key = (row["N° siniestro"], row["Certificado"], row["Cédula"])
        if key in seen:
            problems.append(f"duplicado: {key}")
        seen.add(key)

        if row["Monto a indemnizar"] != round(
            row["Total costo de inversión / valor de perdida"] - row["Monto deducible"], 2
        ):
            problems.append(f"indemnización inconsistente: {row['N° siniestro']}")

        if row["Rendimiento total (qq)"] != round(
            row["Rendimiento qq/ha"] * row["Superficie a cosechar (ha)"], 2
        ):
            problems.append(f"rendimiento inconsistente: {row['N° siniestro']}")

        if row["Tipo de pérdida"] == "parcial":
            if row["Total costo de inversión / valor de perdida"] != round(
                row["Valor asegurado"] - row["Valor Salvamento"], 2
            ):
                problems.append(f"pérdida parcial != asegurado - salvamento: {row['N° siniestro']}")
            if row["Total costo de inversión / valor de perdida"] <= 0:
                problems.append(f"pérdida parcial no positiva: {row['N° siniestro']}")
        elif row["Total costo de inversión / valor de perdida"] != row["Valor asegurado"]:
            problems.append(f"pérdida total no iguala valor asegurado: {row['N° siniestro']}")

        expected_insured = int(
            row["Superficie a cosechar (ha)"] * profile["rate_per_policy"][row["Póliza"]]
        )
        if row["Valor asegurado"] != expected_insured:
            problems.append(f"valor asegurado fuera de tarifa: {row['N° siniestro']}")

        if row["Fecha siniestro"] > row["Fecha aviso/notificación"]:
            problems.append(f"aviso anterior al siniestro: {row['N° siniestro']}")

        if row["Fecha inspección"] < row["Fecha asignación"]:
            problems.append(f"inspección antes de asignación: {row['N° siniestro']}")

    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="Export real del sistema")
    parser.add_argument("--target", required=True, help="Archivo de casos a generar")
    parser.add_argument("--rows", type=int, default=20)
    parser.add_argument("--seed", type=int, default=20261113)
    args = parser.parse_args()

    profile = learn(Path(args.source))
    rng = random.Random(args.seed)
    rows = build_rows(profile, args.rows, rng)

    problems = validate(rows, profile)
    if problems:
        for problem in problems:
            print(f"  ✗ {problem}")
        return 1

    write_cases(Path(args.target), rows)

    totals = Counter(row["Tipo de pérdida"] for row in rows)
    print(f"{len(rows)} registros escritos en {args.target}")
    print(f"  parcial={totals['parcial']} total={totals['total']}")
    print(f"  indemnización total={sum(r['Monto a indemnizar'] for r in rows):,.2f} USD")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
