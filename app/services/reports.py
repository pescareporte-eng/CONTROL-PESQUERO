from __future__ import annotations

import io
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from xml.sax.saxutils import escape

from .validation import dec

MODULES = {
    "pesca": ("INGRESO_PESCA", "01_PESCA", "Reporte de ingreso de pesca"),
    "valorizacion": ("VALORIZACION_PESCA", "02_VALORIZACION", "Reporte general de valorizaciones"),
    "valorizacion_tm": ("VALORIZACION_PESCA", "02_VALORIZACION", "Reporte de valorización por TM"),
    "valorizacion_kg": ("VALORIZACION_PESCA", "02_VALORIZACION", "Reporte de valorización por KG"),
    "hielo": ("DESPACHO_HIELO", "03_HIELO", "Reporte de despacho de hielo"),
    "gastos_estadia": ("GASTOS_ESTADIA", "05_GASTOS_ESTADIA", "Resumen general de gastos de estadía"),
    "consolidado": (None, "04_CONSOLIDADO", "Reporte consolidado"),
}

def filtered(rows, desde, hasta, vessel_id=None):
    out = []
    for row in rows:
        row_date = row.get("fecha") or row.get("fecha_valorizacion", "")
        if desde and row_date < desde: continue
        if hasta and row_date > hasta: continue
        if vessel_id:
            rid = row.get("embarcacion_id")
            if rid is None: continue
            if rid != vessel_id: continue
        if row.get("estado", "ACTIVO") == "ANULADO": continue
        out.append(row)
    return out

def _valuation_rows(repo, desde, hasta, vessel_id=None):
    rows = filtered(repo.get_all("VALORIZACION_PESCA"), desde, hasta)
    landings = {x["id"]: x for x in repo.get_all("INGRESO_PESCA")}
    result = []
    for source in rows:
        landing = landings.get(source.get("ingreso_pesca_id"), {})
        if vessel_id and landing.get("embarcacion_id") != vessel_id:
            continue
        row = dict(source)
        row["embarcacion_id"] = landing.get("embarcacion_id", "")
        row["fecha_desembarque"] = landing.get("fecha", "")
        row["importe_tm"] = row.get("importe_tm") or row.get("importe_total", "0")
        row["importe_kg"] = row.get("importe_kg") or "0"
        result.append(row)
    return result


def collect_report(repo, kind, desde, hasta, vessel_id=None):
    vessels = {v["id"]: f"{v.get('nombre', '')} ({v.get('codigo', '')})".strip(" ()") for v in repo.get_all("EMBARCACIONES")}
    if kind == "pesca":
        rows = filtered(repo.get_all("INGRESO_PESCA"), desde, hasta, vessel_id)
        return {"vessels": vessels, "pesca": rows}
    if kind in ("valorizacion", "valorizacion_tm", "valorizacion_kg"):
        rows = _valuation_rows(repo, desde, hasta, vessel_id)
        tm_rows = [r for r in rows if dec(r.get("toneladas_valorizadas")) > 0]
        kg_rows = [r for r in rows if dec(r.get("kilos_valorizados")) > 0]
        if kind == "valorizacion_tm":
            return {"vessels": vessels, "valorizaciones": tm_rows, "valorizaciones_tm": tm_rows}
        if kind == "valorizacion_kg":
            return {"vessels": vessels, "valorizaciones": kg_rows, "valorizaciones_kg": kg_rows}
        return {"vessels": vessels, "valorizaciones": rows, "valorizaciones_tm": tm_rows, "valorizaciones_kg": kg_rows}
    if kind == "hielo":
        rows = filtered(repo.get_all("DESPACHO_HIELO"), desde, hasta, vessel_id)
        return {"vessels": vessels, "hielo": rows}
    if kind == "gastos_estadia":
        rows = filtered(repo.get_all("GASTOS_ESTADIA"), desde, hasta)
        return {"vessels": vessels, "gastos_estadia": rows}
    pesca = filtered(repo.get_all("INGRESO_PESCA"), desde, hasta, vessel_id)
    hielo = filtered(repo.get_all("DESPACHO_HIELO"), desde, hasta, vessel_id)
    val_data = collect_report(repo, "valorizacion", desde, hasta, vessel_id)
    stay_expenses = filtered(repo.get_all("GASTOS_ESTADIA"), desde, hasta)
    return {"vessels": vessels, "pesca": pesca, "valorizaciones": val_data["valorizaciones"],
            "valorizaciones_tm": val_data["valorizaciones_tm"], "valorizaciones_kg": val_data["valorizaciones_kg"],
            "hielo": hielo, "gastos_estadia": stay_expenses}

def report_pdf(kind, data, desde, hasta, generated_at):
    buf = io.BytesIO()
    # Todos los reportes PDF se generan en A4 vertical (portrait).
    # Los anchos se ajustan a los 186 mm disponibles entre márgenes.
    doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=12*mm, leftMargin=12*mm, topMargin=13*mm, bottomMargin=13*mm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("ReportTitle", parent=styles["Title"], textColor=colors.HexColor("#183B56"), fontSize=17, alignment=0, spaceAfter=5)
    small = ParagraphStyle("Small", parent=styles["Normal"], fontSize=8, leading=10)
    table_header = ParagraphStyle("ReportHeader", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=6.5, leading=7.4, textColor=colors.white, wordWrap="CJK")
    table_cell = ParagraphStyle("ReportCell", parent=styles["Normal"], fontName="Helvetica", fontSize=6.7, leading=8, textColor=colors.HexColor("#263F52"), wordWrap="CJK")
    story = [Paragraph("CONTROL PESQUERO", title_style), Paragraph(MODULES[kind][2], styles["Heading2"]),
             Paragraph(f"Periodo: {desde or 'Inicio'} al {hasta or 'Actualidad'} &nbsp;&nbsp; | &nbsp;&nbsp; Generado: {generated_at}", small), Spacer(1, 8)]
    vessel_names = data["vessels"]
    def section(title, headers, rows, totals=None, col_widths=None, wrap_cells=True):
        story.append(Paragraph(title, styles["Heading3"]))
        # En A4 vertical todas las celdas son párrafos para permitir ajuste
        # de texto y evitar que nombres, descripciones u observaciones se corten.
        header_cells = [Paragraph(escape(str(value or "")), table_header) for value in headers]
        body_rows = [[Paragraph(escape(str(value or "")), table_cell) for value in row] for row in rows]
        if not body_rows:
            body_rows = [[Paragraph("Sin registros para los filtros seleccionados", table_cell)] + [""] * (len(headers)-1)]
        if totals:
            body_rows.append([Paragraph(escape(str(value or "")), table_cell) for value in totals])
        table_data = [header_cells] + body_rows
        if col_widths is None:
            available_width = A4[0] - 24*mm
            col_widths = [available_width / len(headers)] * len(headers)
        t = Table(table_data, repeatRows=1, colWidths=col_widths, hAlign="LEFT", splitByRow=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#183B56")),
            ("TEXTCOLOR", (0,0), (-1,0), colors.white),
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE", (0,0), (-1,-1), 7),
            ("GRID", (0,0), (-1,-1), 0.35, colors.HexColor("#D8E1E8")),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#F3F6F8")]),
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
            ("LEFTPADDING", (0,0), (-1,-1), 5), ("RIGHTPADDING", (0,0), (-1,-1), 5),
            ("TOPPADDING", (0,0), (-1,-1), 5), ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ]))
        story.extend([t, Spacer(1, 10)])
    if kind in ("pesca", "consolidado"):
        rows = [[r.get("fecha",""), vessel_names.get(r.get("embarcacion_id"), "(sin nombre)"), r.get("toneladas_tm","0"), r.get("kilos_kg","0"), r.get("observaciones","")] for r in data.get("pesca", [])]
        total_tm = sum((dec(r.get("toneladas_tm")) for r in data.get("pesca", [])), Decimal("0"))
        total_kg = sum((dec(r.get("kilos_kg")) for r in data.get("pesca", [])), Decimal("0"))
        fishing_widths = [24*mm, 38*mm, 18*mm, 18*mm, 88*mm]
        section("INGRESO DE PESCA", ["Fecha", "Embarcación", "TM", "KG", "Observaciones"], rows,
                ["TOTAL", "", f"{total_tm:.3f}", f"{total_kg:.3f}", ""],
                col_widths=fishing_widths)
    if kind in ("valorizacion", "valorizacion_tm", "valorizacion_kg", "consolidado"):
        tm_rows = data.get("valorizaciones_tm", data.get("valorizaciones", []))
        kg_rows = data.get("valorizaciones_kg", data.get("valorizaciones", []))
        if kind in ("valorizacion", "valorizacion_tm", "consolidado"):
            rows_tm = [[r.get("fecha_valorizacion", ""), vessel_names.get(r.get("embarcacion_id"), "(sin nombre)"),
                        r.get("toneladas_valorizadas", "0"), f"S/ {dec(r.get('precio_por_tm')):,.2f}",
                        f"S/ {(dec(r.get('importe_tm')) if r.get('importe_tm') not in (None, '') else dec(r.get('importe_total'))):,.2f}"] for r in tm_rows]
            total_tm = sum((dec(r.get("toneladas_valorizadas")) for r in tm_rows), Decimal("0"))
            amount_tm = sum((dec(r.get("importe_tm")) if r.get("importe_tm") not in (None, "") else dec(r.get("importe_total")) for r in tm_rows), Decimal("0"))
            section("VALORIZACIÓN INDEPENDIENTE - TONELADAS TM", ["Fecha", "Embarcación", "TM valorizadas", "Precio/TM", "Importe TM"], rows_tm,
                    ["TOTAL TM", "", f"{total_tm:.3f}", "", f"S/ {amount_tm:,.2f}"],
                    col_widths=[23*mm, 43*mm, 30*mm, 33*mm, 57*mm])
        if kind in ("valorizacion", "valorizacion_kg", "consolidado"):
            rows_kg = [[r.get("fecha_valorizacion", ""), vessel_names.get(r.get("embarcacion_id"), "(sin nombre)"),
                        r.get("kilos_valorizados", "0"), f"S/ {dec(r.get('precio_por_kg')):,.2f}",
                        f"S/ {dec(r.get('importe_kg')):,.2f}"] for r in kg_rows]
            total_kg = sum((dec(r.get("kilos_valorizados")) for r in kg_rows), Decimal("0"))
            amount_kg = sum((dec(r.get("importe_kg")) for r in kg_rows), Decimal("0"))
            section("VALORIZACIÓN INDEPENDIENTE - KILOS KG", ["Fecha", "Embarcación", "KG valorizados", "Precio/KG", "Importe KG"], rows_kg,
                    ["TOTAL KG", "", f"{total_kg:.3f}", "", f"S/ {amount_kg:,.2f}"],
                    col_widths=[23*mm, 43*mm, 30*mm, 33*mm, 57*mm])
    if kind in ("hielo", "consolidado"):
        rows = [[r.get("fecha",""), vessel_names.get(r.get("embarcacion_id"), "(sin nombre)"), r.get("cantidad","0"), r.get("unidad",""), f"S/ {dec(r.get('precio_unitario')):,.2f}", f"S/ {dec(r.get('importe_total')):,.2f}"] for r in data.get("hielo", [])]
        total_money = sum((dec(r.get("importe_total")) for r in data.get("hielo", [])), Decimal("0"))
        section("DESPACHO DE HIELO", ["Fecha", "Embarcación", "Cantidad", "Unidad", "Precio unitario", "Importe"], rows,
                ["TOTAL", "", "", "", "", f"S/ {total_money:,.2f}"],
                col_widths=[22*mm, 39*mm, 23*mm, 20*mm, 34*mm, 48*mm])
    if kind in ("gastos_estadia", "consolidado"):
        expenses = data.get("gastos_estadia", [])
        rows = [[r.get("fecha", ""), r.get("descripcion", ""), f"S/ {dec(r.get('precio')):,.2f}"] for r in expenses]
        total = sum((dec(r.get("precio")) for r in expenses), Decimal("0"))
        section("GASTOS GENERALES DE ESTADÍA", ["Fecha", "Descripción", "Precio"], rows,
                ["TOTAL", "", f"S/ {total:,.2f}"],
                col_widths=[28*mm, 112*mm, 46*mm])
    doc.build(story)
    return buf.getvalue()

def report_excel(kind, data, desde, hasta, generated_at):
    wb = Workbook()
    ws = wb.active
    ws.title = "Resumen"
    ws.append(["CONTROL PESQUERO"])
    ws.append([MODULES[kind][2]])
    ws.append([f"Periodo: {desde or 'Inicio'} al {hasta or 'Actualidad'}"])
    ws.append([f"Generado: {generated_at}"])
    ws.append([])
    vessel_names = data["vessels"]
    sections = []
    if kind in ("pesca", "consolidado"):
        sections.append(("INGRESO_PESCA", ["Fecha", "Embarcación", "TM", "KG", "Observaciones"], [[r.get("fecha"), vessel_names.get(r.get("embarcacion_id"), ""), r.get("toneladas_tm"), r.get("kilos_kg"), r.get("observaciones")] for r in data.get("pesca", [])]))
    if kind in ("valorizacion", "valorizacion_tm", "valorizacion_kg", "consolidado"):
        tm_rows = data.get("valorizaciones_tm", data.get("valorizaciones", []))
        kg_rows = data.get("valorizaciones_kg", data.get("valorizaciones", []))
        if kind in ("valorizacion", "valorizacion_tm", "consolidado"):
            tm_values = [[r.get("fecha_valorizacion"), vessel_names.get(r.get("embarcacion_id"), ""), r.get("toneladas_valorizadas"), r.get("precio_por_tm"), r.get("importe_tm") or r.get("importe_total")] for r in tm_rows]
            sections.append(("VALORIZACION_TM", ["Fecha", "Embarcación", "TM valorizadas", "Precio/TM", "Importe TM"], tm_values))
        if kind in ("valorizacion", "valorizacion_kg", "consolidado"):
            kg_values = [[r.get("fecha_valorizacion"), vessel_names.get(r.get("embarcacion_id"), ""), r.get("kilos_valorizados"), r.get("precio_por_kg"), r.get("importe_kg")] for r in kg_rows]
            sections.append(("VALORIZACION_KG", ["Fecha", "Embarcación", "KG valorizados", "Precio/KG", "Importe KG"], kg_values))
    if kind in ("hielo", "consolidado"):
        sections.append(("DESPACHO_HIELO", ["Fecha", "Embarcación", "Cantidad", "Unidad", "Precio unitario", "Importe"], [[r.get("fecha"), vessel_names.get(r.get("embarcacion_id"), ""), r.get("cantidad"), r.get("unidad"), r.get("precio_unitario"), r.get("importe_total")] for r in data.get("hielo", [])]))
    if kind in ("gastos_estadia", "consolidado"):
        expenses = data.get("gastos_estadia", [])
        sections.append(("GASTOS_ESTADIA", ["Fecha", "Descripción", "Precio"], [[r.get("fecha"), r.get("descripcion"), r.get("precio")] for r in expenses]))
    for title, headers, rows in sections:
        ws.append([title]); ws.append(headers)
        for row in rows: ws.append(row)
        if title == "GASTOS_ESTADIA":
            total_stay = sum((dec(r.get("precio")) for r in data.get("gastos_estadia", [])), Decimal("0"))
            ws.append(["TOTAL", "", str(total_stay)])
        ws.append([])
    for cell in ws[1]:
        cell.font = Font(bold=True, size=16, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="183B56")
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            if cell.value in ("INGRESO_PESCA", "VALORIZACION_PESCA", "VALORIZACION_TM", "VALORIZACION_KG", "DESPACHO_HIELO", "GASTOS_ESTADIA"):
                cell.font = Font(bold=True, color="183B56", size=12)
            elif cell.row > 5:
                if cell.value in ("Fecha", "Embarcación", "TM", "KG", "Observaciones", "Fecha valorización", "TM valorizadas", "Precio/TM", "Importe TM", "KG valorizados", "Precio/KG", "Importe KG", "Importe total", "Importe", "Cantidad", "Unidad", "Precio unitario", "Descripción", "Precio"):
                    cell.font = Font(bold=True, color="FFFFFF")
                    cell.fill = PatternFill("solid", fgColor="2878A5")
    for col in ws.columns:
        letter = col[0].column_letter
        max_len = max((len(str(c.value or "")) for c in col), default=10)
        ws.column_dimensions[letter].width = min(max(max_len + 2, 12), 40)
    ws.freeze_panes = "A7"
    # Configurar también la impresión de Excel en A4 vertical.
    ws.page_setup.orientation = "portrait"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_margins.left = 0.30
    ws.page_margins.right = 0.30
    ws.page_margins.top = 0.45
    ws.page_margins.bottom = 0.45
    ws.print_area = f"A1:{ws.cell(row=ws.max_row, column=ws.max_column).coordinate}"
    buf = io.BytesIO(); wb.save(buf); return buf.getvalue()
