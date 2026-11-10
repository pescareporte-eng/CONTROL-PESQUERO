# CONTROL PESQUERO

Aplicación web responsive para controlar ingreso de pesca, valorización por tonelada métrica y despachos de hielo por embarcación. Utiliza Google Sheets como almacenamiento principal y Google Drive para guardar los reportes. La aplicación se ejecuta en Python/Flask y puede publicarse en Render.

> **Estado del entregable:** proyecto inicial funcional en código, preparado para conectar con tu cuenta Google. No incluye credenciales ni está conectado a una cuenta real: esas conexiones se realizan siguiendo esta guía.

## 1. Funciones incluidas

- Login con Google limitado a una única dirección autorizada (`ALLOWED_EMAIL`). No hay registro de usuarios ni gestión de otros usuarios.
- Dashboard con TM, KG, importes de pesca e hielo, pendiente de valorización, gráficos y embarcaciones con mayor ingreso.
- Catálogo único de embarcaciones, compartido por pesca y hielo.
- Ingreso de pesca con fecha, embarcación, toneladas TM manuales, kilos KG manuales y observaciones. TM y KG se totalizan de forma independiente.
- Valorización vinculada a un desembarque: TM × precio por TM. Permite valorizaciones parciales y controla que no se valorice más TM que las registradas.
- Despacho de hielo por embarcación, con cantidad, unidad, precio unitario e importe calculado.
- Anulación lógica de registros (no se borran físicamente) y bitácora básica en `AUDITORIA`.
- Reportes PDF y Excel por módulo, periodo y embarcación. Cada reporte se guarda en Drive y también se descarga en el navegador.
- Interfaz adaptable a computadoras, tablets y celulares.

## 2. Requisitos en tu computadora

1. Windows 10/11.
2. Python 3.11 o 3.12 (descarga oficial: https://www.python.org/downloads/). Durante la instalación marca **Add Python to PATH**.
3. Visual Studio Code (https://code.visualstudio.com/).
4. Git (https://git-scm.com/downloads), para subir el código a GitHub.
5. Una cuenta Google propia para Sheets y Drive.

No necesitas instalar PostgreSQL. Google Sheets será la fuente de datos de esta primera versión.

## 3. Abrir el proyecto en VS Code

1. Descomprime `CONTROL_PESQUERO.zip`.
2. Abre VS Code y selecciona **File > Open Folder**. Abre la carpeta `control_pesquero`.
3. En VS Code abre **Terminal > New Terminal**.
4. Crea y activa el entorno virtual:

### Windows PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Si PowerShell bloquea la activación, ejecuta una sola vez en esa terminal:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

## 4. Crear y conectar Google Sheets y Google Drive

La conexión inicial crea automáticamente una hoja llamada `CONTROL_PESQUERO`, sus pestañas, una carpeta de Drive y una carpeta para reportes.

### A. Crear un proyecto de Google Cloud

1. Abre https://console.cloud.google.com/ e inicia sesión con la cuenta Google que será propietaria de tus datos.
2. Crea un proyecto llamado `CONTROL-PESQUERO`.
3. En **APIs & Services > Library**, habilita:
   - Google Sheets API
   - Google Drive API
4. En **Google Auth Platform**, configura la pantalla de consentimiento y el tipo de audiencia. Para uso personal, registra tu propio correo como usuario de prueba mientras haces las primeras pruebas.
5. En **Google Auth Platform > Clients**, crea un OAuth Client ID de tipo **Web application**.
6. En **Authorized redirect URIs**, registra exactamente estas dos direcciones para trabajar localmente:

```text
http://127.0.0.1:8765/
http://127.0.0.1:5000/auth/callback
```

7. Descarga el JSON del cliente OAuth. En el proyecto crea/usa la carpeta `secrets` y guarda el archivo como:

```text
secrets/client_secret.json
```

**No subas ese JSON a GitHub.** Ya está excluido mediante `.gitignore`.

Documentación oficial de OAuth web: https://developers.google.com/identity/protocols/oauth2/web-server

### B. Ejecutar el asistente de Google

Con el entorno virtual activo, desde la raíz del proyecto:

```powershell
python scripts/setup_google.py
```

1. Escribe el correo Google que será el único autorizado a entrar a la aplicación.
2. Se abrirá el navegador. Selecciona esa cuenta y acepta los permisos solicitados para crear y administrar la hoja y los reportes de esta aplicación.
3. Regresa a la terminal. El script crea:
   - La hoja `CONTROL_PESQUERO` con pestañas `EMBARCACIONES`, `INGRESO_PESCA`, `VALORIZACION_PESCA`, `DESPACHO_HIELO` y `AUDITORIA`.
   - La carpeta `CONTROL_PESQUERO` en Drive.
   - La subcarpeta `REPORTES` y la subcarpeta `RESPALDOS`.
   - El archivo local `.env` con los identificadores y credenciales necesarios.

El asistente imprimirá enlaces a la hoja y a la carpeta de Drive.

> Si Google devuelve `redirect_uri_mismatch`, revisa que `http://127.0.0.1:8765/` esté escrito exactamente igual en los URI autorizados del OAuth Client. No cambies `127.0.0.1` por `localhost` sin registrar también esa dirección.

### C. Probar localmente

Ejecuta:

```powershell
python run.py
```

Abre http://127.0.0.1:5000 y pulsa **Ingresar con Google**. Debes entrar con el mismo correo indicado en el asistente. Cualquier otra cuenta será rechazada.

Prueba en este orden:

1. Crea una embarcación.
2. Registra un ingreso de pesca.
3. Selecciona ese ingreso y registra una valorización parcial o total.
4. Registra un despacho de hielo para la misma embarcación.
5. Abre el dashboard.
6. Genera un PDF y verifica que aparece en la carpeta `CONTROL_PESQUERO/REPORTES` de Drive y que también se descarga en tu computadora.

## 5. Subir el proyecto a GitHub

1. Crea una cuenta en https://github.com/ si aún no tienes.
2. Crea un repositorio **privado**, por ejemplo `control-pesquero`.
3. En VS Code abre Terminal y ejecuta desde la carpeta raíz:

```powershell
git init
git add .
git status
```

Antes de confirmar, revisa que `.env` y `secrets/client_secret.json` NO aparezcan entre los archivos listos para subir. Si aparecen, detente y revisa `.gitignore`.

Luego:

```powershell
git commit -m "Version inicial de Control Pesquero"
git branch -M main
git remote add origin https://github.com/TU-CUENTA/control-pesquero.git
git push -u origin main
```

Sustituye `TU-CUENTA` por tu usuario de GitHub. El repositorio contiene código; los datos reales permanecen en Google Sheets/Drive.

## 6. Publicar en Render

1. Crea una cuenta en https://render.com/.
2. En Render selecciona **New > Web Service**.
3. Conecta GitHub y el repositorio privado `control-pesquero`.
4. Configura:

| Campo Render | Valor |
|---|---|
| Runtime | Python 3 |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `gunicorn --workers 1 --threads 4 --timeout 120 wsgi:app` |
| Health Check Path | `/api/health` |

5. En la sección **Environment**, agrega las variables del `.env` local. Puedes usar **Add from .env** si la opción está disponible, o copiarlas una por una. Nunca publiques esos valores en GitHub ni los compartas en chats.
6. Cambia `GOOGLE_REDIRECT_URI` al callback real que Render asigna. Por ejemplo:

```text
https://NOMBRE-DE-TU-SERVICIO.onrender.com/auth/callback
```

7. Vuelve a Google Cloud > OAuth Client y agrega esa misma dirección, exactamente, en **Authorized redirect URIs**.
8. En Render guarda los cambios y despliega nuevamente.
9. Abre la URL de Render e inicia sesión con el correo autorizado.

Render permite desplegar Flask/Gunicorn desde un repositorio conectado y guardar secretos como variables de entorno: https://render.com/docs/deploy-flask y https://render.com/docs/configure-environment-variables

## 7. Variables de entorno

El script `setup_google.py` crea el `.env` local. Las principales variables son:

| Variable | Para qué sirve |
|---|---|
| `SECRET_KEY` | Firma segura de sesiones Flask |
| `ALLOWED_EMAIL` | Único correo autorizado |
| `GOOGLE_CLIENT_ID` | Identifica el cliente OAuth |
| `GOOGLE_CLIENT_SECRET` | Secreto OAuth del servidor |
| `GOOGLE_REDIRECT_URI` | Callback OAuth local o de Render |
| `GOOGLE_TOKEN_JSON_B64` | Token de acceso a Sheets y Drive, codificado en Base64 |
| `GOOGLE_SPREADSHEET_ID` | Identificador de la hoja principal |
| `GOOGLE_DRIVE_ROOT_FOLDER_ID` | Carpeta principal de Drive |
| `GOOGLE_DRIVE_REPORTS_FOLDER_ID` | Carpeta donde se crean los reportes |
| `SESSION_COOKIE_SECURE` | Debe ser `true` en Render con HTTPS |
| `APP_TIMEZONE` | Zona horaria de reportes (`America/Lima`) |

## 8. Cómo se organizan los reportes

Al generar un reporte, la aplicación crea automáticamente esta estructura:

```text
Mi unidad/
└── CONTROL_PESQUERO/
    ├── CONTROL_PESQUERO (Google Sheets)
    ├── REPORTES/
    │   └── 2026/
    │       ├── 01_PESCA/
    │       ├── 02_VALORIZACION/
    │       ├── 03_HIELO/
    │       └── 04_CONSOLIDADO/
    └── RESPALDOS/
```

Los archivos incluyen fecha del periodo y hora de generación para evitar que un reporte nuevo sobrescriba otro. El mismo archivo se devuelve al navegador como descarga.

## 9. Reglas de negocio implementadas

- TM y KG de ingreso de pesca son campos manuales e independientes; no se convierten uno al otro.
- La valorización solo utiliza TM y precio por TM.
- El total se calcula en Python con `Decimal` y se redondea a dos decimales.
- Una descarga puede tener varias valorizaciones parciales, siempre que la suma activa no supere las TM del desembarque.
- El hielo se registra por embarcación. Unidades disponibles: BLOQUE, BOLSA, KG, TM, UNIDAD y OTRO. Las cantidades físicas no se suman entre unidades diferentes; los importes sí.
- Las anulaciones cambian el estado a `ANULADO`; no borran filas.
- La hoja `AUDITORIA` registra altas y anulaciones.
- Una embarcación se desactiva, no se elimina; sus movimientos históricos permanecen.

## 10. Notas importantes antes de usar datos reales

1. **Google Sheets como base principal:** es una alternativa simple para una aplicación personal y volumen moderado. No es una base transaccional como PostgreSQL. Este proyecto usa un proceso Gunicorn y bloqueo en memoria para reducir conflictos. Mantén una sola instancia del servicio y evita registrar simultáneamente desde varias sesiones. Si el sistema crece o varias personas ingresan a la vez, conviene migrar a PostgreSQL.
2. **Límites API:** Google aplica cuotas por minuto a Sheets. La aplicación hace lecturas por operación; para un uso mayor se debe agregar caché, escritura por lotes y reintentos exponenciales. Ver: https://developers.google.com/workspace/sheets/api/limits
3. **OAuth en modo Testing:** Google puede hacer expirar los refresh tokens a los siete días cuando una app externa está en Testing y solicita permisos de acceso a datos. Para uso continuo, revisa la publicación/estado de la pantalla de consentimiento; si el token expira, vuelve a ejecutar el asistente. Ver: https://developers.google.com/identity/protocols/oauth2
4. **Render gratuito:** puede suspender servicios inactivos y no ofrece la misma disponibilidad que un plan de producción. Para uso operativo diario, evalúa un plan de pago.
5. **Copia de seguridad:** la carpeta `RESPALDOS` queda creada, pero esta versión no programa respaldos automáticos. Descarga periódicamente una copia de la hoja desde Google Sheets.
6. **Edición de operaciones:** esta primera versión incluye alta, consulta y anulación con auditoría. No incluye edición de desembarques o precios ya guardados; es preferible definir primero el procedimiento de corrección para no alterar valorizaciones relacionadas.
7. **Pruebas:** antes de registrar operaciones reales, completa los casos de prueba de la sección 4 y confirma los importes y saldos con tus documentos de operación.

## 11. Ejecutar pruebas

Con el entorno virtual activo:

```powershell
pip install pytest
pytest
```

Los tests incluidos verifican validación de cantidades, fechas y redondeo monetario. No sustituyen las pruebas integrales con tu cuenta de Google.

## 12. Seguridad

- Nunca subas `.env`, `secrets/client_secret.json` ni tokens a GitHub.
- Si una credencial se expone, revócala en Google Cloud/tu cuenta Google y genera otra.
- Usa repositorio privado.
- En Render, activa `SESSION_COOKIE_SECURE=true`.
- No compartas la URL de la aplicación si no deseas que otras personas vean el formulario de login; las rutas de datos exigen autenticación y el correo debe coincidir exactamente con `ALLOWED_EMAIL`.
