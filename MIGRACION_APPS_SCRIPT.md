# Migración segura de CONTROL-PESQUERO a Google Apps Script

## Qué resuelve esta versión

La versión que enviaste utiliza el mismo refresh token OAuth para Google Sheets y Google Drive. Ese token caduca porque el cliente OAuth está en modo Testing. Esta variante conserva Google Sheets como base de datos y Drive como destino de reportes, pero delega ambas operaciones a una Web App de Apps Script ejecutada bajo `pescareporte@gmail.com`. No usa una cuenta de servicio ni almacenamiento externo de pago.

**El acceso de inicio de sesión al dashboard sigue usando el OAuth web de Flask.** Solo cambia la conexión que el backend usa para leer/escribir Sheets y guardar PDF/Excel.

## Importante antes de usar

- No ejecutar `scripts/setup_google.py`: el script original crea una hoja y carpetas nuevas.
- No borrar las variables ni credenciales antiguas de Render hasta completar todas las pruebas y confirmar el rollback.
- No copiar secretos, claves ni valores de variables de entorno en GitHub o en un chat.
- No subir `.env`, `secrets/` o claves JSON al repositorio. Se añadió `.gitignore` para excluirlos.
- El paquete es una adaptación de código pendiente de probar contra tu cuenta real; no desplegar directamente en producción sin el ensayo descrito abajo.

## Paso A. Crear el proyecto Apps Script

1. Entra a https://script.google.com/ con `pescareporte@gmail.com`.
2. Crea un proyecto nuevo y nómbralo `CONTROL PESQUERO - Conector`.
3. Abre `google_apps_script/Code.gs` de este paquete, copia todo el contenido y reemplaza el contenido de `Code.gs` del editor.
4. En Apps Script > Configuración del proyecto (ícono de engranaje) > Propiedades del script, agrega estas tres propiedades:

| Propiedad | Valor |
|---|---|
| `CP_SPREADSHEET_ID` | Valor actual de `GOOGLE_SPREADSHEET_ID` en Render |
| `CP_REPORTS_FOLDER_ID` | Valor actual de `GOOGLE_DRIVE_REPORTS_FOLDER_ID` en Render |
| `CP_API_SECRET` | Secreto aleatorio nuevo generado localmente |

No uses una hoja ni una carpeta nuevas. Copia los IDs existentes desde Render > Environment, sin enviarlos en el chat.

Para crear el secreto en Windows PowerShell:

```powershell
$bytes = New-Object byte[] 48
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$rng.GetBytes($bytes)
$secret = [Convert]::ToBase64String($bytes)
$secret
```

Guárdalo localmente. Lo colocarás en Apps Script como `CP_API_SECRET` y en Render como `GOOGLE_APPS_SCRIPT_SECRET`. No lo compartas.

5. En la lista de funciones, selecciona `authorizeControlPesquero` y pulsa Ejecutar. Acepta los permisos de Sheets y Drive para `pescareporte@gmail.com`. Esta función solo abre la hoja y la carpeta configuradas; no crea ni modifica registros.
6. El código de esta versión conserva las filas vacías intermedias al leer la hoja, para que las actualizaciones apunten a la fila física correcta. También evita crear pestañas o encabezados automáticamente al iniciar Flask.
7. Para la primera publicación: Implementar > Nueva implementación > Aplicación web. Para actualizar una publicación ya existente: Implementar > Gestionar implementaciones > Editar (lápiz) > Versión nueva > Implementar. Así se conserva la misma URL `/exec`.
   - Ejecutar como: **Yo (`pescareporte@gmail.com`)**.
   - Quién tiene acceso: **Cualquier usuario / Anyone (incluso anónimo)**, si esa opción está disponible. Es necesaria porque Render no puede iniciar sesión en tu navegador. La clave privada valida cada solicitud.
8. Copia la URL terminada en `/exec` y mantenla privada.
9. Abre la URL en el navegador; debe mostrar un JSON indicando que el servicio está activo.

Si no aparece la opción de acceso anónimo, detente y no elijas una alternativa a ciegas.

## Paso B. Preparar la copia adaptada

1. Descomprime `CONTROL-PESQUERO-migracion-Apps-Script.zip` en una carpeta distinta a la copia original.
2. No sustituyas todavía el código conectado a Render.
3. Verifica que `google_apps_script/Code.gs` y `google_apps_script/appsscript.json` estén incluidos.

## Paso C. Prueba técnica antes de producción

El servidor Flask requiere estas dos variables nuevas:

- `GOOGLE_APPS_SCRIPT_URL`: URL `/exec` obtenida en el despliegue.
- `GOOGLE_APPS_SCRIPT_SECRET`: el secreto local configurado como `CP_API_SECRET`.

Se conservan los valores existentes de `GOOGLE_SPREADSHEET_ID`, `GOOGLE_DRIVE_ROOT_FOLDER_ID` y `GOOGLE_DRIVE_REPORTS_FOLDER_ID`. El código usa el ID de hoja y el ID de carpeta REPORTES que se guardan como propiedades de Apps Script.

Antes de publicar, probar en una copia o entorno de prueba:

1. `ping`: comprueba que el script ve la hoja y la carpeta de reportes existentes.
2. Lectura de pestañas: `EMBARCACIONES`, `INGRESO_PESCA`, `VALORIZACION_PESCA`, `DESPACHO_HIELO`, `GASTOS_ESTADIA`, `AUDITORIA`.
3. Escritura: usar un registro de prueba claramente identificado en una hoja de prueba o copia del spreadsheet; no hacer pruebas de escritura con operaciones reales.
4. Reporte: subir un PDF de prueba en una carpeta temporal y verificar que se crea en Drive; eliminar solo ese archivo de prueba.
5. Cuando todo pase, realizar el despliegue coordinado en Render y comprobar cada módulo.

## Cuotas y costo

No se incorpora ningún servicio de pago. Apps Script tiene cuotas gratuitas para cuentas personales; Google publica límites diarios y un tiempo máximo de ejecución de seis minutos por ejecución. Las cuotas pueden cambiar y, al excederse, las llamadas fallan hasta que se restablezca la cuota. Render Free también puede suspender el servicio por inactividad. Por tanto, el costo adicional puede mantenerse en cero mientras se permanezca dentro de los planes y cuotas gratuitos, pero no se garantiza disponibilidad ilimitada.

Cuotas oficiales: https://developers.google.com/apps-script/guides/services/quotas
Guía oficial de Web Apps: https://developers.google.com/apps-script/guides/web
