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
import os
from datetime import datetime
import numpy as np
import matplotlib.pyplot as plt
import streamlit as st

st.set_page_config(page_title="Calculadora Hipotecaria", layout="wide")

# =============================================================================
#  SUPABASE - Configuracion
# =============================================================================

SUPABASE_URL = "https://TU-PROJECT.supabase.co"   # <-- CAMBIA ESTO si no usas secrets
SUPABASE_KEY = "TU-ANON-KEY"                        # <-- CAMBIA ESTO si no usas secrets


def get_supabase_client():
    """Conecta con Supabase usando credenciales de Streamlit Secrets o variables."""
    try:
        from supabase import create_client

        # Intentar leer de Streamlit Secrets primero
        try:
            url = st.secrets["supabase"]["url"]
            key = st.secrets["supabase"]["key"]
        except Exception:
            # Fallback a variables hardcodeadas
            url = SUPABASE_URL
            key = SUPABASE_KEY

        # Asegurar que la URL no termine en /
        url = url.rstrip("/")

        client = create_client(url, key)
        return client
    except Exception as e:
        st.error(f"Error conectando a Supabase: {e}")
        return None


def diagnosticar_supabase():
    """Muestra información de diagnóstico sobre la conexión a Supabase."""
    try:
        from supabase import create_client
        try:
            url = st.secrets["supabase"]["url"].rstrip("/")
            key = st.secrets["supabase"]["key"]
            source = "Streamlit Secrets"
        except Exception:
            url = SUPABASE_URL.rstrip("/")
            key = SUPABASE_KEY
            source = "Variables del script"

        st.write(f"**URL:** `{url}`")
        st.write(f"**Key (primeros 20 chars):** `{key[:20]}...`")
        st.write(f"**Fuente:** {source}")

        client = create_client(url, key)

        # Intentar listar tablas
        try:
            response = client.rpc("get_schema", {}).execute()
            st.write(f"**Respuesta RPC:** {response}")
        except Exception as e:
            st.write(f"**RPC falló (normal):** {e}")

        return client
    except Exception as e:
        st.error(f"Diagnóstico falló: {e}")
        return None


def guardar_en_supabase(datos):
    """Guarda un escenario en Supabase."""
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
            return False, "La tabla 'escenarios' no existe en Supabase. Créala primero."
        else:
            return False, f"Error de Supabase: {error_str}"


def cargar_desde_supabase():
    """Carga todos los escenarios guardados en Supabase."""
    client = get_supabase_client()
    if client is None:
        return []
    try:
        response = client.table("escenarios").select("*").order("created_at", desc=True).execute()
        return response.data
    except Exception as e:
        error_str = str(e)
        if "PGRST125" in error_str or "Invalid path" in error_str:
            st.error("Supabase: RLS está activado sin políticas. Desactívalo en Table Editor → escenarios → toggle RLS.")
        elif "relation" in error_str.lower() and "does not exist" in error_str.lower():
            st.error("Supabase: La tabla 'escenarios' no existe. Créala primero.")
        else:
            st.error(f"Error cargando desde Supabase: {error_str}")
        return []


def eliminar_de_supabase(nombre):
    """Elimina un escenario por nombre."""
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
        "cancelar_madre": cancelar_madre,
        "tipo_interes_base": tipo_interes_base,
        "tipo_interes_bonif": tipo_interes,
        "descuento_total": descuento_total,
    }


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
    ax.fill_between(x, y_banco, y_banco + y_tio, color="#3498db", alpha=0.8, label="Tío")

    if esc["coste_seguros_mes"] > 0:
        ax.fill_between(x, y_banco + y_tio, y_banco + y_tio + y_seguros, color="#9b59b6", alpha=0.8, label="Seguros")

    if esc["cancelar_madre"]:
        ax.fill_between(x, 0, y_madre, color="#2ecc71", alpha=0.8, label="Madre (devolución)")
        ax.axhline(y=0, color="black", linewidth=0.5)

    ax.axhline(y=esc["max_efectivo"], color="purple", linestyle="--", linewidth=2, label="Límite banco")

    ax.set_title("Evolución de la cuota mensual", fontsize=14, fontweight="bold")
    ax.set_xlabel("Mes")
    ax.set_ylabel("Cuota mensual (€)")
    ax.legend(loc="upper right")
    ax.set_xlim(1, meses_totales)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    return fig


# =============================================================================
#  INICIALIZAR SESSION STATE
# =============================================================================

if "pagina" not in st.session_state:
    st.session_state.pagina = "Calcular"

if "cargar_nombre" not in st.session_state:
    st.session_state.cargar_nombre = None


# =============================================================================
#  NAVEGACION
# =============================================================================

st.sidebar.title("🧭 Navegación")
pagina = st.sidebar.radio("Ir a", ["Calcular", "Mis escenarios"], index=0 if st.session_state.pagina == "Calcular" else 1)

if pagina != st.session_state.pagina:
    st.session_state.pagina = pagina
    st.rerun()


# =============================================================================
#  PAGINA: CALCULAR
# =============================================================================

if st.session_state.pagina == "Calcular":

    st.title("🏠 Calculadora de Hipotecas")
    st.markdown("Modifica los parámetros en el panel de la izquierda y ve cómo evoluciona tu cuota en tiempo real.")

    defaults = {
        "precio_piso": 365_000, "gastos": 8_500, "aportacion": 100_000,
        "cantidad_banco": 200_000, "tipo_interes": 3.5, "plazo_banco": 30,
        "plazo_tio": 10, "ingresos": 2_999, "max_pct": 35,
        "otra_cuota": 529, "otra_resto": 31_000, "num_partes": 3,
        "cancelar_madre": False, "plazo_devol_madre": 10,
        "bonif_nomina_activa": False, "bonif_nomina_pct": 0.30,
        "bonif_hogar_activa": False, "bonif_hogar_pct": 0.10, "bonif_hogar_coste": 25.0,
        "bonif_vida_activa": False, "bonif_vida_pct": 0.10, "bonif_vida_coste": 15.0,
        "bonif_otro_activa": False, "bonif_otro_pct": 0.05, "bonif_otro_coste": 0.0,
    }

    if st.session_state.cargar_nombre is not None:
        try:
            records = cargar_desde_supabase()
            for r in records:
                if r.get("nombre") == st.session_state.cargar_nombre:
                    for key in defaults:
                        if key in r:
                            val = r[key]
                            if key in ["cancelar_madre", "bonif_nomina_activa", "bonif_hogar_activa",
                                       "bonif_vida_activa", "bonif_otro_activa", "cumple"]:
                                defaults[key] = bool(val)
                            else:
                                defaults[key] = val
                    break
        except Exception:
            pass
        st.session_state.cargar_nombre = None
        st.toast("Escenario cargado", icon="✅")

    with st.sidebar:
        st.header("⚙️ Parámetros")

        st.subheader("El piso")
        precio_piso = st.number_input("Precio del piso (€)", value=int(defaults["precio_piso"]), step=1_000, key="precio_piso")
        gastos = st.number_input("Gastos (notaría, registro, ITP...) (€)", value=int(defaults["gastos"]), step=500, key="gastos")
        aportacion = st.number_input("Tu aportación neta (€)", value=int(defaults["aportacion"]), step=1_000, key="aportacion")

        st.subheader("El banco")
        cantidad_banco = st.number_input("Cantidad que te da el banco (€)", value=int(defaults["cantidad_banco"]), step=1_000, key="cantidad_banco")
        tipo_interes_base = st.slider("Tipo de interés anual SIN bonificar (%)", min_value=2.0, max_value=4.0, value=float(defaults["tipo_interes"]), step=0.01, key="tipo_interes") / 100
        plazo_banco = st.slider("Plazo banco (años)", min_value=20, max_value=40, value=int(defaults["plazo_banco"]), step=1, key="plazo_banco")

        st.subheader("El tío")
        plazo_tio = st.slider("Plazo tío (años)", min_value=5, max_value=20, value=int(defaults["plazo_tio"]), step=1, key="plazo_tio")

        st.subheader("Tus ingresos")
        ingresos = st.number_input("Ingresos netos mensuales (€)", value=int(defaults["ingresos"]), step=50, key="ingresos")
        max_pct = st.slider("Máxima cuota banco (% de ingresos)", min_value=30, max_value=50, value=int(defaults["max_pct"]), step=1, key="max_pct") / 100

        st.subheader("Otra hipoteca (madre/hermana)")
        st.markdown("*La paga tu madre, pero el banco te resta capacidad por ser titular.*")
        otra_cuota = st.number_input("Cuota total mensual (€)", value=int(defaults["otra_cuota"]), step=10, key="otra_cuota")
        otra_resto = st.number_input("Capital pendiente (€)", value=int(defaults["otra_resto"]), step=1_000, key="otra_resto")
        num_partes = st.number_input("Número de titulares", value=int(defaults["num_partes"]), step=1, min_value=1, key="num_partes")

        st.subheader("¿Cancelar la hipoteca de la madre?")
        cancelar_madre = st.checkbox(f"Sí, cancelarla (le doy {fmt(otra_resto)} y me los devuelve)", value=defaults["cancelar_madre"], key="cancelar_madre")
        if cancelar_madre:
            plazo_devol_madre = st.slider("Plazo devolución madre (años)", min_value=3, max_value=15, value=int(defaults["plazo_devol_madre"]), step=1, key="plazo_devol_madre")
        else:
            plazo_devol_madre = int(defaults["plazo_devol_madre"])

        st.subheader("🎁 Bonificaciones")
        st.markdown("*Marca las que apliques para ver el interés bonificado.*")

        bonif_nomina_activa = st.checkbox("📋 Nómina", value=defaults["bonif_nomina_activa"], key="bonif_nomina_activa")
        if bonif_nomina_activa:
            bonif_nomina_pct = st.number_input("Bonificación nómina (%)", value=float(defaults["bonif_nomina_pct"]), step=0.01, min_value=0.0, max_value=2.0, key="bonif_nomina_pct") / 100
        else:
            bonif_nomina_pct = float(defaults["bonif_nomina_pct"]) / 100

        bonif_hogar_activa = st.checkbox("🏠 Seguro de hogar", value=defaults["bonif_hogar_activa"], key="bonif_hogar_activa")
        if bonif_hogar_activa:
            bonif_hogar_pct = st.number_input("Bonificación hogar (%)", value=float(defaults["bonif_hogar_pct"]), step=0.01, min_value=0.0, max_value=2.0, key="bonif_hogar_pct") / 100
            bonif_hogar_coste = st.number_input("Coste seguro hogar (€/mes)", value=float(defaults["bonif_hogar_coste"]), step=1.0, min_value=0.0, key="bonif_hogar_coste")
        else:
            bonif_hogar_pct = float(defaults["bonif_hogar_pct"]) / 100
            bonif_hogar_coste = float(defaults["bonif_hogar_coste"])

        bonif_vida_activa = st.checkbox("❤️ Seguro de vida", value=defaults["bonif_vida_activa"], key="bonif_vida_activa")
        if bonif_vida_activa:
            bonif_vida_pct = st.number_input("Bonificación vida (%)", value=float(defaults["bonif_vida_pct"]), step=0.01, min_value=0.0, max_value=2.0, key="bonif_vida_pct") / 100
            bonif_vida_coste = st.number_input("Coste seguro vida (€/mes)", value=float(defaults["bonif_vida_coste"]), step=1.0, min_value=0.0, key="bonif_vida_coste")
        else:
            bonif_vida_pct = float(defaults["bonif_vida_pct"]) / 100
            bonif_vida_coste = float(defaults["bonif_vida_coste"])

        bonif_otro_activa = st.checkbox("➕ Otro adicional", value=defaults["bonif_otro_activa"], key="bonif_otro_activa")
        if bonif_otro_activa:
            bonif_otro_pct = st.number_input("Bonificación otro (%)", value=float(defaults["bonif_otro_pct"]), step=0.01, min_value=0.0, max_value=2.0, key="bonif_otro_pct") / 100
            bonif_otro_coste = st.number_input("Coste otro (€/mes)", value=float(defaults["bonif_otro_coste"]), step=1.0, min_value=0.0, key="bonif_otro_coste")
        else:
            bonif_otro_pct = float(defaults["bonif_otro_pct"]) / 100
            bonif_otro_coste = float(defaults["bonif_otro_coste"])

    esc = calcular_escenario(
        precio_piso, gastos, aportacion, cantidad_banco, tipo_interes_base,
        plazo_banco, plazo_tio, ingresos, max_pct,
        otra_cuota, otra_resto, num_partes,
        cancelar_madre, plazo_devol_madre,
        bonif_nomina_activa, bonif_nomina_pct,
        bonif_hogar_activa, bonif_hogar_pct, bonif_hogar_coste,
        bonif_vida_activa, bonif_vida_pct, bonif_vida_coste,
        bonif_otro_activa, bonif_otro_pct, bonif_otro_coste
    )

    # =============================================================================
    #  RESULTADOS
    # =============================================================================

    if esc["descuento_total"] > 0:
        st.info(f"📉 Interés base: **{tipo_interes_base*100:.2f}%** → Bonificado: **{esc['tipo_interes_bonif']*100:.2f}%** (descuento total: {esc['descuento_total']*100:.2f}%)")
    else:
        st.info(f"📉 Interés aplicado: **{esc['tipo_interes_bonif']*100:.2f}%** (sin bonificaciones)")

    st.header("💶 Tu cuota mensual")

    if esc["cancelar_madre"]:
        cols = st.columns(5)
        cols[0].metric("TOTAL NETO al mes", fmt(esc["neto_mensual"]), help="Banco + Tío + Seguros - Devolución madre")
        cols[1].metric("→ BANCO", fmt(esc["cuota_banco"]))
        cols[2].metric("→ TÍO", fmt(esc["cuota_tio"]))
        cols[3].metric("→ SEGUROS", fmt(esc["coste_seguros_mes"]) if esc["coste_seguros_mes"] > 0 else "0,00 €")
        cols[4].metric("→ MADRE devuelve", f"+{fmt(esc['cuota_devol_madre'])}")
    else:
        cols = st.columns(4)
        cols[0].metric("TOTAL al mes", fmt(esc["gasto_mensual"]), help="Banco + Tío + Seguros")
        cols[1].metric("→ BANCO", fmt(esc["cuota_banco"]))
        cols[2].metric("→ TÍO", fmt(esc["cuota_tio"]))
        cols[3].metric("→ SEGUROS", fmt(esc["coste_seguros_mes"]) if esc["coste_seguros_mes"] > 0 else "0,00 €")

    st.divider()

    st.header("🏦 Límite del banco")
    lim1, lim2, lim3 = st.columns(3)
    lim1.metric(f"Máx. cuota bruta ({max_pct*100:.0f}%)", f"{fmt(esc['max_bruto'])}/mes")
    if not esc["cancelar_madre"]:
        lim2.metric("Resta otra hipoteca", f"-{fmt(esc['resta_otra'])}/mes", help="El banco te resta esta cantidad por ser titular")
    else:
        lim2.metric("Resta otra hipoteca", "0 €", help="Hipoteca cancelada, no hay resta")
    lim3.metric("Capacidad EFECTIVA", f"{fmt(esc['max_efectivo'])}/mes", help="Cuota máxima que el banco te permitiría")

    st.info(f"💡 **Con estos datos, el banco podría darte como máximo: {fmt(esc['capital_max_banco'])}** (cuota de {fmt(esc['max_efectivo'])}/mes a {esc['tipo_interes_bonif']*100:.2f}% en {plazo_banco} años)")

    if esc["cumple"]:
        st.success(f"✅ La cuota del banco ({fmt(esc['cuota_banco'])}) CUMPLE el límite. Sobran {fmt(esc['max_efectivo'] - esc['cuota_banco'])} al mes.")
    else:
        st.error(f"❌ La cuota del banco ({fmt(esc['cuota_banco'])}) SUPERA el límite. Faltan {fmt(esc['cuota_banco'] - esc['max_efectivo'])} al mes.")

    st.divider()

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
                "Seguros": fmt(p["seguros"]) if p["seguros"] > 0 else "---",
                "Madre": f"+{fmt(p['madre'])} (dev.)" if (esc["cancelar_madre"] and p["madre"] > 0) else "---",
                "Total neto": fmt(p["total"])
            })
        st.table(periodos_data)

    st.divider()

    # --- GUARDAR EN SUPABASE ---
    st.header("💾 Guardar escenario")

    # Diagnóstico de conexión (colapsado por defecto)
    with st.expander("🔧 Diagnóstico de conexión a Supabase"):
        diagnosticar_supabase()

    nombre_guardar = st.text_input("Nombre del escenario", placeholder="Ej: Oferta Santander marzo")
    if st.button("💾 Guardar en Supabase", type="primary"):
        if nombre_guardar.strip() == "":
            st.error("Introduce un nombre para guardar")
        else:
            datos_guardar = {
                "nombre": nombre_guardar.strip(),
                "precio_piso": precio_piso, "gastos": gastos, "aportacion": aportacion,
                "cantidad_banco": cantidad_banco, "tipo_interes": round(tipo_interes_base * 100, 2),
                "plazo_banco": plazo_banco, "plazo_tio": plazo_tio,
                "ingresos": ingresos, "max_pct": int(max_pct * 100),
                "otra_cuota": otra_cuota, "otra_resto": otra_resto, "num_partes": num_partes,
                "cancelar_madre": cancelar_madre, "plazo_devol_madre": plazo_devol_madre,
                "bonif_nomina_activa": bonif_nomina_activa, "bonif_nomina_pct": round(bonif_nomina_pct * 100, 2),
                "bonif_hogar_activa": bonif_hogar_activa, "bonif_hogar_pct": round(bonif_hogar_pct * 100, 2), "bonif_hogar_coste": bonif_hogar_coste,
                "bonif_vida_activa": bonif_vida_activa, "bonif_vida_pct": round(bonif_vida_pct * 100, 2), "bonif_vida_coste": bonif_vida_coste,
                "bonif_otro_activa": bonif_otro_activa, "bonif_otro_pct": round(bonif_otro_pct * 100, 2), "bonif_otro_coste": bonif_otro_coste,
                "cuota_banco": round(esc["cuota_banco"], 2), "cuota_tio": round(esc["cuota_tio"], 2),
                "coste_seguros": round(esc["coste_seguros_mes"], 2), "total_mensual": round(esc["gasto_mensual"], 2),
                "cumple": esc["cumple"],
            }
            ok, error_msg = guardar_en_supabase(datos_guardar)
            if ok:
                st.success(f"Escenario '{nombre_guardar.strip()}' guardado en Supabase ✅")
            else:
                st.error(f"No se pudo guardar en Supabase: {error_msg}")
                st.warning("Puedes copiar los datos manualmente desde abajo.")

    # Fallback: mostrar JSON copiable siempre
    with st.expander("📋 Ver datos como JSON (copia manual si Supabase falla)"):
        datos_json = {
            "nombre": nombre_guardar if nombre_guardar else "sin_nombre",
            "precio_piso": precio_piso, "gastos": gastos, "aportacion": aportacion,
            "cantidad_banco": cantidad_banco, "tipo_interes": round(tipo_interes_base * 100, 2),
            "plazo_banco": plazo_banco, "plazo_tio": plazo_tio,
            "ingresos": ingresos, "max_pct": int(max_pct * 100),
            "otra_cuota": otra_cuota, "otra_resto": otra_resto, "num_partes": num_partes,
            "cancelar_madre": cancelar_madre, "plazo_devol_madre": plazo_devol_madre,
            "bonif_nomina_activa": bonif_nomina_activa, "bonif_nomina_pct": round(bonif_nomina_pct * 100, 2),
            "bonif_hogar_activa": bonif_hogar_activa, "bonif_hogar_pct": round(bonif_hogar_pct * 100, 2), "bonif_hogar_coste": bonif_hogar_coste,
            "bonif_vida_activa": bonif_vida_activa, "bonif_vida_pct": round(bonif_vida_pct * 100, 2), "bonif_vida_coste": bonif_vida_coste,
            "bonif_otro_activa": bonif_otro_activa, "bonif_otro_pct": round(bonif_otro_pct * 100, 2), "bonif_otro_coste": bonif_otro_coste,
            "cuota_banco": round(esc["cuota_banco"], 2), "cuota_tio": round(esc["cuota_tio"], 2),
            "coste_seguros": round(esc["coste_seguros_mes"], 2), "total_mensual": round(esc["gasto_mensual"], 2),
            "cumple": esc["cumple"],
        }
        st.code(json.dumps(datos_json, indent=2, ensure_ascii=False), language="json")

    st.divider()
    st.caption("App generada con Streamlit + Supabase.")


# =============================================================================
#  PAGINA: MIS ESCENARIOS
# =============================================================================

else:
    st.title("📂 Mis escenarios guardados")
    st.markdown("Aquí puedes ver todos los escenarios guardados en Supabase, cargarlos o eliminarlos.")

    records = cargar_desde_supabase()

    if not records:
        st.info("No tienes escenarios guardados todavía (o no se pudo conectar a Supabase). Ve a 'Calcular' y guarda uno.")
    else:
        st.write(f"Tienes **{len(records)}** escenario(s) guardado(s) en Supabase.")
        st.divider()

        for r in records:
            tipo_interes = float(r.get("tipo_interes", 3.5)) / 100
            descuento = 0.0
            if bool(r.get("bonif_nomina_activa", False)):
                descuento += float(r.get("bonif_nomina_pct", 0)) / 100
            if bool(r.get("bonif_hogar_activa", False)):
                descuento += float(r.get("bonif_hogar_pct", 0)) / 100
            if bool(r.get("bonif_vida_activa", False)):
                descuento += float(r.get("bonif_vida_pct", 0)) / 100
            if bool(r.get("bonif_otro_activa", False)):
                descuento += float(r.get("bonif_otro_pct", 0)) / 100
            tipo_bonif = max(0.0, tipo_interes - descuento)

            cantidad_banco = float(r.get("cantidad_banco", 200_000))
            plazo_banco = int(r.get("plazo_banco", 30))
            cuota_banco = cuota_hipoteca_fija(cantidad_banco, tipo_bonif, plazo_banco)

            ingresos = float(r.get("ingresos", 2_999))
            max_pct = float(r.get("max_pct", 35)) / 100
            resta = 0.0 if bool(r.get("cancelar_madre", False)) else float(r.get("otra_cuota", 529)) / float(r.get("num_partes", 3))
            max_efectivo = ingresos * max_pct - resta
            cumple = cuota_banco <= max_efectivo
            nombre = r.get("nombre", "Sin nombre")

            with st.container(border=True):
                col1, col2, col3, col4, col5, col6 = st.columns([2, 1.2, 1.2, 1.2, 1, 1])

                with col1:
                    st.markdown(f"**{nombre}**")
                    st.caption(f"Banco: {fmt(cantidad_banco)} | Tipo: {tipo_bonif*100:.2f}% | Plazo: {plazo_banco} años")

                with col2:
                    st.metric("Cuota banco", fmt(cuota_banco))

                with col3:
                    st.metric("Capacidad", fmt(max_efectivo))

                with col4:
                    if cumple:
                        st.success("✅ Cumple")
                    else:
                        st.error("❌ No cumple")

                with col5:
                    if st.button("📂 Cargar", key=f"cargar_{nombre}"):
                        st.session_state.cargar_nombre = nombre
                        st.session_state.pagina = "Calcular"
                        st.rerun()

                with col6:
                    if st.button("🗑️ Eliminar", key=f"eliminar_{nombre}"):
                        if eliminar_de_supabase(nombre):
                            st.success(f"'{nombre}' eliminado")
                            st.rerun()
                        else:
                            st.error("No se pudo eliminar")

    st.divider()
    if st.button("➕ Crear nuevo escenario"):
        st.session_state.pagina = "Calcular"
        st.rerun()
