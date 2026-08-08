#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
  HIPOTECA INTERACTIVA - Streamlit App
================================================================================

Para ejecutar:
    streamlit run hipoteca_streamlit.py

Luego abre el navegador en la URL que te indique (normalmente http://localhost:8501)
"""

import math
import numpy as np
import matplotlib.pyplot as plt
import streamlit as st

st.set_page_config(page_title="Calculadora Hipotecaria", layout="wide")

# =============================================================================
#  FUNCIONES DE CALCULO
# =============================================================================

def cuota_hipoteca_fija(capital, tipo_anual, anos):
    if capital <= 0 or tipo_anual <= 0 or anos <= 0:
        return 0.0
    r = tipo_anual / 12
    n = anos * 12
    return capital * (r * (1 + r)**n) / ((1 + r)**n - 1)

def capital_maximo(cuota_mensual, tipo_anual, anos):
    """Dada una cuota maxima, calcula el capital maximo que se puede pedir."""
    if cuota_mensual <= 0 or tipo_anual <= 0 or anos <= 0:
        return 0.0
    r = tipo_anual / 12
    n = anos * 12
    return cuota_mensual * ((1 + r)**n - 1) / (r * (1 + r)**n)

def cuota_sin_interes(capital, anos):
    if capital <= 0 or anos <= 0:
        return 0.0
    return capital / (anos * 12)

def fmt(valor):
    return f"{valor:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")

def calcular_escenario(precio_piso, gastos, aportacion, cantidad_banco, tipo_interes,
                       plazo_banco, plazo_tio, ingresos, max_pct, otra_cuota, otra_resto,
                       num_partes, cancelar_madre, plazo_devol_madre):
    total_necesario = precio_piso + gastos
    mi_aportacion = aportacion + gastos
    dinero_disponible = mi_aportacion - (otra_resto if cancelar_madre else 0)
    financiacion = total_necesario - dinero_disponible

    cantidad_tio = financiacion - cantidad_banco
    if cantidad_tio < 0:
        cantidad_tio = 0
        cantidad_banco = financiacion

    cuota_banco = cuota_hipoteca_fija(cantidad_banco, tipo_interes, plazo_banco)
    cuota_tio = cuota_sin_interes(cantidad_tio, plazo_tio)
    mi_parte_otra = otra_cuota / num_partes

    if cancelar_madre:
        cuota_devol_madre = cuota_sin_interes(otra_resto, plazo_devol_madre)
        resta_otra = 0
    else:
        cuota_devol_madre = 0
        resta_otra = mi_parte_otra

    gasto_mensual = cuota_banco + cuota_tio
    max_bruto = ingresos * max_pct
    max_efectivo = max_bruto - resta_otra
    cumple = cuota_banco <= max_efectivo

    # Capital maximo que el banco podria darme con estos parametros
    capital_max_banco = capital_maximo(max_efectivo, tipo_interes, plazo_banco)

    meses_banco = plazo_banco * 12
    meses_tio = plazo_tio * 12
    meses_madre = plazo_devol_madre * 12 if cancelar_madre else 0

    puntos = sorted(set([0, meses_banco, meses_tio, meses_madre]))
    puntos = [p for p in puntos if p > 0]

    periodos = []
    inicio = 1
    for fin in puntos:
        if fin < inicio:
            continue
        b = cuota_banco if inicio <= meses_banco else 0
        t = cuota_tio if inicio <= meses_tio else 0
        m = cuota_devol_madre if (cancelar_madre and inicio <= meses_madre) else 0
        total = b + t - (m if cancelar_madre else 0)
        periodos.append({
            "inicio": inicio, "fin": fin,
            "banco": b, "tio": t, "madre": m, "total": total,
            "cancelar": cancelar_madre
        })
        inicio = fin + 1

    if inicio <= meses_banco:
        b = cuota_banco
        t = cuota_tio if inicio <= meses_tio else 0
        m = cuota_devol_madre if (cancelar_madre and inicio <= meses_madre) else 0
        total = b + t - (m if cancelar_madre else 0)
        periodos.append({
            "inicio": inicio, "fin": meses_banco,
            "banco": b, "tio": t, "madre": m, "total": total,
            "cancelar": cancelar_madre
        })

    return {
        "total_necesario": total_necesario,
        "mi_aportacion": mi_aportacion,
        "dinero_disponible": dinero_disponible,
        "financiacion": financiacion,
        "cantidad_banco": cantidad_banco,
        "cantidad_tio": cantidad_tio,
        "cuota_banco": cuota_banco,
        "cuota_tio": cuota_tio,
        "cuota_devol_madre": cuota_devol_madre,
        "gasto_mensual": gasto_mensual,
        "neto_mensual": gasto_mensual - cuota_devol_madre,
        "max_bruto": max_bruto,
        "max_efectivo": max_efectivo,
        "resta_otra": resta_otra,
        "capital_max_banco": capital_max_banco,
        "cumple": cumple,
        "periodos": periodos,
        "meses_banco": meses_banco,
        "cancelar_madre": cancelar_madre
    }


def generar_grafica(esc):
    meses_totales = esc["meses_banco"]
    x = np.arange(1, meses_totales + 1)
    y_banco = np.zeros(meses_totales)
    y_tio = np.zeros(meses_totales)
    y_madre = np.zeros(meses_totales)

    for p in esc["periodos"]:
        ini = p["inicio"] - 1
        fin = p["fin"]
        y_banco[ini:fin] = p["banco"]
        y_tio[ini:fin] = p["tio"]
        if esc["cancelar_madre"]:
            y_madre[ini:fin] = -p["madre"]

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.fill_between(x, 0, y_banco, color="#e74c3c", alpha=0.8, label="Banco")
    ax.fill_between(x, y_banco, y_banco + y_tio, color="#3498db", alpha=0.8, label="Tío")

    if esc["cancelar_madre"]:
        ax.fill_between(x, 0, y_madre, color="#2ecc71", alpha=0.8, label="Madre (devolución)")
        ax.axhline(y=0, color="black", linewidth=0.5)

    ax.axhline(y=esc["max_efectivo"], color="purple", linestyle="--", linewidth=2, label=f"Límite banco ({fmt(esc['max_efectivo'])})")

    ax.set_title("Evolución de la cuota mensual", fontsize=14, fontweight="bold")
    ax.set_xlabel("Mes")
    ax.set_ylabel("Cuota mensual (€)")
    ax.legend(loc="upper right")
    ax.set_xlim(1, meses_totales)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    return fig


# =============================================================================
#  INTERFAZ STREAMLIT
# =============================================================================

st.title("🏠 Calculadora de Hipotecas")
st.markdown("Modifica los parámetros en el panel de la izquierda y ve cómo evoluciona tu cuota en tiempo real.")

# Sidebar con todos los controles
with st.sidebar:
    st.header("⚙️ Parámetros")

    st.subheader("El piso")
    precio_piso = st.number_input("Precio del piso (€)", value=365_000, step=1_000)
    gastos = st.number_input("Gastos (notaría, registro, ITP...) (€)", value=8_500, step=500)
    aportacion = st.number_input("Tu aportación neta (€)", value=100_000, step=1_000)

    st.subheader("El banco")
    cantidad_banco = st.number_input("Cantidad que te da el banco (€)", value=200_000, step=1_000)
    tipo_interes = st.slider("Tipo de interés anual (%)", min_value=0.5, max_value=8.0, value=3.5, step=0.05) / 100
    plazo_banco = st.slider("Plazo banco (años)", min_value=20, max_value=40, value=30, step=1)

    st.subheader("El tío")
    plazo_tio = st.slider("Plazo tío (años)", min_value=5, max_value=20, value=10, step=1)

    st.subheader("Tus ingresos")
    ingresos = st.number_input("Ingresos netos mensuales (€)", value=2_999, step=50)
    max_pct = st.slider("Máxima cuota banco (% de ingresos)", min_value=20, max_value=60, value=35, step=5) / 100

    st.subheader("Otra hipoteca (madre/hermana)")
    st.markdown("*La paga tu madre, pero el banco te resta capacidad por ser titular.*")
    otra_cuota = st.number_input("Cuota total mensual (€)", value=529, step=10)
    otra_resto = st.number_input("Capital pendiente (€)", value=31_000, step=1_000)
    num_partes = st.number_input("Número de titulares", value=3, step=1, min_value=1)

    st.subheader("¿Cancelar la hipoteca de la madre?")
    cancelar_madre = st.checkbox("Sí, cancelarla (le doy 31.000 € y me los devuelve)", value=False)
    if cancelar_madre:
        plazo_devol_madre = st.slider("Plazo devolución madre (años)", min_value=3, max_value=15, value=10, step=1)
    else:
        plazo_devol_madre = 10

# Cálculo
esc = calcular_escenario(
    precio_piso, gastos, aportacion, cantidad_banco, tipo_interes,
    plazo_banco, plazo_tio, ingresos, max_pct, otra_cuota, otra_resto,
    num_partes, cancelar_madre, plazo_devol_madre
)

# =============================================================================
#  LAYOUT PRINCIPAL
# =============================================================================

# --- CUOTA TOTAL PRIMERO (lo que pide el usuario) ---
st.header("💶 Tu cuota mensual")

if esc["cancelar_madre"]:
    col_total, col_banco, col_tio, col_madre = st.columns(4)
    col_total.metric(
        "TOTAL NETO al mes",
        f"{fmt(esc['neto_mensual'])}",
        help="Lo que realmente sale de tu bolsillo: banco + tío - devolución de madre"
    )
    col_banco.metric("→ De eso, al BANCO", f"{fmt(esc['cuota_banco'])}")
    col_tio.metric("→ De eso, al TÍO", f"{fmt(esc['cuota_tio'])}")
    col_madre.metric("→ De eso, MADRE te devuelve", f"+{fmt(esc['cuota_devol_madre'])}")
else:
    col_total, col_banco, col_tio = st.columns(3)
    col_total.metric(
        "TOTAL al mes",
        f"{fmt(esc['gasto_mensual'])}",
        help="Lo que sale de tu bolsillo: banco + tío"
    )
    col_banco.metric("→ De eso, al BANCO", f"{fmt(esc['cuota_banco'])}")
    col_tio.metric("→ De eso, al TÍO", f"{fmt(esc['cuota_tio'])}")

st.divider()

# --- LÍMITE DEL BANCO Y CAPITAL MÁXIMO ---
st.header("🏦 Límite del banco")

lim1, lim2, lim3 = st.columns(3)
lim1.metric(f"Máx. cuota bruta ({max_pct*100:.0f}%)", f"{fmt(esc['max_bruto'])}/mes")

if not esc["cancelar_madre"]:
    lim2.metric("Resta otra hipoteca", f"-{fmt(esc['resta_otra'])}/mes", help="El banco te resta esta cantidad por ser titular de la otra hipoteca")
else:
    lim2.metric("Resta otra hipoteca", "0 €", help="Hipoteca cancelada, no hay resta")

lim3.metric("Capacidad EFECTIVA", f"{fmt(esc['max_efectivo'])}/mes", help="Cuota máxima que el banco te permitiría")

# Capital máximo que podría dar el banco
st.info(f"💡 **Con estos datos, el banco podría darte como máximo: {fmt(esc['capital_max_banco'])}** (cuota de {fmt(esc['max_efectivo'])}/mes a {tipo_interes*100:.2f}% en {plazo_banco} años)")

if esc["cumple"]:
    st.success(f"✅ La cuota del banco ({fmt(esc['cuota_banco'])}) CUMPLE el límite. Sobran {fmt(esc['max_efectivo'] - esc['cuota_banco'])} al mes.")
else:
    st.error(f"❌ La cuota del banco ({fmt(esc['cuota_banco'])}) SUPERA el límite. Faltan {fmt(esc['cuota_banco'] - esc['max_efectivo'])} al mes.")

st.divider()

# --- DATOS GENERALES ---
st.header("📊 Datos de la operación")
c1, c2, c3 = st.columns(3)
c1.metric("Total necesario", fmt(esc["total_necesario"]))
c2.metric("Tu aportación", fmt(esc["mi_aportacion"]))
c3.metric("Financiación total", fmt(esc["financiacion"]))

c4, c5, c6 = st.columns(3)
c4.metric("Banco te da", fmt(esc["cantidad_banco"]))
c5.metric("Tío te da", fmt(esc["cantidad_tio"]))
c6.metric("Entrada disponible", fmt(esc["dinero_disponible"]))

st.divider()

# --- GRÁFICA Y TABLA ---
col_izq, col_der = st.columns([1, 1])

with col_izq:
    st.subheader("📈 Evolución mensual")
    fig = generar_grafica(esc)
    st.pyplot(fig)

with col_der:
    st.subheader("📅 Periodos mensuales")
    periodos_data = []
    for p in esc["periodos"]:
        periodos_data.append({
            "Periodo": f"Mes {p['inicio']} - {p['fin']}",
            "Banco": fmt(p["banco"]),
            "Tío": fmt(p["tio"]),
            "Madre": f"+{fmt(p['madre'])} (dev.)" if (esc["cancelar_madre"] and p["madre"] > 0) else "---",
            "Total neto": fmt(p["total"])
        })
    st.table(periodos_data)

st.divider()
st.caption("App generada con Streamlit. Para usarla localmente: `streamlit run hipoteca_streamlit.py`")
