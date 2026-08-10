# 🏠 Calculadora de Hipotecas con Supabase

App interactiva en Streamlit para comparar escenarios hipotecarios con persistencia en Supabase.

## Requisitos

- Python 3.9+
- Cuenta en Supabase (gratuita)
- Tabla `escenarios` creada en Supabase

## Configuracion local

1. Crea una carpeta `.streamlit/` en la raiz del proyecto
2. Dentro, crea un archivo `secrets.toml`:

```toml
[supabase]
url = "https://TU-PROJECT.supabase.co"
key = "TU-ANON-KEY"
```

3. Edita `SUPABASE_URL` y `SUPABASE_KEY` en el script con tus datos de Supabase.

## Ejecucion local

```bash
pip install -r requirements.txt
streamlit run hipoteca_streamlit.py
```

## Despliegue en Streamlit Cloud

1. Sube este repo a GitHub
2. Ve a [share.streamlit.io](https://share.streamlit.io)
3. Conecta tu repositorio
4. En **Settings → Secrets**, pega:

```toml
[supabase]
url = "https://TU-PROJECT.supabase.co"
key = "TU-ANON-KEY"
```

5. Deploy
