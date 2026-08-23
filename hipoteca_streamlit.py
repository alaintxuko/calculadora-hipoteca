#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
  HIPOTECA INTERACTIVA - Streamlit App con Supabase
================================================================================

Para ejecutar en local:
    1. Crea un archivo .streamlit/secrets.toml con:
       [supabase]
       url = "https://TU-PROJECT.supabase.co"
       key = "TU-ANON-KEY"
    2. streamlit run hipoteca_streamlit.py

Para desplegar en Streamlit Cloud:
    1. Sube a GitHub
    2. En Streamlit Cloud → Settings → Secrets, pega las credenciales de Supabase
    3. Deploy
"""

import math
import json
import os
from datetime import datetime
import numpy as np
import matplotlib.pyplot as plt
import streamlit as st

st.set_page_config(page_title="Calculadora Hipotecaria", layout="wide")

# =============================================================================
#  SUPABASE - Configuracion
# =============================================================================

SUPABASE_URL = "https://TU-PROJECT.supabase.co"
SUPABASE_KEY = "TU-ANON-KEY"


def get_supabase_client():
    try:
        from supabase import create_client
        try:
            url = st.secrets["supabase"]["url"]
            key = st.secrets["supabase"]["key"]
        except Exception:
            url = SUPABASE_URL
            key = SUPABASE_KEY
        url = url.replace("/rest/v1", "").rstrip("/")
        client = create_client(url, key)
        return client
    except Exception as e:
        st.error(f"Error conectando a Supabase: {e}")
        return None


def diagnosticar_supabase():
    try:
        from supabase import create_client
        try:
            url = st.secrets["supabase"]["url"].replace("/rest/v1", "").rstrip("/")
            key = st.secrets["supabase"]["key"]
            source = "Streamlit Secrets"
        except Exception:
            url = SUPABASE_URL.replace("/rest/v1", "").rstrip("/")
            key = SUPABASE_KEY
            source = "Variables del script"
        st.write(f"**URL:** `{url}`")
        st.write(f"**Key (primeros 20 chars):** `{key[:20]}...`")
        st.write(f"**Fuente:** {source}")
        client = create_client(url, key)
        try:
            response = client.rpc("get_schema", {}).execute()
            st.write(f"**Respuesta RPC:** {response}")
        except Exception as e:
            st.write(f"**RPC fallo (normal):** {e}")
        return client
    except Exception as e:
        st.error(f"Diagnostico fallo: {e}")
        return None


def existe_escenario(nombre):
    client = get_supabase_client()
    if client is None:
        return False
    try:
        response = client.table("escenarios").select("nombre").eq("nombre", nombre).execute()
        return len(response.data) > 0
    except Exception:
        return False


def eliminar_por_nombre(nombre):
    client = get_supabase_client()
    if client is None:
        return False
    try:
        client.table("escenarios").delete().eq("nombre", nombre).execute()
        return True
    except Exception:
        return False


def guardar_en_supabase(datos):
    client = get_supabase_client()
    if client is None:
        return False, "No se pudo conectar a Supabase. Revisa la URL y la API key."
    try:
        response = client.table("escenarios").insert(datos).execute()
        return True, None
    except Exception as e:
        error_str = str(e)
        if "PGRST125" in error_str or "Invalid path" in error_str:
            return False, "PGRST125: PostgREST no encuentra la tabla. Posibles causas: (1) La tabla 'escenarios' no existe en el schema 'public', (2) La URL del proyecto es incorrecta, (3) Hay un problema con la API key."
        elif "relation" in error_str.lower() and "does not exist" in error_str.lower():
            return False, "La tabla 'escenarios' no existe en Supabase. Creala primero."
        else:
            return False, f"Error de Supabase: {error_str}"


def cargar_desde_supabase():
    client = get_supabase_client()
    if client is None:
        return []
    try:
        response = client.table("escenarios").select("*").order("created_at", desc=True).execute()
        return response.data
    except Exception as e:
        error_str = str(e)
        if "PGRST125" in error_str or "Invalid path" in error_str:
            st.error("Supabase: RLS esta activado sin politicas. Desactivalo en Table Editor → escenarios → toggle RLS.")
        elif "relation" in error_str.lower() and "does not exist" in error_str.lower():
            st.error("Supabase: La tabla 'escenarios' no existe. Creala primero.")
        else:
            st.error(f"Error cargando desde Supabase: {error_str}")
        return []


def eliminar_de_supabase(nombre):
    client = get_supabase_client()
    if client is None:
        return False
    try:
        client.table("escenarios").delete().eq("nombre", nombre).execute()
        return True
    except Exception as e:
        st.error(f"Error eliminando de Supabase: {e}")
        return False


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


def calcular_escenario(precio_piso, gastos, aportacion, cantidad_banco, tipo_interes_base,
                       plazo_banco, plazo_tio, ingresos, max_pct,
                       otra_cuota, otra_resto, num_partes,
                       cancelar_madre, plazo_devol_madre,
                       bonif_nomina_activa, bonif_nomina_pct,
                       bonif_hogar_activa, bonif_hogar_pct, bonif_hogar_coste,
                       bonif_vida_activa, bonif_vida_pct, bonif_vida_coste,
                       bonif_otro_activa, bonif_otro_pct, bonif_otro_coste):

    descuento_total = 0.0
    if bonif_nomina_activa:
        descuento_total += bonif_nomina_pct
    if bonif_hogar_activa:
        descuento_total += bonif_hogar_pct
    if bonif_vida_activa:
        descuento_total += bonif_vida_pct
    if bonif_otro_activa:
        descuento_total += bonif_otro_pct

    tipo_interes = max(0.0, tipo_interes_base - descuento_total)

    coste_seguros_mes = 0.0
    if bonif_hogar_activa:
        coste_seguros_mes += bonif_hogar_coste
    if bonif_vida_activa:
        coste_seguros_mes += bonif_vida_coste
    if bonif_otro_activa:
        coste_seguros_mes += bonif_otro_coste

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

    gasto_mensual = cuota_banco + cuota_tio + coste_seguros_mes
    max_bruto = ingresos * max_pct
    max_efectivo = max_bruto - resta_otra
    cumple = cuota_banco <= max_efectivo

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
        total = b + t - (m if cancelar_madre else 0) + coste_seguros_mes
        periodos.append({
            "inicio": inicio, "fin": fin,
            "banco": b, "tio": t, "madre": m,
            "seguros": coste_seguros_mes,
            "total": total,
            "cancelar": cancelar_madre
        })
        inicio = fin + 1

    if inicio <= meses_banco:
        b = cuota_banco
        t = cuota_tio if inicio <= meses_tio else 0
        m = cuota_devol_madre if (cancelar_madre and inicio <= meses_madre) else 0
        total = b + t - (m if cancelar_madre else 0) + coste_seguros_mes
        periodos.append({
            "inicio": inicio, "fin": meses_banco,
            "banco": b, "tio": t, "madre": m,
            "seguros": coste_seguros_mes,
            "total": total,
            "cancelar": cancelar_madre
        })

    total_pagado_banco = cuota_banco * meses_banco
    intereses_totales_banco = total_pagado_banco - cantidad_banco
    total_pagado_tio = cuota_tio * meses_tio
    total_pagado_seguros = coste_seguros_mes * meses_banco

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
        "coste_seguros_mes": coste_seguros_mes,
        "gasto_mensual": gasto_mensual,
        "neto_mensual": gasto_mensual - cuota_devol_madre,
        "max_bruto": max_bruto,
        "max_efectivo": max_efectivo,
        "resta_otra": resta_otra,
        "capital_max_banco": capital_max_banco,
        "cumple": cumple,
        "periodos": periodos,
        "meses_banco": meses_banco,
        "meses_tio": meses_tio,
        "cancelar_madre": cancelar_madre,
        "tipo_interes_base": tipo_interes_base,
        "tipo_interes_bonif": tipo_interes,
        "descuento_total": descuento_total,
        "total_pagado_banco": total_pagado_banco,
        "intereses_totales_banco": intereses_totales_banco,
        "total_pagado_tio": total_pagado_tio,
        "total_pagado_seguros": total_pagado_seguros,
    }


def capital_pendiente(capital_inicial, tipo_anual, anos, meses_pagados):
    """Calcula el capital pendiente despues de k meses pagados."""
    if capital_inicial <= 0 or tipo_anual <= 0 or anos <= 0 or meses_pagados <= 0:
        return capital_inicial
    r = tipo_anual / 12
    n = anos * 12
    cuota = capital_inicial * (r * (1 + r)**n) / ((1 + r)**n - 1)
    # Formula del capital pendiente despues de k pagos
    pendiente = capital_inicial * (1 + r)**meses_pagados - cuota * ((1 + r)**meses_pagados - 1) / r
    return max(0.0, pendiente)


def generar_grafica(esc):
    meses_totales = esc["meses_banco"]
    x = np.arange(1, meses_totales + 1)
    y_banco = np.zeros(meses_totales)
    y_tio = np.zeros(meses_totales)
    y_madre = np.zeros(meses_totales)
    y_seguros = np.zeros(meses_totales)

    for p in esc["periodos"]:
        ini = p["inicio"] - 1
        fin = p["fin"]
        y_banco[ini:fin] = p["banco"]
        y_tio[ini:fin] = p["tio"]
        y_seguros[ini:fin] = p["seguros"]
        if esc["cancelar_madre"]:
            y_madre[ini:fin] = -p["madre"]

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.fill_between(x, 0, y_banco, color="#e74c3c", alpha=0.8, label="Banco")
    ax.fill_between(x, y_banco, y_banco + y_tio, color="#3498db", alpha=0.8, label="Tio")

    if esc["coste_seguros_mes"] > 0:
        ax.fill_between(x, y_banco + y_tio, y_banco + y_tio + y_seguros, color="#9b59b6", alpha=0.8, label="Seguros")

    if esc["cancelar_madre"]:
        ax.fill_between(x, 0, y_madre, color="#2ecc71", alpha=0.8, label="Madre (devolucion)")
        ax.axhline(y=0, color="black", linewidth=0.5)

    ax.axhline(y=esc["max_efectivo"], color="purple", linestyle="--", linewidth=2, label="Limite banco")

    ax.set_title("Evolucion de la cuota mensual", fontsize=14, fontweight="bold")
    ax.set_xlabel("Mes")
    ax.set_ylabel("Cuota mensual (€)")
    ax.legend(loc="upper right")
    ax.set_xlim(1, meses_totales)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    return fig


# =============================================================================
#  VALORES POR DEFECTO
# =============================================================================

DEFAULTS = {
    "precio_piso": 365000,
    "gastos": 8500,
    "aportacion": 100000,
    "cantidad_banco": 200000,
    "tipo_interes": 3.5,
    "plazo_banco": 30,
    "plazo_tio": 10,
    "ingresos": 2999,
    "max_pct": 35,
    "otra_cuota": 529,
    "otra_resto": 31000,
    "num_partes": 3,
    "cancelar_madre": False,
    "plazo_devol_madre": 10,
    "bonif_nomina_activa": False,
    "bonif_nomina_pct": 0.30,
    "bonif_hogar_activa": False,
    "bonif_hogar_pct": 0.10,
    "bonif_hogar_coste": 300.0,
    "bonif_vida_activa": False,
    "bonif_vida_pct": 0.10,
    "bonif_vida_coste": 180.0,
    "bonif_otro_activa": False,
    "bonif_otro_pct": 0.05,
    "bonif_otro_coste": 0.0,
}


# =============================================================================
#  INICIALIZAR SESSION STATE (una sola vez)
# =============================================================================

for key, val in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = val

if "pagina" not in st.session_state:
    st.session_state.pagina = "Calcular"

if "cargar_nombre" not in st.session_state:
    st.session_state.cargar_nombre = None


# =============================================================================
#  CARGAR ESCENARIO -> ESCRIBIR EN SESSION_STATE
# =============================================================================

if st.session_state.cargar_nombre is not None:
    try:
        records = cargar_desde_supabase()
        for r in records:
            if r.get("nombre") == st.session_state.cargar_nombre:
                for key in DEFAULTS:
                    if key in r:
                        val = r[key]
                        if key in ["cancelar_madre", "bonif_nomina_activa", "bonif_hogar_activa",
                                   "bonif_vida_activa", "bonif_otro_activa"]:
                            st.session_state[key] = bool(val)
                        elif key in ["precio_piso", "gastos", "aportacion", "cantidad_banco",
                                     "plazo_banco", "plazo_tio", "ingresos", "max_pct",
                                     "otra_cuota", "otra_resto", "num_partes", "plazo_devol_madre"]:
                            st.session_state[key] = int(val)
                        elif key in ["bonif_hogar_coste", "bonif_vida_coste", "bonif_otro_coste"]:
                            # En DB se guardan mensuales, en session_state anuales
                            st.session_state[key] = float(val) * 12
                        else:
                            st.session_state[key] = float(val)
                break
    except Exception:
        pass
    st.session_state.cargar_nombre = None
    st.toast("Escenario cargado", icon="✅")
    st.rerun()


# =============================================================================
#  NAVEGACION
# =============================================================================

st.sidebar.title("🧭 Navegacion")
pagina = st.sidebar.radio("Ir a", ["Calcular", "Analisis", "Amortizacion", "Mis escenarios"],
    index=0 if st.session_state.pagina == "Calcular" else (1 if st.session_state.pagina == "Analisis" else (2 if st.session_state.pagina == "Amortizacion" else 3)),
    key="nav_pagina")

if pagina != st.session_state.pagina:
    st.session_state.pagina = pagina


# =============================================================================
#  SIDEBAR - INPUTS GLOBALES
#  Usamos key en los widgets, SIN value. Streamlit lee/escribe session_state
#  automaticamente. Inicializamos arriba para que los widgets tengan valor.
# =============================================================================

with st.sidebar:
    st.header("⚙️ Parametros")

    st.subheader("El piso")
    st.number_input("Precio del piso (€)", step=1000, key="precio_piso")
    st.number_input("Gastos (notaria, registro, ITP...) (€)", step=500, key="gastos")
    st.number_input("Tu aportacion neta (€)", step=1000, key="aportacion")

    st.subheader("El banco")
    st.number_input("Cantidad que te da el banco (€)", step=1000, key="cantidad_banco")
    st.slider("Tipo de interes anual SIN bonificar (%)", min_value=1.5, max_value=6.0, step=0.01, key="tipo_interes")
    st.slider("Plazo banco (anos)", min_value=20, max_value=40, step=1, key="plazo_banco")

    st.subheader("El tio")
    st.slider("Plazo tio (anos)", min_value=5, max_value=20, step=1, key="plazo_tio")

    st.subheader("Tus ingresos")
    st.number_input("Ingresos netos mensuales (€)", step=50, key="ingresos")
    st.slider("Maxima cuota banco (% de ingresos)", min_value=30, max_value=50, step=1, key="max_pct")

    st.subheader("Otra hipoteca (madre/hermana)")
    st.markdown("*La paga tu madre, pero el banco te resta capacidad por ser titular.*")
    st.number_input("Cuota total mensual (€)", step=10, key="otra_cuota")
    st.number_input("Capital pendiente (€)", step=1000, key="otra_resto")
    st.number_input("Numero de titulares", step=1, min_value=1, key="num_partes")

    st.subheader("¿Cancelar la hipoteca de la madre?")
    st.checkbox("Si, cancelarla (le doy el capital pendiente y me lo devuelve)", key="cancelar_madre")
    if st.session_state["cancelar_madre"]:
        st.slider("Plazo devolucion madre (anos)", min_value=3, max_value=15, step=1, key="plazo_devol_madre")

    st.subheader("🎁 Bonificaciones")
    st.markdown("*Marca las que apliques. Los costes se introducen en €/ano.*")

    st.checkbox("📋 Nomina", key="bonif_nomina_activa")
    if st.session_state["bonif_nomina_activa"]:
        st.number_input("Bonificacion nomina (%)", step=0.01, min_value=0.0, max_value=2.0, key="bonif_nomina_pct")

    st.checkbox("🏠 Seguro de hogar", key="bonif_hogar_activa")
    if st.session_state["bonif_hogar_activa"]:
        st.number_input("Bonificacion hogar (%)", step=0.01, min_value=0.0, max_value=2.0, key="bonif_hogar_pct")
        st.number_input("Coste seguro hogar (€/ano)", step=12.0, min_value=0.0, key="bonif_hogar_coste")

    st.checkbox("❤️ Seguro de vida", key="bonif_vida_activa")
    if st.session_state["bonif_vida_activa"]:
        st.number_input("Bonificacion vida (%)", step=0.01, min_value=0.0, max_value=2.0, key="bonif_vida_pct")
        st.number_input("Coste seguro vida (€/ano)", step=12.0, min_value=0.0, key="bonif_vida_coste")

    st.checkbox("➕ Otro adicional", key="bonif_otro_activa")
    if st.session_state["bonif_otro_activa"]:
        st.number_input("Bonificacion otro (%)", step=0.01, min_value=0.0, max_value=2.0, key="bonif_otro_pct")
        st.number_input("Coste otro (€/ano)", step=12.0, min_value=0.0, key="bonif_otro_coste")


# =============================================================================
#  FUNCION AUXILIAR: leer parametros normalizados desde session_state
# =============================================================================

def get_params():
    """Lee todos los parametros de session_state y los normaliza para calcular_escenario."""
    s = st.session_state
    return {
        "precio_piso": int(s["precio_piso"]),
        "gastos": int(s["gastos"]),
        "aportacion": int(s["aportacion"]),
        "cantidad_banco": int(s["cantidad_banco"]),
        "tipo_interes_base": float(s["tipo_interes"]) / 100,
        "plazo_banco": int(s["plazo_banco"]),
        "plazo_tio": int(s["plazo_tio"]),
        "ingresos": int(s["ingresos"]),
        "max_pct": int(s["max_pct"]) / 100,
        "otra_cuota": int(s["otra_cuota"]),
        "otra_resto": int(s["otra_resto"]),
        "num_partes": int(s["num_partes"]),
        "cancelar_madre": bool(s["cancelar_madre"]),
        "plazo_devol_madre": int(s.get("plazo_devol_madre", 10)),
        "bonif_nomina_activa": bool(s["bonif_nomina_activa"]),
        "bonif_nomina_pct": float(s["bonif_nomina_pct"]) / 100,
        "bonif_hogar_activa": bool(s["bonif_hogar_activa"]),
        "bonif_hogar_pct": float(s["bonif_hogar_pct"]) / 100,
        "bonif_hogar_coste": float(s["bonif_hogar_coste"]) / 12,
        "bonif_vida_activa": bool(s["bonif_vida_activa"]),
        "bonif_vida_pct": float(s["bonif_vida_pct"]) / 100,
        "bonif_vida_coste": float(s["bonif_vida_coste"]) / 12,
        "bonif_otro_activa": bool(s["bonif_otro_activa"]),
        "bonif_otro_pct": float(s["bonif_otro_pct"]) / 100,
        "bonif_otro_coste": float(s["bonif_otro_coste"]) / 12,
    }


# =============================================================================
#  CALCULAR ESCENARIO (siempre, para todas las paginas)
# =============================================================================

p = get_params()

esc = calcular_escenario(
    p["precio_piso"], p["gastos"], p["aportacion"], p["cantidad_banco"],
    p["tipo_interes_base"], p["plazo_banco"], p["plazo_tio"],
    p["ingresos"], p["max_pct"],
    p["otra_cuota"], p["otra_resto"], p["num_partes"],
    p["cancelar_madre"], p["plazo_devol_madre"],
    p["bonif_nomina_activa"], p["bonif_nomina_pct"],
    p["bonif_hogar_activa"], p["bonif_hogar_pct"], p["bonif_hogar_coste"],
    p["bonif_vida_activa"], p["bonif_vida_pct"], p["bonif_vida_coste"],
    p["bonif_otro_activa"], p["bonif_otro_pct"], p["bonif_otro_coste"]
)


# =============================================================================
#  PAGINA: CALCULAR
# =============================================================================

if st.session_state.pagina == "Calcular":

    st.title("🏠 Calculadora de Hipotecas")
    st.markdown("Modifica los parametros en el panel de la izquierda y ve como evoluciona tu cuota en tiempo real.")

    # --- Interes aplicado ---
    if esc["descuento_total"] > 0:
        st.info(f"📉 Interes base: **{p['tipo_interes_base']*100:.2f}%** → Bonificado: **{esc['tipo_interes_bonif']*100:.2f}%** (descuento total: {esc['descuento_total']*100:.2f}%)")
    else:
        st.info(f"📉 Interes aplicado: **{esc['tipo_interes_bonif']*100:.2f}%** (sin bonificaciones)")

    # --- Cuota mensual ---
    st.header("💶 Tu cuota mensual")

    if esc["cancelar_madre"]:
        cols = st.columns(5)
        cols[0].metric("TOTAL NETO al mes", fmt(esc["neto_mensual"]), help="Banco + Tio + Seguros - Devolucion madre")
        cols[1].metric("→ BANCO", fmt(esc["cuota_banco"]))
        cols[2].metric("→ TIO", fmt(esc["cuota_tio"]))
        cols[3].metric("→ SEGUROS", fmt(esc["coste_seguros_mes"]) if esc["coste_seguros_mes"] > 0 else "0,00 €")
        cols[4].metric("→ MADRE devuelve", f"+{fmt(esc['cuota_devol_madre'])}")
    else:
        cols = st.columns(4)
        cols[0].metric("TOTAL al mes", fmt(esc["gasto_mensual"]), help="Banco + Tio + Seguros")
        cols[1].metric("→ BANCO", fmt(esc["cuota_banco"]))
        cols[2].metric("→ TIO", fmt(esc["cuota_tio"]))
        cols[3].metric("→ SEGUROS", fmt(esc["coste_seguros_mes"]) if esc["coste_seguros_mes"] > 0 else "0,00 €")

    st.divider()

    # --- Limite del banco ---
    st.header("🏦 Limite del banco")
    lim1, lim2, lim3 = st.columns(3)
    lim1.metric(f"Max. cuota bruta ({p['max_pct']*100:.0f}%)", f"{fmt(esc['max_bruto'])}/mes")
    if not esc["cancelar_madre"]:
        lim2.metric("Resta otra hipoteca", f"-{fmt(esc['resta_otra'])}/mes", help="El banco te resta esta cantidad por ser titular")
    else:
        lim2.metric("Resta otra hipoteca", "0 €", help="Hipoteca cancelada, no hay resta")
    lim3.metric("Capacidad EFECTIVA", f"{fmt(esc['max_efectivo'])}/mes", help="Cuota maxima que el banco te permitiria")

    st.info(f"💡 **Con estos datos, el banco podria darte como maximo: {fmt(esc['capital_max_banco'])}** (cuota de {fmt(esc['max_efectivo'])}/mes a {esc['tipo_interes_bonif']*100:.2f}% en {p['plazo_banco']} anos)")

    if esc["cumple"]:
        st.success(f"✅ La cuota del banco ({fmt(esc['cuota_banco'])}) CUMPLE el limite. Sobran {fmt(esc['max_efectivo'] - esc['cuota_banco'])} al mes.")
    else:
        st.error(f"❌ La cuota del banco ({fmt(esc['cuota_banco'])}) SUPERA el limite. Faltan {fmt(esc['cuota_banco'] - esc['max_efectivo'])} al mes.")

    st.divider()

    # --- Datos de la operacion ---
    st.header("📊 Datos de la operacion")
    c1, c2, c3 = st.columns(3)
    c1.metric("Total necesario", fmt(esc["total_necesario"]))
    c2.metric("Tu aportacion", fmt(esc["mi_aportacion"]))
    c3.metric("Financiacion total", fmt(esc["financiacion"]))
    c4, c5, c6 = st.columns(3)
    c4.metric("Banco te da", fmt(esc["cantidad_banco"]))
    c5.metric("Tio te da", fmt(esc["cantidad_tio"]))
    c6.metric("Entrada disponible", fmt(esc["dinero_disponible"]))

    st.subheader("💰 Totales a pagar")
    t1, t2, t3, t4 = st.columns(4)
    t1.metric("Pedido al banco", fmt(esc["cantidad_banco"]))
    t2.metric("Pagado al banco", fmt(esc["total_pagado_banco"]))
    t3.metric("Intereses banco", fmt(esc["intereses_totales_banco"]), help="Diferencia entre lo pagado y lo pedido")
    t4.metric("Pagado al tio", fmt(esc["total_pagado_tio"]))

    st.divider()

    # --- Grafica y periodos ---
    col_izq, col_der = st.columns([1, 1])
    with col_izq:
        st.subheader("📈 Evolucion mensual")
        fig = generar_grafica(esc)
        st.pyplot(fig)

    with col_der:
        st.subheader("📅 Periodos mensuales")
        periodos_data = []
        for per in esc["periodos"]:
            periodos_data.append({
                "Periodo": f"Mes {per['inicio']} - {per['fin']}",
                "Banco": fmt(per["banco"]),
                "Tio": fmt(per["tio"]),
                "Seguros": fmt(per["seguros"]) if per["seguros"] > 0 else "---",
                "Madre": f"+{fmt(per['madre'])} (dev.)" if (esc["cancelar_madre"] and per["madre"] > 0) else "---",
                "Total neto": fmt(per["total"])
            })
        st.table(periodos_data)

    st.divider()

    # --- Guardar en Supabase ---
    st.header("💾 Guardar escenario")

    with st.expander("🔧 Diagnostico de conexion a Supabase"):
        diagnosticar_supabase()

    nombre_guardar = st.text_input("Nombre del escenario", placeholder="Ej: Oferta Santander marzo")

    nombre_limpio = nombre_guardar.strip()
    ya_existe = existe_escenario(nombre_limpio) if nombre_limpio else False

    if ya_existe:
        st.warning(f"⚠️ Ya existe un escenario llamado '{nombre_limpio}'. Pulsa Guardar para sobreescribirlo.")

    if st.button("💾 Guardar en Supabase", type="primary"):
        if nombre_limpio == "":
            st.error("Introduce un nombre para guardar")
        else:
            if ya_existe:
                eliminar_por_nombre(nombre_limpio)

            datos_guardar = {
                "nombre": nombre_limpio,
                "precio_piso": p["precio_piso"], "gastos": p["gastos"], "aportacion": p["aportacion"],
                "cantidad_banco": p["cantidad_banco"], "cantidad_tio": esc["cantidad_tio"],
                "tipo_interes": round(p["tipo_interes_base"] * 100, 2),
                "plazo_banco": p["plazo_banco"], "plazo_tio": p["plazo_tio"],
                "ingresos": p["ingresos"], "max_pct": int(p["max_pct"] * 100),
                "otra_cuota": p["otra_cuota"], "otra_resto": p["otra_resto"], "num_partes": p["num_partes"],
                "cancelar_madre": p["cancelar_madre"], "plazo_devol_madre": p["plazo_devol_madre"],
                "bonif_nomina_activa": p["bonif_nomina_activa"], "bonif_nomina_pct": round(p["bonif_nomina_pct"] * 100, 2),
                "bonif_hogar_activa": p["bonif_hogar_activa"], "bonif_hogar_pct": round(p["bonif_hogar_pct"] * 100, 2), "bonif_hogar_coste": round(p["bonif_hogar_coste"], 2),
                "bonif_vida_activa": p["bonif_vida_activa"], "bonif_vida_pct": round(p["bonif_vida_pct"] * 100, 2), "bonif_vida_coste": round(p["bonif_vida_coste"], 2),
                "bonif_otro_activa": p["bonif_otro_activa"], "bonif_otro_pct": round(p["bonif_otro_pct"] * 100, 2), "bonif_otro_coste": round(p["bonif_otro_coste"], 2),
                "cuota_banco": round(esc["cuota_banco"], 2), "cuota_tio": round(esc["cuota_tio"], 2),
                "coste_seguros": round(esc["coste_seguros_mes"], 2), "total_mensual": round(esc["gasto_mensual"], 2),
                "intereses_totales": round(esc["intereses_totales_banco"], 2),
                "total_pagado_banco": round(esc["total_pagado_banco"], 2),
                "total_pagado_tio": round(esc["total_pagado_tio"], 2),
                "cumple": esc["cumple"],
            }
            ok, error_msg = guardar_en_supabase(datos_guardar)
            if ok:
                if ya_existe:
                    st.success(f"Escenario '{nombre_limpio}' sobreescrito en Supabase ✅")
                else:
                    st.success(f"Escenario '{nombre_limpio}' guardado en Supabase ✅")
            else:
                st.error(f"No se pudo guardar en Supabase: {error_msg}")
                st.warning("Puedes copiar los datos manualmente desde abajo.")

    with st.expander("📋 Ver datos como JSON (copia manual si Supabase falla)"):
        datos_json = {
            "nombre": nombre_guardar if nombre_guardar else "sin_nombre",
            "precio_piso": p["precio_piso"], "gastos": p["gastos"], "aportacion": p["aportacion"],
            "cantidad_banco": p["cantidad_banco"], "tipo_interes": round(p["tipo_interes_base"] * 100, 2),
            "plazo_banco": p["plazo_banco"], "plazo_tio": p["plazo_tio"],
            "ingresos": p["ingresos"], "max_pct": int(p["max_pct"] * 100),
            "otra_cuota": p["otra_cuota"], "otra_resto": p["otra_resto"], "num_partes": p["num_partes"],
            "cancelar_madre": p["cancelar_madre"], "plazo_devol_madre": p["plazo_devol_madre"],
            "bonif_nomina_activa": p["bonif_nomina_activa"], "bonif_nomina_pct": round(p["bonif_nomina_pct"] * 100, 2),
            "bonif_hogar_activa": p["bonif_hogar_activa"], "bonif_hogar_pct": round(p["bonif_hogar_pct"] * 100, 2), "bonif_hogar_coste": round(p["bonif_hogar_coste"], 2),
            "bonif_vida_activa": p["bonif_vida_activa"], "bonif_vida_pct": round(p["bonif_vida_pct"] * 100, 2), "bonif_vida_coste": round(p["bonif_vida_coste"], 2),
            "bonif_otro_activa": p["bonif_otro_activa"], "bonif_otro_pct": round(p["bonif_otro_pct"] * 100, 2), "bonif_otro_coste": round(p["bonif_otro_coste"], 2),
            "cuota_banco": round(esc["cuota_banco"], 2), "cuota_tio": round(esc["cuota_tio"], 2),
            "coste_seguros": round(esc["coste_seguros_mes"], 2), "total_mensual": round(esc["gasto_mensual"], 2),
            "cumple": esc["cumple"],
        }
        st.code(json.dumps(datos_json, indent=2, ensure_ascii=False), language="json")

    st.divider()

    # --- ANALISIS DE BONIFICACIONES (al final) ---
    if esc["descuento_total"] > 0:
        st.header("🎁 Analisis de bonificaciones")
        st.markdown("Para cada bonificacion activa: cuanto pagas al mes por el producto y cuanto ahorras en la cuota del banco.")

        bonif_data = []
        bonif_items = [
            ("Nomina", p["bonif_nomina_activa"], p["bonif_nomina_pct"], 0),
            ("Seguro de hogar", p["bonif_hogar_activa"], p["bonif_hogar_pct"], p["bonif_hogar_coste"]),
            ("Seguro de vida", p["bonif_vida_activa"], p["bonif_vida_pct"], p["bonif_vida_coste"]),
            ("Otro adicional", p["bonif_otro_activa"], p["bonif_otro_pct"], p["bonif_otro_coste"]),
        ]

        for nombre, activa, pct, coste_mes in bonif_items:
            if activa:
                descuento_sin_esta = esc["descuento_total"] - pct
                tipo_sin_esta = max(0.0, p["tipo_interes_base"] - descuento_sin_esta)
                cuota_sin_esta = cuota_hipoteca_fija(esc["cantidad_banco"], tipo_sin_esta, p["plazo_banco"])
                ahorro_mes = cuota_sin_esta - esc["cuota_banco"]
                balance_mes = ahorro_mes - coste_mes

                bonif_data.append({
                    "Bonificacion": nombre,
                    "Pagas/mes": fmt(coste_mes),
                    "Ahorras/mes": fmt(ahorro_mes),
                    "Balance neto/mes": fmt(balance_mes),
                })

        if bonif_data:
            st.table(bonif_data)

            total_coste = sum([coste for _, activa, _, coste in bonif_items if activa])
            cuota_sin_ninguna = cuota_hipoteca_fija(esc["cantidad_banco"], p["tipo_interes_base"], p["plazo_banco"])
            ahorro_total = cuota_sin_ninguna - esc["cuota_banco"]
            balance_total = ahorro_total - total_coste

            c1, c2, c3 = st.columns(3)
            c1.metric("Pagas/mes en bonificaciones", fmt(total_coste))
            c2.metric("Ahorras/mes en cuota", fmt(ahorro_total))
            c3.metric("Balance neto/mes", fmt(balance_total), help="Ahorro en cuota menos coste de seguros")
        else:
            st.info("No hay bonificaciones activas.")

        st.divider()

    st.caption("App generada con Streamlit + Supabase.")


# =============================================================================
#  PAGINA: ANALISIS
# =============================================================================

elif st.session_state.pagina == "Analisis":

    st.title("📊 Analisis de sensibilidad")
    st.markdown("Elige un parametro y observa como varia tu cuota mensual inicial. **Todos los demas parametros mantienen los valores actuales del sidebar.**")

    col_param, col_range = st.columns([1, 2])

    with col_param:
        parametro = st.selectbox("Parametro a analizar", [
            "aportacion",
            "cantidad_banco",
            "tipo_interes",
            "plazo_banco",
            "plazo_tio",
        ], format_func=lambda x: {
            "aportacion": "Mi aportacion neta (€)",
            "cantidad_banco": "Cantidad del banco (€)",
            "tipo_interes": "Tipo de interes (%)",
            "plazo_banco": "Plazo banco (anos)",
            "plazo_tio": "Plazo tio (anos)",
        }[x])

    with col_range:
        # Leer el valor actual ya normalizado de get_params()
        if parametro == "aportacion":
            actual = int(p["aportacion"])
            c1, c2 = st.columns(2)
            min_val = c1.number_input("Minimo (€)", value=max(20000, actual - 30000), step=5000, min_value=20000, max_value=200000)
            max_val = c2.number_input("Maximo (€)", value=min(200000, actual + 30000), step=5000, min_value=20000, max_value=200000)
            valores = np.arange(min_val, max_val + 1, 5000)
        elif parametro == "cantidad_banco":
            actual = int(p["cantidad_banco"])
            c1, c2 = st.columns(2)
            min_val = c1.number_input("Minimo (€)", value=max(100000, actual - 50000), step=5000, min_value=100000, max_value=300000)
            max_val = c2.number_input("Maximo (€)", value=min(300000, actual + 50000), step=5000, min_value=100000, max_value=300000)
            valores = np.arange(min_val, max_val + 1, 5000)
        elif parametro == "tipo_interes":
            actual = round(p["tipo_interes_base"] * 100, 2)
            c1, c2 = st.columns(2)
            min_val = c1.number_input("Minimo (%)", value=max(0.01, round(actual - 0.5, 2)), step=0.05, min_value=0.01, max_value=10.0)
            max_val = c2.number_input("Maximo (%)", value=min(10.0, round(actual + 0.5, 2)), step=0.05, min_value=0.01, max_value=10.0)
            valores = np.arange(min_val, max_val + 0.001, 0.05)
        elif parametro == "plazo_banco":
            actual = int(p["plazo_banco"])
            c1, c2 = st.columns(2)
            min_val = c1.number_input("Minimo (anos)", value=max(5, actual - 5), step=1, min_value=5, max_value=40)
            max_val = c2.number_input("Maximo (anos)", value=min(40, actual + 5), step=1, min_value=5, max_value=40)
            valores = np.arange(min_val, max_val + 1, 1)
        elif parametro == "plazo_tio":
            actual = int(p["plazo_tio"])
            c1, c2 = st.columns(2)
            min_val = c1.number_input("Minimo (anos)", value=max(1, actual - 3), step=1, min_value=1, max_value=30)
            max_val = c2.number_input("Maximo (anos)", value=min(30, actual + 3), step=1, min_value=1, max_value=30)
            valores = np.arange(min_val, max_val + 1, 1)

    # Mapeo: nombre en UI -> clave en diccionario p
    param_key = {
        "aportacion": "aportacion",
        "cantidad_banco": "cantidad_banco",
        "tipo_interes": "tipo_interes_base",
        "plazo_banco": "plazo_banco",
        "plazo_tio": "plazo_tio",
    }[parametro]

    cuotas = []
    limites = []
    for v in valores:
        p_temp = dict(p)  # copia
        if parametro == "aportacion":
            p_temp["aportacion"] = int(v)
        elif parametro == "cantidad_banco":
            p_temp["cantidad_banco"] = int(v)
        elif parametro == "tipo_interes":
            p_temp["tipo_interes_base"] = v / 100
        elif parametro == "plazo_banco":
            p_temp["plazo_banco"] = int(v)
        elif parametro == "plazo_tio":
            p_temp["plazo_tio"] = int(v)

        esc_temp = calcular_escenario(
            p_temp["precio_piso"], p_temp["gastos"], p_temp["aportacion"], p_temp["cantidad_banco"],
            p_temp["tipo_interes_base"], p_temp["plazo_banco"], p_temp["plazo_tio"],
            p_temp["ingresos"], p_temp["max_pct"],
            p_temp["otra_cuota"], p_temp["otra_resto"], p_temp["num_partes"],
            p_temp["cancelar_madre"], p_temp["plazo_devol_madre"],
            p_temp["bonif_nomina_activa"], p_temp["bonif_nomina_pct"],
            p_temp["bonif_hogar_activa"], p_temp["bonif_hogar_pct"], p_temp["bonif_hogar_coste"],
            p_temp["bonif_vida_activa"], p_temp["bonif_vida_pct"], p_temp["bonif_vida_coste"],
            p_temp["bonif_otro_activa"], p_temp["bonif_otro_pct"], p_temp["bonif_otro_coste"]
        )
        cuotas.append(esc_temp["gasto_mensual"])
        limites.append(esc_temp["max_efectivo"])

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(valores, cuotas, color="#e74c3c", linewidth=2.5, marker="o", markersize=4, label="Cuota mensual total")

    valor_base = p[param_key]
    if parametro in ["aportacion", "cantidad_banco", "plazo_banco", "plazo_tio"]:
        valor_base = int(valor_base)
    elif parametro == "tipo_interes":
        valor_base = round(valor_base * 100, 2)

    idx_base = np.argmin(np.abs(valores - valor_base))
    ax.axvline(x=valores[idx_base], color="#2ecc71", linestyle=":", linewidth=2, alpha=0.7, label="Valor actual")
    ax.scatter([valores[idx_base]], [cuotas[idx_base]], color="#2ecc71", s=100, zorder=5)

    ax.set_xlabel({
        "aportacion": "Mi aportacion neta (€)",
        "cantidad_banco": "Cantidad del banco (€)",
        "tipo_interes": "Tipo de interes (%)",
        "plazo_banco": "Plazo banco (anos)",
        "plazo_tio": "Plazo tio (anos)",
    }[parametro], fontsize=12)
    ax.set_ylabel("Cuota mensual total (€)", fontsize=12)
    ax.set_title(f"Evolucion de la cuota segun {parametro}", fontsize=14, fontweight="bold")
    ax.legend(loc="upper right")
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    st.pyplot(fig)

    st.subheader("📋 Valores detallados")
    tabla_data = []
    for i, v in enumerate(valores):
        tabla_data.append({
            "Valor": f"{v:,.0f} €" if parametro in ["aportacion", "cantidad_banco"] else (f"{v:.2f}%" if parametro == "tipo_interes" else f"{int(v)}"),
            "Cuota total/mes": fmt(cuotas[i]),
            "Diferencia vs actual": fmt(cuotas[i] - cuotas[idx_base])
        })
    st.table(tabla_data)


# =============================================================================
#  PAGINA: AMORTIZACION
# =============================================================================

elif st.session_state.pagina == "Amortizacion":

    st.title("💰 Calculadora de Amortizacion Anticipada")
    st.markdown("Compara cuanto te ahorras amortizando una cantidad extra, ya sea acortando el plazo o reduciendo la cuota mensual.")

    from datetime import date
    hoy = date.today()

    # =============================================================================
    #  INPUTS
    # =============================================================================

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("📋 Datos de la hipoteca")
        cap_inicial = st.number_input("Capital prestado (€)", value=int(p["cantidad_banco"]), step=1000, key="amort_capital")
        tipo_int = st.slider("Tipo de interes anual (%)", min_value=0.5, max_value=6.0, value=round(p["tipo_interes_base"]*100, 2), step=0.01, key="amort_tipo")
        plazo_anos = st.slider("Plazo total (anos)", min_value=5, max_value=40, value=int(p["plazo_banco"]), step=1, key="amort_plazo")
        fecha_inicio = st.date_input("Fecha inicio de la hipoteca", value=date(hoy.year-1, hoy.month, 1), key="amort_fecha_inicio")
        fecha_actual = st.date_input("Fecha actual", value=hoy, key="amort_fecha_actual")

        st.subheader("💶 Amortizacion")
        cantidad_amortizar = st.number_input("Cantidad a amortizar (€)", value=10000, step=1000, min_value=1000, key="amort_cantidad")

    with col2:
        st.subheader("📊 Situacion actual")

        if fecha_actual < fecha_inicio:
            st.error("La fecha actual no puede ser anterior a la fecha de inicio.")
        else:
            meses_pasados = (fecha_actual.year - fecha_inicio.year) * 12 + (fecha_actual.month - fecha_inicio.month)
            meses_pasados = max(0, meses_pasados)

            r_mensual = (tipo_int / 100) / 12
            n_total = plazo_anos * 12
            meses_pasados = min(meses_pasados, n_total)

            if cap_inicial <= 0 or tipo_int <= 0 or plazo_anos <= 0:
                st.error("Los datos de la hipoteca deben ser mayores que cero.")
            else:
                cuota_original = cuota_hipoteca_fija(cap_inicial, tipo_int / 100, plazo_anos)
                pendiente = capital_pendiente(cap_inicial, tipo_int / 100, plazo_anos, meses_pasados)
                meses_restantes = n_total - meses_pasados

                m1, m2 = st.columns(2)
                m1.metric("Cuota mensual", fmt(cuota_original))
                m2.metric("Capital pendiente", fmt(pendiente))
                m3, m4 = st.columns(2)
                m3.metric("Meses transcurridos", f"{meses_pasados}")
                m4.metric("Meses restantes", f"{meses_restantes}")

                if cantidad_amortizar > pendiente:
                    st.warning(f"La cantidad a amortizar ({fmt(cantidad_amortizar)}) supera el capital pendiente ({fmt(pendiente)}). Se usara el capital pendiente.")
                    cantidad_amortizar = pendiente

                if cantidad_amortizar > 0 and pendiente > 0 and meses_restantes > 0:
                    # --- CALCULOS ---

                    # Sin amortizar
                    total_sin = cuota_original * meses_restantes
                    intereses_sin = total_sin - pendiente

                    # Acortar plazo
                    nuevo_capital = pendiente - cantidad_amortizar
                    ratio = r_mensual * nuevo_capital / cuota_original
                    if ratio >= 1.0 or nuevo_capital <= 0:
                        meses_exactos_acortar = 0.0
                    else:
                        meses_exactos_acortar = -math.log(1 - ratio) / math.log(1 + r_mensual)
                    meses_exactos_acortar = max(0.0, meses_exactos_acortar)
                    meses_redondeado_acortar = math.ceil(meses_exactos_acortar)

                    total_acortar = cuota_original * meses_exactos_acortar
                    intereses_acortar = total_acortar - nuevo_capital
                    ahorro_acortar = intereses_sin - intereses_acortar
                    meses_ahorrados = meses_restantes - meses_exactos_acortar

                    # Reducir cuota
                    nueva_cuota = cuota_hipoteca_fija(nuevo_capital, tipo_int / 100, meses_restantes / 12)
                    total_reducir = nueva_cuota * meses_restantes
                    intereses_reducir = total_reducir - nuevo_capital
                    ahorro_reducir = intereses_sin - intereses_reducir
                    ahorro_mensual = cuota_original - nueva_cuota

                    st.divider()
                    st.subheader("🎯 Resultados de amortizar")

                    # Opcion 1: Acortar plazo
                    st.markdown("#### 🏃 Acortar plazo (misma cuota, menos meses)")
                    a1, a2, a3, a4 = st.columns(4)
                    a1.metric("Intereses restantes", fmt(intereses_acortar))
                    a2.metric("Ahorro en intereses", fmt(ahorro_acortar), delta=f"-{fmt(ahorro_acortar)}")
                    a3.metric("Meses restantes", str(meses_redondeado_acortar))
                    a4.metric("Meses ahorrados", f"{meses_ahorrados:.1f}", delta=f"-{meses_ahorrados:.1f}")

                    # Opcion 2: Reducir cuota
                    st.markdown("#### 🐢 Reducir cuota (mismos meses, cuota menor)")
                    r1, r2, r3, r4 = st.columns(4)
                    r1.metric("Intereses restantes", fmt(intereses_reducir))
                    r2.metric("Ahorro en intereses", fmt(ahorro_reducir), delta=f"-{fmt(ahorro_reducir)}")
                    r3.metric("Nueva cuota", fmt(nueva_cuota), delta=f"-{fmt(ahorro_mensual)}")
                    r4.metric("Cuota actual", fmt(cuota_original))

                    # Comparativa visual
                    st.divider()
                    st.subheader("📈 Comparativa de intereses restantes")

                    fig, ax = plt.subplots(figsize=(10, 5))
                    categorias = ["Sin amortizar", "Acortar plazo", "Reducir cuota"]
                    intereses_vals = [intereses_sin, intereses_acortar, intereses_reducir]
                    colores = ["#95a5a6", "#e74c3c", "#3498db"]

                    bars = ax.bar(categorias, intereses_vals, color=colores, alpha=0.8)
                    ax.set_ylabel("Intereses restantes (€)")
                    ax.set_title("Intereses a pagar desde hoy segun opcion de amortizacion")

                    for bar, val in zip(bars, intereses_vals):
                        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(intereses_vals)*0.01,
                                fmt(val), ha="center", va="bottom", fontweight="bold")

                    plt.tight_layout()
                    st.pyplot(fig)

                    # Tabla resumen limpia
                    st.divider()
                    st.subheader("📋 Resumen detallado")

                    st.markdown("**Situacion actual**")
                    st.json({
                        "Capital pendiente": fmt(pendiente),
                        "Cuota mensual": fmt(cuota_original),
                        "Meses restantes": meses_restantes,
                        "Intereses restantes (sin amortizar)": fmt(intereses_sin),
                    })

                    st.markdown("**Tras amortizar " + fmt(cantidad_amortizar) + "**")
                    st.json({
                        "Nuevo capital": fmt(nuevo_capital),
                        "Opcion Acortar plazo": {
                            "Intereses restantes": fmt(intereses_acortar),
                            "Ahorro en intereses": fmt(ahorro_acortar),
                            "Meses restantes (exacto)": round(meses_exactos_acortar, 1),
                            "Meses restantes (redondeado)": meses_redondeado_acortar,
                            "Meses ahorrados": round(meses_ahorrados, 1),
                        },
                        "Opcion Reducir cuota": {
                            "Intereses restantes": fmt(intereses_reducir),
                            "Ahorro en intereses": fmt(ahorro_reducir),
                            "Nueva cuota mensual": fmt(nueva_cuota),
                            "Ahorro mensual": fmt(ahorro_mensual),
                        }
                    })
# =============================================================================
#  PAGINA: MIS ESCENARIOS
# =============================================================================

else:
    st.title("📂 Mis escenarios guardados")
    st.markdown("Aqui puedes ver todos los escenarios guardados en Supabase, cargarlos o eliminarlos.")

    records = cargar_desde_supabase()

    if not records:
        st.info("No tienes escenarios guardados todavia (o no se pudo conectar a Supabase). Ve a 'Calcular' y guarda uno.")
    else:
        st.write(f"Tienes **{len(records)}** escenario(s) guardado(s) en Supabase.")
        st.divider()

        for r in records:
            nombre = r.get("nombre", "Sin nombre")

            cuota_banco = float(r.get("cuota_banco", 0))
            cuota_tio = float(r.get("cuota_tio", 0))
            intereses = float(r.get("intereses_totales", 0))
            cantidad_banco = float(r.get("cantidad_banco", 0))
            tipo_interes = float(r.get("tipo_interes", 0))
            plazo_banco = int(r.get("plazo_banco", 0))

            if intereses == 0 and cuota_banco > 0 and cantidad_banco > 0 and plazo_banco > 0:
                total_pagado = cuota_banco * plazo_banco * 12
                intereses = total_pagado - cantidad_banco

            pct_intereses = (intereses / cantidad_banco * 100) if cantidad_banco > 0 else 0
            pedido_fmt = f"{int(cantidad_banco):,} €".replace(",", ".")

            with st.container(border=True):
                c1, c2, c3, c4, c5, c6, c7 = st.columns([2.5, 1.0, 1.0, 1.0, 1.2, 0.7, 0.7])

                with c1:
                    st.markdown(f"<span style='font-size:0.9rem; font-weight:600'>{nombre}</span>", unsafe_allow_html=True)
                    st.markdown(f"<span style='font-size:0.75rem; color:#666'>Pedido: {pedido_fmt} | Tipo: {tipo_interes:.2f}% | {plazo_banco} anos</span>", unsafe_allow_html=True)

                with c2:
                    st.markdown(f"<span style='font-size:0.75rem; color:#666'>Total/mes</span>", unsafe_allow_html=True)
                    st.markdown(f"<span style='font-size:0.9rem; font-weight:600'>{fmt(cuota_banco + cuota_tio)}</span>", unsafe_allow_html=True)

                with c3:
                    st.markdown(f"<span style='font-size:0.75rem; color:#666'>Banco</span>", unsafe_allow_html=True)
                    st.markdown(f"<span style='font-size:0.9rem'>{fmt(cuota_banco)}</span>", unsafe_allow_html=True)

                with c4:
                    st.markdown(f"<span style='font-size:0.75rem; color:#666'>Tio</span>", unsafe_allow_html=True)
                    st.markdown(f"<span style='font-size:0.9rem'>{fmt(cuota_tio)}</span>", unsafe_allow_html=True)

                with c5:
                    st.markdown(f"<span style='font-size:0.75rem; color:#666'>Intereses</span>", unsafe_allow_html=True)
                    st.markdown(f"<span style='font-size:0.85rem; color:#e74c3c'>{fmt(intereses)} ({pct_intereses:.1f}%)</span>", unsafe_allow_html=True)

                with c6:
                    if st.button("📂", key=f"cargar_{nombre}", help="Cargar escenario"):
                        st.session_state.cargar_nombre = nombre
                        st.session_state.pagina = "Calcular"
                        st.rerun()

                with c7:
                    if st.button("🗑️", key=f"eliminar_{nombre}", help="Eliminar escenario"):
                        if eliminar_de_supabase(nombre):
                            st.success(f"'{nombre}' eliminado")
                            st.rerun()
                        else:
                            st.error("No se pudo eliminar")

    st.divider()
    if st.button("➕ Crear nuevo escenario"):
        st.session_state.pagina = "Calcular"
        st.rerun()
