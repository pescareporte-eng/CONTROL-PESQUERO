from __future__ import annotations

import uuid
import unicodedata
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from flask import Blueprint, jsonify, request, session, current_app, send_file, make_response
from io import BytesIO

from ..services.vessel_codes import next_vessel_code

from .auth import login_required
from ..services.google_sheets import get_repository
from ..services.validation import parse_decimal, parse_date, money, dec
from ..services.reports import collect_report, report_pdf, report_excel, MODULES

api_bp = Blueprint("api", __name__)
ICE_UNITS = ["BLOQUE", "BOLSA", "KG", "TM", "UNIDAD", "OTRO"]

@api_bp.errorhandler(ValueError)
def value_error(error):
    return jsonify({"error": str(error)}), 400

@api_bp.errorhandler(Exception)
def general_error(error):
    current_app.logger.exception("API error: %s", error)
    return jsonify({"error": "No se pudo completar la operación. Verifica la conexión con Google Sheets y Drive."}), 500

def actor():
    return session.get("user_email", "personal")

def active_rows(repo, tab):
    return [r for r in repo.get_all(tab) if r.get("estado", "ACTIVO") == "ACTIVO"]

def normalize_vessel_name(value):
    """Normaliza nombres para evitar duplicados por mayúsculas, espacios o tildes."""
    raw = unicodedata.normalize("NFKD", str(value or "").strip())
    without_marks = "".join(char for char in raw if not unicodedata.combining(char))
    return " ".join(without_marks.casefold().split())


def find_duplicate_vessel(repo, name, exclude_id=None):
    normalized = normalize_vessel_name(name)
    if not normalized:
        return None
    for vessel in repo.get_all("EMBARCACIONES"):
        if vessel.get("id") == exclude_id:
            continue
        if normalize_vessel_name(vessel.get("nombre")) == normalized:
            return vessel
    return None


def vessel_exists(repo, vessel_id):
    vessel = repo.find("EMBARCACIONES", vessel_id)
    if not vessel or vessel[1].get("estado") != "ACTIVA":
        raise ValueError("Selecciona una embarcación activa.")
    return vessel[1]


def resolve_vessel(repo, data):
    """Acepta el ID elegido o resuelve el nombre escrito por el usuario."""
    vessel_id = str(data.get("embarcacion_id", "")).strip()
    if vessel_id:
        return vessel_id, vessel_exists(repo, vessel_id)

    name = str(data.get("embarcacion_nombre", "")).strip()
    if not name:
        raise ValueError("Escribe o selecciona una embarcación.")
    normalized = normalize_vessel_name(name)
    matches = [
        vessel for vessel in repo.get_all("EMBARCACIONES")
        if vessel.get("estado") == "ACTIVA"
        and normalize_vessel_name(vessel.get("nombre")) == normalized
    ]
    if len(matches) == 1:
        return str(matches[0].get("id", "")), matches[0]
    if len(matches) > 1:
        raise ValueError("Hay embarcaciones repetidas con ese nombre. Revisa el catálogo de Embarcaciones.")
    raise ValueError(
        f'La embarcación "{name}" no está registrada. Ingresa a Embarcaciones y pulsa '
        '"Registrar embarcación" para agregarla.'
    )

@api_bp.get("/health")
def health():
    return jsonify({"status": "ok", "service": "control-pesquero"})

@api_bp.get("/vessels")
@login_required
def get_vessels():
    repo = get_repository()
    rows = repo.get_all("EMBARCACIONES")
    return jsonify([r for r in rows if r.get("estado") == "ACTIVA"])

@api_bp.get("/vessels/next-code")
@login_required
def get_next_vessel_code():
    repo = get_repository()
    # El mismo bloqueo protege la lectura del correlativo y el alta dentro de este proceso.
    with repo._lock:
        return jsonify({"codigo": next_vessel_code(repo.get_all("EMBARCACIONES"))})

@api_bp.post("/vessels")
@login_required
def create_vessel():
    data = request.get_json(silent=True) or {}
    repo = get_repository()
    name = str(data.get("nombre", "")).strip().upper()
    matricula = str(data.get("matricula", "")).strip().upper()
    if not name:
        raise ValueError("El nombre de la embarcación es obligatorio.")
    record_id = uuid.uuid4().hex
    # La comprobación y el alta comparten bloqueo para reducir carreras entre altas.
    with repo._lock:
        duplicate = find_duplicate_vessel(repo, name)
        if duplicate:
            raise ValueError(
                f'Ya existe una embarcación con el nombre "{duplicate.get("nombre", name)}" '
                f'(código {duplicate.get("codigo", "sin código")}). No se permiten nombres duplicados.'
            )
        # El código se calcula en el servidor; nunca se confía en el código del navegador.
        code = next_vessel_code(repo.get_all("EMBARCACIONES"))
        item = {"id": record_id, "codigo": code, "nombre": name, "matricula": matricula, "estado": "ACTIVA", "fecha_creacion": datetime.now().isoformat(timespec="seconds")}
        repo.append("EMBARCACIONES", item)
    repo.audit(actor(), "CREAR", "EMBARCACIONES", record_id, f"Alta de embarcación {code} - {name}")
    return jsonify(item), 201

@api_bp.put("/vessels/<record_id>")
@login_required
def edit_vessel(record_id):
    data = request.get_json(silent=True) or {}
    repo = get_repository()
    with repo._lock:
        found = repo.find("EMBARCACIONES", record_id)
        if not found or found[1].get("estado") != "ACTIVA":
            return jsonify({"error": "Embarcación no encontrada o inactiva."}), 404
        name = str(data.get("nombre", found[1].get("nombre", ""))).strip().upper()
        matricula = str(data.get("matricula", found[1].get("matricula", ""))).strip().upper()
        if not name:
            raise ValueError("El nombre de la embarcación es obligatorio.")
        duplicate = find_duplicate_vessel(repo, name, exclude_id=record_id)
        if duplicate:
            raise ValueError(
                f'Ya existe otra embarcación con el nombre "{duplicate.get("nombre", name)}" '
                f'(código {duplicate.get("codigo", "sin código")}). No se permiten nombres duplicados.'
            )
        updated = repo.update("EMBARCACIONES", record_id, {"nombre": name, "matricula": matricula})
    repo.audit(actor(), "EDITAR", "EMBARCACIONES", record_id, f"Edición de embarcación {updated.get('codigo')}: {name}")
    return jsonify(updated)

@api_bp.post("/vessels/<record_id>/deactivate")
@login_required
def deactivate_vessel(record_id):
    repo = get_repository()
    updated = repo.update("EMBARCACIONES", record_id, {"estado": "INACTIVA"})
    if not updated: return jsonify({"error": "Embarcación no encontrada."}), 404
    repo.audit(actor(), "DESACTIVAR", "EMBARCACIONES", record_id, "Embarcación desactivada; se conservan sus históricos.")
    return jsonify({"ok": True})

@api_bp.get("/fishing")
@login_required
def get_fishing():
    repo = get_repository()
    rows = active_rows(repo, "INGRESO_PESCA")
    desde, hasta = request.args.get("desde", ""), request.args.get("hasta", "")
    vessel_id = request.args.get("embarcacion_id", "")
    if desde: rows = [r for r in rows if r.get("fecha", "") >= desde]
    if hasta: rows = [r for r in rows if r.get("fecha", "") <= hasta]
    if vessel_id: rows = [r for r in rows if r.get("embarcacion_id") == vessel_id]
    vessels = {v["id"]: v for v in repo.get_all("EMBARCACIONES")}
    for row in rows:
        vessel = vessels.get(row.get("embarcacion_id"), {})
        row["embarcacion_nombre"] = vessel.get("nombre", "(embarcación no disponible)")
        row["embarcacion_codigo"] = vessel.get("codigo", "")
    return jsonify(sorted(rows, key=lambda x: x.get("fecha", ""), reverse=True))

@api_bp.post("/fishing")
@login_required
def create_fishing():
    data = request.get_json(silent=True) or {}
    repo = get_repository()
    date_value = parse_date(data.get("fecha", ""))
    vessel_id, vessel = resolve_vessel(repo, data)
    tm = parse_decimal(data.get("toneladas_tm", ""), "toneladas TM")
    kg = parse_decimal(data.get("kilos_kg", ""), "kilos KG")
    if tm == 0 and kg == 0:
        raise ValueError("Ingresa toneladas, kilos o ambos; el registro no puede estar vacío.")
    record_id = uuid.uuid4().hex
    item = {"id": record_id, "fecha": date_value, "embarcacion_id": vessel_id, "toneladas_tm": str(tm), "kilos_kg": str(kg), "observaciones": str(data.get("observaciones", "")).strip(), "estado": "ACTIVO", "usuario_registro": actor(), "fecha_registro": datetime.now().isoformat(timespec="seconds")}
    repo.append("INGRESO_PESCA", item)
    repo.audit(actor(), "CREAR", "PESCA", record_id, f"Desembarque {vessel.get('nombre')}: {tm} TM / {kg} KG")
    return jsonify(item), 201

@api_bp.put("/fishing/<record_id>")
@login_required
def edit_fishing(record_id):
    data = request.get_json(silent=True) or {}
    repo = get_repository()
    found = repo.find("INGRESO_PESCA", record_id)
    if not found or found[1].get("estado") != "ACTIVO":
        return jsonify({"error": "Ingreso de pesca no encontrado o inactivo."}), 404
    old = found[1]
    date_value = parse_date(data.get("fecha", old.get("fecha", "")))
    tm = parse_decimal(data.get("toneladas_tm", old.get("toneladas_tm", "0")), "toneladas TM", allow_zero=True)
    kg = parse_decimal(data.get("kilos_kg", old.get("kilos_kg", "0")), "kilos KG", allow_zero=True)
    if tm == 0 and kg == 0:
        raise ValueError("El ingreso debe conservar TM, KG o ambos mayores que cero.")
    related = [v for v in active_rows(repo, "VALORIZACION_PESCA") if v.get("ingreso_pesca_id") == record_id]
    used_tm = sum((dec(v.get("toneladas_valorizadas")) for v in related), Decimal("0"))
    used_kg = sum((dec(v.get("kilos_valorizados")) for v in related), Decimal("0"))
    if tm < used_tm:
        raise ValueError(f"No puedes reducir las TM por debajo de lo ya valorizado ({used_tm} TM).")
    if kg < used_kg:
        raise ValueError(f"No puedes reducir los KG por debajo de lo ya valorizado ({used_kg} KG).")
    changes = {"fecha": date_value, "toneladas_tm": str(tm), "kilos_kg": str(kg), "observaciones": str(data.get("observaciones", old.get("observaciones", ""))).strip()}
    updated = repo.update("INGRESO_PESCA", record_id, changes)
    repo.audit(actor(), "EDITAR", "PESCA", record_id, f"Edición de desembarque: {tm} TM / {kg} KG")
    return jsonify(updated)

@api_bp.post("/fishing/<record_id>/annul")
@login_required
def annul_fishing(record_id):
    repo = get_repository()
    related = [v for v in active_rows(repo, "VALORIZACION_PESCA") if v.get("ingreso_pesca_id") == record_id]
    if related:
        raise ValueError("Este desembarque tiene valorizaciones activas. Anula primero las valorizaciones relacionadas.")
    updated = repo.update("INGRESO_PESCA", record_id, {"estado": "ANULADO"})
    if not updated: return jsonify({"error": "Registro no encontrado."}), 404
    repo.audit(actor(), "ANULAR", "PESCA", record_id, "Se anuló un ingreso de pesca.")
    return jsonify({"ok": True})

@api_bp.get("/valuations")
@login_required
def get_valuations():
    repo = get_repository()
    rows = active_rows(repo, "VALORIZACION_PESCA")
    landings = {r["id"]: r for r in repo.get_all("INGRESO_PESCA")}
    vessels = {v["id"]: v for v in repo.get_all("EMBARCACIONES")}
    desde, hasta = request.args.get("desde", ""), request.args.get("hasta", "")
    result = []
    for source in rows:
        row = dict(source)
        if desde and row.get("fecha_valorizacion", "") < desde: continue
        if hasta and row.get("fecha_valorizacion", "") > hasta: continue
        landing = landings.get(row.get("ingreso_pesca_id"), {})
        vessel = vessels.get(landing.get("embarcacion_id"), {})
        row["embarcacion_nombre"] = vessel.get("nombre", "")
        row["embarcacion_codigo"] = vessel.get("codigo", "")
        row["fecha_desembarque"] = landing.get("fecha", "")
        # Los registros históricos mixtos se muestran en ambos historiales según su cantidad.
        row["toneladas_valorizadas"] = str(dec(row.get("toneladas_valorizadas")))
        row["kilos_valorizados"] = str(dec(row.get("kilos_valorizados")))
        row["precio_por_tm"] = str(dec(row.get("precio_por_tm")))
        row["precio_por_kg"] = str(dec(row.get("precio_por_kg")))
        row["importe_tm"] = str(dec(row.get("importe_tm")) if row.get("importe_tm") not in (None, "") else dec(row.get("importe_total")))
        row["importe_kg"] = str(dec(row.get("importe_kg")))
        row["importe_total"] = str(dec(row.get("importe_total")))
        kind = str(row.get("tipo_valorizacion", "")).upper()
        if kind not in ("TM", "KG"):
            tm_qty, kg_qty = dec(row.get("toneladas_valorizadas")), dec(row.get("kilos_valorizados"))
            kind = "MIXTA" if tm_qty > 0 and kg_qty > 0 else ("KG" if kg_qty > 0 else "TM")
        row["tipo_valorizacion"] = kind
        result.append(row)
    return jsonify(sorted(result, key=lambda x: x.get("fecha_valorizacion", ""), reverse=True))

@api_bp.get("/available-landings")
@login_required
def available_landings():
    repo = get_repository()
    landings = active_rows(repo, "INGRESO_PESCA")
    values = active_rows(repo, "VALORIZACION_PESCA")
    vessels = {v["id"]: v for v in repo.get_all("EMBARCACIONES")}
    totals_tm, totals_kg = {}, {}
    for valuation in values:
        key = valuation.get("ingreso_pesca_id")
        totals_tm[key] = totals_tm.get(key, Decimal("0")) + dec(valuation.get("toneladas_valorizadas"))
        totals_kg[key] = totals_kg.get(key, Decimal("0")) + dec(valuation.get("kilos_valorizados"))
    result = []
    for landing in landings:
        tm = dec(landing.get("toneladas_tm"))
        kg = dec(landing.get("kilos_kg"))
        valued_tm = totals_tm.get(landing["id"], Decimal("0"))
        valued_kg = totals_kg.get(landing["id"], Decimal("0"))
        remaining_tm = max(Decimal("0"), tm - valued_tm)
        remaining_kg = max(Decimal("0"), kg - valued_kg)
        if remaining_tm > 0 or remaining_kg > 0:
            vessel = vessels.get(landing.get("embarcacion_id"), {})
            result.append({
                "id": landing["id"], "fecha": landing.get("fecha"),
                "embarcacion_nombre": vessel.get("nombre", ""), "embarcacion_codigo": vessel.get("codigo", ""),
                "toneladas_tm": str(tm), "toneladas_valorizadas": str(valued_tm), "pendiente_tm": str(remaining_tm),
                "kilos_kg": str(kg), "kilos_valorizados": str(valued_kg), "pendiente_kg": str(remaining_kg),
            })
    return jsonify(sorted(result, key=lambda x: x.get("fecha", ""), reverse=True))

@api_bp.post("/valuations")
@login_required
def create_valuation():
    data = request.get_json(silent=True) or {}
    repo = get_repository()
    kind = str(data.get("tipo_valorizacion", "")).strip().upper()
    if kind not in ("TM", "KG"):
        raise ValueError("Selecciona si la valorización corresponde a TM o KG.")
    landing_id = str(data.get("ingreso_pesca_id", ""))
    landing_found = repo.find("INGRESO_PESCA", landing_id)
    if not landing_found or landing_found[1].get("estado") != "ACTIVO":
        raise ValueError("Selecciona un ingreso de pesca válido.")
    landing = landing_found[1]
    valuation_date = parse_date(data.get("fecha_valorizacion", ""), "fecha de valorización")

    tm = parse_decimal(data.get("toneladas_valorizadas", "0") or "0", "TM a valorizar", allow_zero=True)
    kg = parse_decimal(data.get("kilos_valorizados", "0") or "0", "KG a valorizar", allow_zero=True)
    if kind == "TM" and (tm <= 0 or kg != 0):
        raise ValueError("Una valorización TM debe contener únicamente una cantidad mayor que cero en TM.")
    if kind == "KG" and (kg <= 0 or tm != 0):
        raise ValueError("Una valorización KG debe contener únicamente una cantidad mayor que cero en KG.")

    price_tm_raw = str(data.get("precio_por_tm", "")).strip()
    price_kg_raw = str(data.get("precio_por_kg", "")).strip()
    if kind == "TM" and not price_tm_raw:
        raise ValueError("Ingresa el precio por TM.")
    if kind == "KG" and not price_kg_raw:
        raise ValueError("Ingresa el precio por KG.")
    price_tm = parse_decimal(price_tm_raw or "0", "precio por TM", allow_zero=True, places=Decimal("0.01"))
    price_kg = parse_decimal(price_kg_raw or "0", "precio por KG", allow_zero=True, places=Decimal("0.01"))

    active_vals = [x for x in active_rows(repo, "VALORIZACION_PESCA") if x.get("ingreso_pesca_id") == landing_id]
    previous_tm = sum((dec(x.get("toneladas_valorizadas")) for x in active_vals), Decimal("0"))
    previous_kg = sum((dec(x.get("kilos_valorizados")) for x in active_vals), Decimal("0"))
    available_tm = max(Decimal("0"), dec(landing.get("toneladas_tm")) - previous_tm)
    available_kg = max(Decimal("0"), dec(landing.get("kilos_kg")) - previous_kg)
    if kind == "TM" and tm > available_tm:
        raise ValueError(f"La cantidad supera el saldo TM pendiente. Disponible: {available_tm:.3f} TM.")
    if kind == "KG" and kg > available_kg:
        raise ValueError(f"La cantidad supera el saldo KG pendiente. Disponible: {available_kg:.3f} KG.")

    amount_tm = money(tm * price_tm) if kind == "TM" else Decimal("0.00")
    amount_kg = money(kg * price_kg) if kind == "KG" else Decimal("0.00")
    total = money(amount_tm + amount_kg)
    record_id = uuid.uuid4().hex
    item = {
        "id": record_id, "ingreso_pesca_id": landing_id, "fecha_valorizacion": valuation_date,
        "tipo_valorizacion": kind,
        "toneladas_valorizadas": str(tm), "precio_por_tm": str(price_tm),
        "kilos_valorizados": str(kg), "precio_por_kg": str(price_kg),
        "importe_tm": str(amount_tm), "importe_kg": str(amount_kg), "importe_total": str(total),
        "observaciones": str(data.get("observaciones", "")).strip(), "estado": "ACTIVO",
        "usuario_registro": actor(), "fecha_registro": datetime.now().isoformat(timespec="seconds"),
    }
    repo.append("VALORIZACION_PESCA", item)
    detail = f"Valorización {kind}: {tm} TM x S/ {price_tm} = S/ {amount_tm}" if kind == "TM" else f"Valorización {kind}: {kg} KG x S/ {price_kg} = S/ {amount_kg}"
    repo.audit(actor(), "CREAR", f"VALORIZACION_{kind}", record_id, detail)
    return jsonify(item), 201

@api_bp.put("/valuations/<record_id>")
@login_required
def edit_valuation(record_id):
    data = request.get_json(silent=True) or {}
    repo = get_repository()
    found = repo.find("VALORIZACION_PESCA", record_id)
    if not found or found[1].get("estado") != "ACTIVO":
        return jsonify({"error": "Valorización no encontrada o inactiva."}), 404
    old = found[1]
    kind = str(old.get("tipo_valorizacion", "") or ("KG" if dec(old.get("kilos_valorizados")) > 0 else "TM")).upper()
    landing_id = old.get("ingreso_pesca_id", "")
    landing_found = repo.find("INGRESO_PESCA", landing_id)
    if not landing_found or landing_found[1].get("estado") != "ACTIVO":
        raise ValueError("El desembarque asociado ya no está activo.")
    landing = landing_found[1]
    date_value = parse_date(data.get("fecha_valorizacion", old.get("fecha_valorizacion", "")), "fecha de valorización")
    if kind == "TM":
        qty = parse_decimal(data.get("toneladas_valorizadas", old.get("toneladas_valorizadas", "0")), "TM a valorizar")
        price = parse_decimal(data.get("precio_por_tm", old.get("precio_por_tm", "0")), "precio por TM", places=Decimal("0.01"))
        used = sum((dec(v.get("toneladas_valorizadas")) for v in active_rows(repo, "VALORIZACION_PESCA") if v.get("ingreso_pesca_id") == landing_id and v.get("id") != record_id), Decimal("0"))
        available = max(Decimal("0"), dec(landing.get("toneladas_tm")) - used)
        if qty > available: raise ValueError(f"La cantidad supera el saldo TM pendiente. Disponible: {available:.3f} TM.")
        amount_tm, amount_kg, kg, price_kg = money(qty * price), Decimal("0.00"), Decimal("0"), Decimal("0")
        tm = qty
    elif kind == "KG":
        qty = parse_decimal(data.get("kilos_valorizados", old.get("kilos_valorizados", "0")), "KG a valorizar")
        price = parse_decimal(data.get("precio_por_kg", old.get("precio_por_kg", "0")), "precio por KG", places=Decimal("0.01"))
        used = sum((dec(v.get("kilos_valorizados")) for v in active_rows(repo, "VALORIZACION_PESCA") if v.get("ingreso_pesca_id") == landing_id and v.get("id") != record_id), Decimal("0"))
        available = max(Decimal("0"), dec(landing.get("kilos_kg")) - used)
        if qty > available: raise ValueError(f"La cantidad supera el saldo KG pendiente. Disponible: {available:.3f} KG.")
        amount_tm, amount_kg, tm, price_tm = Decimal("0.00"), money(qty * price), Decimal("0"), Decimal("0")
        kg, price_kg = qty, price
    else:
        raise ValueError("No se reconoce el tipo de valorización de este registro.")
    total = money(amount_tm + amount_kg)
    changes = {"fecha_valorizacion": date_value, "toneladas_valorizadas": str(tm), "precio_por_tm": str(price_tm if kind == "KG" else price), "kilos_valorizados": str(kg), "precio_por_kg": str(price_kg if kind == "KG" else Decimal("0")), "importe_tm": str(amount_tm), "importe_kg": str(amount_kg), "importe_total": str(total)}
    changes["observaciones"] = str(data.get("observaciones", old.get("observaciones", ""))).strip()
    updated = repo.update("VALORIZACION_PESCA", record_id, changes)
    repo.audit(actor(), "EDITAR", f"VALORIZACION_{kind}", record_id, f"Edición de valorización {kind}: S/ {total}")
    return jsonify(updated)

@api_bp.post("/valuations/<record_id>/annul")
@login_required
def annul_valuation(record_id):
    repo = get_repository()
    updated = repo.update("VALORIZACION_PESCA", record_id, {"estado": "ANULADO"})
    if not updated: return jsonify({"error": "Registro no encontrado."}), 404
    repo.audit(actor(), "ANULAR", "VALORIZACION", record_id, "Se anuló una valorización de pesca.")
    return jsonify({"ok": True})

@api_bp.get("/ice")
@login_required
def get_ice():
    repo = get_repository()
    rows = active_rows(repo, "DESPACHO_HIELO")
    vessels = {v["id"]: v for v in repo.get_all("EMBARCACIONES")}
    desde, hasta = request.args.get("desde", ""), request.args.get("hasta", "")
    vessel_id = request.args.get("embarcacion_id", "")
    out = []
    for row in rows:
        if desde and row.get("fecha", "") < desde: continue
        if hasta and row.get("fecha", "") > hasta: continue
        if vessel_id and row.get("embarcacion_id") != vessel_id: continue
        vessel = vessels.get(row.get("embarcacion_id"), {})
        row["embarcacion_nombre"] = vessel.get("nombre", "")
        row["embarcacion_codigo"] = vessel.get("codigo", "")
        out.append(row)
    return jsonify(sorted(out, key=lambda x: x.get("fecha", ""), reverse=True))

@api_bp.post("/ice")
@login_required
def create_ice():
    data = request.get_json(silent=True) or {}
    repo = get_repository()
    date_value = parse_date(data.get("fecha", ""))
    vessel_id, vessel = resolve_vessel(repo, data)
    quantity = parse_decimal(data.get("cantidad", ""), "cantidad", allow_zero=False)
    unit = str(data.get("unidad", "")).upper().strip()
    if unit not in ICE_UNITS: raise ValueError("Selecciona una unidad válida.")
    price = parse_decimal(data.get("precio_unitario", ""), "precio unitario", places=Decimal("0.01"))
    total = money(quantity * price)
    record_id = uuid.uuid4().hex
    item = {"id": record_id, "fecha": date_value, "embarcacion_id": vessel_id, "cantidad": str(quantity), "unidad": unit, "precio_unitario": str(price), "importe_total": str(total), "observaciones": str(data.get("observaciones", "")).strip(), "estado": "ACTIVO", "usuario_registro": actor(), "fecha_registro": datetime.now().isoformat(timespec="seconds")}
    repo.append("DESPACHO_HIELO", item)
    repo.audit(actor(), "CREAR", "HIELO", record_id, f"Hielo {vessel.get('nombre')}: {quantity} {unit} x S/ {price} = S/ {total}")
    return jsonify(item), 201

@api_bp.put("/ice/<record_id>")
@login_required
def edit_ice(record_id):
    data = request.get_json(silent=True) or {}
    repo = get_repository()
    found = repo.find("DESPACHO_HIELO", record_id)
    if not found or found[1].get("estado") != "ACTIVO":
        return jsonify({"error": "Despacho de hielo no encontrado o inactivo."}), 404
    old = found[1]
    date_value = parse_date(data.get("fecha", old.get("fecha", "")))
    quantity = parse_decimal(data.get("cantidad", old.get("cantidad", "")), "cantidad")
    unit = str(data.get("unidad", old.get("unidad", ""))).upper().strip()
    if unit not in ICE_UNITS: raise ValueError("Selecciona una unidad válida.")
    price = parse_decimal(data.get("precio_unitario", old.get("precio_unitario", "")), "precio unitario", places=Decimal("0.01"))
    total = money(quantity * price)
    changes = {"fecha": date_value, "cantidad": str(quantity), "unidad": unit, "precio_unitario": str(price), "importe_total": str(total), "observaciones": str(data.get("observaciones", old.get("observaciones", ""))).strip()}
    updated = repo.update("DESPACHO_HIELO", record_id, changes)
    repo.audit(actor(), "EDITAR", "HIELO", record_id, f"Edición de despacho: {quantity} {unit}, S/ {total}")
    return jsonify(updated)

@api_bp.post("/ice/<record_id>/annul")
@login_required
def annul_ice(record_id):
    repo = get_repository()
    updated = repo.update("DESPACHO_HIELO", record_id, {"estado": "ANULADO"})
    if not updated: return jsonify({"error": "Registro no encontrado."}), 404
    repo.audit(actor(), "ANULAR", "HIELO", record_id, "Se anuló un despacho de hielo.")
    return jsonify({"ok": True})

@api_bp.get("/stay-expenses")
@login_required
def get_stay_expenses():
    repo = get_repository()
    rows = active_rows(repo, "GASTOS_ESTADIA")
    desde, hasta = request.args.get("desde", ""), request.args.get("hasta", "")
    if desde: rows = [r for r in rows if r.get("fecha", "") >= desde]
    if hasta: rows = [r for r in rows if r.get("fecha", "") <= hasta]
    return jsonify(sorted(rows, key=lambda x: (x.get("fecha", ""), x.get("fecha_registro", "")), reverse=True))

@api_bp.post("/stay-expenses")
@login_required
def create_stay_expense():
    data = request.get_json(silent=True) or {}
    repo = get_repository()
    date_value = parse_date(data.get("fecha", ""))
    description = " ".join(str(data.get("descripcion", "")).strip().split()).upper()
    if not description:
        raise ValueError("La descripción del gasto es obligatoria.")
    price = parse_decimal(data.get("precio", ""), "precio", allow_zero=False, places=Decimal("0.01"))
    record_id = uuid.uuid4().hex
    item = {
        "id": record_id, "fecha": date_value, "descripcion": description,
        "precio": str(price), "estado": "ACTIVO", "usuario_registro": actor(),
        "fecha_registro": datetime.now().isoformat(timespec="seconds"),
    }
    repo.append("GASTOS_ESTADIA", item)
    repo.audit(actor(), "CREAR", "GASTOS_ESTADIA", record_id, f"{description}: S/ {price}")
    return jsonify(item), 201

@api_bp.put("/stay-expenses/<record_id>")
@login_required
def edit_stay_expense(record_id):
    data = request.get_json(silent=True) or {}
    repo = get_repository()
    found = repo.find("GASTOS_ESTADIA", record_id)
    if not found or found[1].get("estado") != "ACTIVO":
        return jsonify({"error": "Gasto de estadía no encontrado o inactivo."}), 404
    old = found[1]
    date_value = parse_date(data.get("fecha", old.get("fecha", "")))
    description = " ".join(str(data.get("descripcion", old.get("descripcion", ""))).strip().split()).upper()
    if not description: raise ValueError("La descripción del gasto es obligatoria.")
    price = parse_decimal(data.get("precio", old.get("precio", "")), "precio", places=Decimal("0.01"))
    updated = repo.update("GASTOS_ESTADIA", record_id, {"fecha": date_value, "descripcion": description, "precio": str(price)})
    repo.audit(actor(), "EDITAR", "GASTOS_ESTADIA", record_id, f"Edición de gasto: {description}, S/ {price}")
    return jsonify(updated)

@api_bp.post("/stay-expenses/<record_id>/annul")
@login_required
def annul_stay_expense(record_id):
    repo = get_repository()
    updated = repo.update("GASTOS_ESTADIA", record_id, {"estado": "ANULADO"})
    if not updated: return jsonify({"error": "Gasto de estadía no encontrado."}), 404
    repo.audit(actor(), "ANULAR", "GASTOS_ESTADIA", record_id, "Se anuló un gasto de estadía.")
    return jsonify({"ok": True})

@api_bp.get("/dashboard")
@login_required
def dashboard_data():
    repo = get_repository()
    desde, hasta = request.args.get("desde", ""), request.args.get("hasta", "")
    fishing = [r for r in active_rows(repo, "INGRESO_PESCA") if (not desde or r.get("fecha", "") >= desde) and (not hasta or r.get("fecha", "") <= hasta)]
    ice = [r for r in active_rows(repo, "DESPACHO_HIELO") if (not desde or r.get("fecha", "") >= desde) and (not hasta or r.get("fecha", "") <= hasta)]
    vals = [r for r in active_rows(repo, "VALORIZACION_PESCA") if (not desde or r.get("fecha_valorizacion", "") >= desde) and (not hasta or r.get("fecha_valorizacion", "") <= hasta)]
    stay_expenses = [r for r in active_rows(repo, "GASTOS_ESTADIA") if (not desde or r.get("fecha", "") >= desde) and (not hasta or r.get("fecha", "") <= hasta)]
    vessel_map = {v["id"]: f"{v.get('nombre', '')} ({v.get('codigo', '')})".strip(" ()") for v in repo.get_all("EMBARCACIONES")}
    landing_map = {r["id"]: r for r in repo.get_all("INGRESO_PESCA")}
    tm = sum((dec(r.get("toneladas_tm")) for r in fishing), Decimal("0"))
    kg = sum((dec(r.get("kilos_kg")) for r in fishing), Decimal("0"))
    amount_val = sum((dec(r.get("importe_total")) for r in vals), Decimal("0"))
    amount_ice = sum((dec(r.get("importe_total")) for r in ice), Decimal("0"))
    amount_stay = sum((dec(r.get("precio")) for r in stay_expenses), Decimal("0"))
    # Las cantidades de hielo se agrupan por unidad: no se mezclan bloques, bolsas, KG y TM.
    ice_by_unit = {}
    for row in ice:
        unit = str(row.get("unidad", "OTRO") or "OTRO").upper()
        bucket = ice_by_unit.setdefault(unit, {"unidad": unit, "cantidad": Decimal("0"), "despachos": 0})
        bucket["cantidad"] += dec(row.get("cantidad"))
        bucket["despachos"] += 1
    ice_summary = [
        {"unidad": unit, "cantidad": f"{values['cantidad']:.3f}", "despachos": values["despachos"]}
        for unit, values in sorted(ice_by_unit.items())
    ]
    grouped = {}
    for r in fishing:
        name = vessel_map.get(r.get("embarcacion_id"), "Sin embarcación")
        grouped[name] = grouped.get(name, Decimal("0")) + dec(r.get("toneladas_tm"))
    top = sorted(grouped.items(), key=lambda x: x[1], reverse=True)[:5]
    daily = {}
    for r in fishing:
        key = r.get("fecha", "")
        daily[key] = daily.get(key, Decimal("0")) + dec(r.get("toneladas_tm"))
    pending_tm = Decimal("0")
    pending_kg = Decimal("0")
    valued_tm_by_landing = {}
    valued_kg_by_landing = {}
    for valuation in active_rows(repo, "VALORIZACION_PESCA"):
        landing_id = valuation.get("ingreso_pesca_id")
        valued_tm_by_landing[landing_id] = valued_tm_by_landing.get(landing_id, Decimal("0")) + dec(valuation.get("toneladas_valorizadas"))
        valued_kg_by_landing[landing_id] = valued_kg_by_landing.get(landing_id, Decimal("0")) + dec(valuation.get("kilos_valorizados"))
    for landing in fishing:
        if landing.get("id"):
            landing_id = landing["id"]
            pending_tm += max(Decimal("0"), dec(landing.get("toneladas_tm")) - valued_tm_by_landing.get(landing_id, Decimal("0")))
            pending_kg += max(Decimal("0"), dec(landing.get("kilos_kg")) - valued_kg_by_landing.get(landing_id, Decimal("0")))
    return jsonify({
        "toneladas_tm": f"{tm:.3f}", "kilos_kg": f"{kg:.3f}", "valor_pesca": f"{amount_val:.2f}", "valor_hielo": f"{amount_ice:.2f}",
        "desembarques": len(fishing), "embarcaciones_activas": len([v for v in repo.get_all("EMBARCACIONES") if v.get("estado") == "ACTIVA"]), "pendiente_tm": f"{pending_tm:.3f}", "pendiente_kg": f"{pending_kg:.3f}",
        "despachos_hielo": len(ice), "hielo_por_unidad": ice_summary,
        "gastos_estadia": f"{amount_stay:.2f}", "registros_gastos_estadia": len(stay_expenses),
        "top_embarcaciones": [{"nombre": n, "tm": float(v)} for n, v in top],
        "pesca_diaria": [{"fecha": d, "tm": float(v)} for d, v in sorted(daily.items())[-14:]],
    })

@api_bp.get("/reports/<kind>/preview")
@login_required
def preview_report(kind):
    if kind not in MODULES:
        return jsonify({"error": "Tipo de reporte no válido."}), 400
    desde = request.args.get("desde", "")
    hasta = request.args.get("hasta", "")
    vessel_id = request.args.get("embarcacion_id", "") or None
    if desde: desde = parse_date(desde, "fecha desde")
    if hasta: hasta = parse_date(hasta, "fecha hasta")
    if desde and hasta and desde > hasta:
        raise ValueError("La fecha desde no puede ser posterior a la fecha hasta.")
    data = collect_report(get_repository(), kind, desde, hasta, vessel_id)
    names = data["vessels"]
    sections = []
    if kind in ("pesca", "consolidado"):
        rows = data.get("pesca", [])
        tm = sum((dec(r.get("toneladas_tm")) for r in rows), Decimal("0"))
        kg = sum((dec(r.get("kilos_kg")) for r in rows), Decimal("0"))
        sections.append({"title": "INGRESO DE PESCA", "headers": ["Fecha", "Embarcación", "TM", "KG", "Observaciones"],
            "rows": [[r.get("fecha", ""), names.get(r.get("embarcacion_id"), "(sin nombre)"), r.get("toneladas_tm", "0"), r.get("kilos_kg", "0"), r.get("observaciones", "")] for r in rows],
            "totals": ["TOTAL", "", f"{tm:.3f}", f"{kg:.3f}", ""]})
    if kind in ("valorizacion_tm", "valorizacion") or kind == "consolidado":
        rows = data.get("valorizaciones_tm", data.get("valorizaciones", []))
        total_qty = sum((dec(r.get("toneladas_valorizadas")) for r in rows), Decimal("0"))
        total_money = sum((dec(r.get("importe_tm")) if r.get("importe_tm") not in (None, "") else dec(r.get("importe_total")) for r in rows), Decimal("0"))
        sections.append({"title": "VALORIZACIÓN DE PESCA - TONELADAS TM", "headers": ["Fecha", "Embarcación", "TM valorizadas", "Precio por TM", "Importe TM"],
            "rows": [[r.get("fecha_valorizacion", ""), names.get(r.get("embarcacion_id"), "(sin nombre)"), r.get("toneladas_valorizadas", "0"), r.get("precio_por_tm", "0"), f"{(dec(r.get('importe_tm')) if r.get('importe_tm') not in (None, '') else dec(r.get('importe_total'))):.2f}"] for r in rows],
            "totals": ["TOTAL TM", "", f"{total_qty:.3f}", "", f"{total_money:.2f}"]})
    if kind in ("valorizacion_kg", "valorizacion") or kind == "consolidado":
        rows = data.get("valorizaciones_kg", data.get("valorizaciones", []))
        total_qty = sum((dec(r.get("kilos_valorizados")) for r in rows), Decimal("0"))
        total_money = sum((dec(r.get("importe_kg")) for r in rows), Decimal("0"))
        sections.append({"title": "VALORIZACIÓN DE PESCA - KILOS KG", "headers": ["Fecha", "Embarcación", "KG valorizados", "Precio por KG", "Importe KG"],
            "rows": [[r.get("fecha_valorizacion", ""), names.get(r.get("embarcacion_id"), "(sin nombre)"), r.get("kilos_valorizados", "0"), r.get("precio_por_kg", "0"), f"{dec(r.get('importe_kg')):.2f}"] for r in rows],
            "totals": ["TOTAL KG", "", f"{total_qty:.3f}", "", f"{total_money:.2f}"]})
    if kind in ("hielo", "consolidado"):
        rows = data.get("hielo", [])
        total_money = sum((dec(r.get("importe_total")) for r in rows), Decimal("0"))
        sections.append({"title": "DESPACHO DE HIELO", "headers": ["Fecha", "Embarcación", "Cantidad", "Unidad", "Precio unitario", "Importe"],
            "rows": [[r.get("fecha", ""), names.get(r.get("embarcacion_id"), "(sin nombre)"), r.get("cantidad", "0"), r.get("unidad", ""), r.get("precio_unitario", "0"), r.get("importe_total", "0")] for r in rows],
            "totals": ["TOTAL", "", "", "", "", f"{total_money:.2f}"]})
    if kind in ("gastos_estadia", "consolidado"):
        rows = data.get("gastos_estadia", [])
        total = sum((dec(r.get("precio")) for r in rows), Decimal("0"))
        sections.append({"title": "GASTOS GENERALES DE ESTADÍA", "headers": ["Fecha", "Descripción", "Precio"],
            "rows": [[r.get("fecha", ""), r.get("descripcion", ""), f"{dec(r.get('precio')):.2f}"] for r in rows],
            "totals": ["TOTAL", "", f"{total:.2f}"]})
    count = sum(len(section["rows"]) for section in sections)
    return jsonify({"title": MODULES[kind][2], "desde": desde or "Inicio", "hasta": hasta or "Actualidad", "count": count, "sections": sections})


@api_bp.get("/reports/<kind>")
@login_required
def download_report(kind):
    if kind not in MODULES: return jsonify({"error": "Tipo de reporte no válido."}), 400
    desde = request.args.get("desde", "")
    hasta = request.args.get("hasta", "")
    vessel_id = request.args.get("embarcacion_id", "") or None
    if desde: desde = parse_date(desde, "fecha desde")
    if hasta: hasta = parse_date(hasta, "fecha hasta")
    if desde and hasta and desde > hasta: raise ValueError("La fecha desde no puede ser posterior a la fecha hasta.")
    repo = get_repository()
    data = collect_report(repo, kind, desde, hasta, vessel_id)
    tz = ZoneInfo(current_app.config["APP_TIMEZONE"])
    now = datetime.now(tz).strftime("%Y-%m-%d %H:%M")
    extension = request.args.get("formato", "pdf").lower()
    prefix = {"pesca":"PESCA", "valorizacion":"VALORIZACION", "valorizacion_tm":"VALORIZACION_TM", "valorizacion_kg":"VALORIZACION_KG", "hielo":"HIELO", "gastos_estadia":"GASTOS_ESTADIA", "consolidado":"CONSOLIDADO"}[kind]
    date_part = f"{desde or 'INICIO'}_AL_{hasta or 'ACTUALIDAD'}"
    if extension == "pdf":
        content = report_pdf(kind, data, desde, hasta, now)
        mime = "application/pdf"
        category = MODULES[kind][1]
    elif extension == "xlsx":
        content = report_excel(kind, data, desde, hasta, now)
        mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        category = MODULES[kind][1]
    else:
        return jsonify({"error": "Formato no válido."}), 400
    timestamp = datetime.now(tz).strftime("%H%M%S")
    filename = f"{prefix}_{date_part}_{timestamp}.{extension}"
    drive_file = repo.upload_report(filename, content, mime, datetime.now(tz).strftime("%Y"), category)
    response = make_response(send_file(BytesIO(content), mimetype=mime, as_attachment=True, download_name=filename))
    response.headers["X-Drive-File-Id"] = drive_file["id"]
    response.headers["X-Drive-File-Url"] = drive_file["url"]
    return response
