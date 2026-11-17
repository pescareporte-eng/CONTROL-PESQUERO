/**
 * CONTROL-PESQUERO - puente privado entre Render y Google Sheets/Drive.
 * Ejecutar como la cuenta propietaria de los archivos y permitir acceso anónimo.
 * Cada solicitud POST se valida con un secreto aleatorio en Script Properties.
 */

const PROP_SECRET = 'CP_API_SECRET';
const PROP_SPREADSHEET_ID = 'CP_SPREADSHEET_ID';
const PROP_REPORTS_FOLDER_ID = 'CP_REPORTS_FOLDER_ID';
const ALLOWED_TABS = [
  'EMBARCACIONES',
  'INGRESO_PESCA',
  'VALORIZACION_PESCA',
  'DESPACHO_HIELO',
  'GASTOS_ESTADIA',
  'AUDITORIA'
];

/** Ejecutar manualmente para comprobar el acceso a la hoja y carpeta actuales. */
function authorizeControlPesquero() {
  const ss = spreadsheet_();
  const folder = reportsFolder_();
  Logger.log('Autorización lista. Hoja: ' + ss.getName() + ' | Carpeta: ' + folder.getName());
}

function doGet() {
  return jsonOutput_({
    ok: true,
    service: 'control-pesquero-google-bridge',
    message: 'Usa POST para las operaciones.'
  });
}

function doPost(e) {
  try {
    if (!e || !e.postData || !e.postData.contents) {
      return jsonOutput_({ ok: false, error: 'Solicitud vacía.' });
    }
    const body = JSON.parse(e.postData.contents);
    const expected = PropertiesService.getScriptProperties().getProperty(PROP_SECRET) || '';
    const supplied = String(body.secret || '');
    if (!expected || !constantTimeEquals_(expected, supplied)) {
      return jsonOutput_({ ok: false, error: 'No autorizado.' });
    }

    const action = String(body.action || '');
    let data;
    switch (action) {
      case 'ping':
        data = withScriptLock_(function () {
          const ss = spreadsheet_();
          const folder = reportsFolder_();
          return {
            service: 'control-pesquero-google-bridge',
            status: 'ready',
            spreadsheet: ss.getName(),
            reports_folder: folder.getName()
          };
        });
        break;
      case 'get_all':
        data = getAll_(String(body.tab || ''));
        break;
      case 'append':
        data = withScriptLock_(function () {
          return appendRow_(String(body.tab || ''), body.item || {});
        });
        break;
      case 'update_row':
        data = withScriptLock_(function () {
          return updateRow_(String(body.tab || ''), Number(body.row_number), body.changes || {});
        });
        break;
      case 'upload_report':
        data = withScriptLock_(function () { return uploadReport_(body); });
        break;
      default:
        throw new Error('Operación no permitida.');
    }
    return jsonOutput_({ ok: true, data: data === undefined ? null : data });
  } catch (err) {
    return jsonOutput_({ ok: false, error: String(err && err.message ? err.message : err) });
  }
}

function jsonOutput_(value) {
  return ContentService.createTextOutput(JSON.stringify(value))
    .setMimeType(ContentService.MimeType.JSON);
}

function constantTimeEquals_(a, b) {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

function withScriptLock_(callback) {
  const lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    return callback();
  } finally {
    lock.releaseLock();
  }
}

function spreadsheet_() {
  const id = PropertiesService.getScriptProperties().getProperty(PROP_SPREADSHEET_ID);
  if (!id) throw new Error('Falta configurar CP_SPREADSHEET_ID en las propiedades del proyecto.');
  return SpreadsheetApp.openById(id);
}

function reportsFolder_() {
  const id = PropertiesService.getScriptProperties().getProperty(PROP_REPORTS_FOLDER_ID);
  if (!id) throw new Error('Falta configurar CP_REPORTS_FOLDER_ID en las propiedades del proyecto.');
  return DriveApp.getFolderById(id);
}

function checkedSheet_(tabName) {
  if (ALLOWED_TABS.indexOf(tabName) === -1) {
    throw new Error('Pestaña no permitida: ' + tabName);
  }
  const sheet = spreadsheet_().getSheetByName(tabName);
  if (!sheet) throw new Error('No existe la pestaña permitida: ' + tabName);
  return sheet;
}

/**
 * Devuelve una entrada por cada fila física de la hoja (incluidas las vacías
 * intermedias), para que el número de fila siga coincidiendo con Google Sheets.
 */
function getAll_(tabName) {
  const sheet = checkedSheet_(tabName);
  const values = sheet.getDataRange().getDisplayValues();
  if (!values || values.length < 2) return [];
  const headers = values[0];
  return values.slice(1).map(function (row) {
    const item = {};
    headers.forEach(function (header, index) {
      if (header !== '') item[header] = String(row[index] === undefined ? '' : row[index]);
    });
    return item;
  });
}

function appendRow_(tabName, item) {
  const sheet = checkedSheet_(tabName);
  const lastColumn = sheet.getLastColumn();
  if (lastColumn < 1) throw new Error('La pestaña no tiene encabezados: ' + tabName);
  const headers = sheet.getRange(1, 1, 1, lastColumn).getDisplayValues()[0];
  const row = headers.map(function (header) {
    const value = item[header];
    return value === undefined || value === null ? '' : String(value);
  });
  sheet.appendRow(row);
  return { row_number: sheet.getLastRow() };
}

function updateRow_(tabName, rowNumber, changes) {
  const sheet = checkedSheet_(tabName);
  if (!Number.isInteger(rowNumber) || rowNumber < 2 || rowNumber > sheet.getLastRow()) {
    throw new Error('Número de fila no válido para actualizar.');
  }
  const lastColumn = sheet.getLastColumn();
  if (lastColumn < 1) throw new Error('La pestaña no tiene encabezados.');
  const headers = sheet.getRange(1, 1, 1, lastColumn).getDisplayValues()[0];
  headers.forEach(function (header, index) {
    if (header !== '' && Object.prototype.hasOwnProperty.call(changes, header)) {
      // Actualiza solo las columnas solicitadas; así se conservan fórmulas
      // y celdas no modificadas de esa misma fila.
      const value = changes[header] === null || changes[header] === undefined
        ? ''
        : String(changes[header]);
      sheet.getRange(rowNumber, index + 1).setValue(value);
    }
  });
  const updatedValues = sheet.getRange(rowNumber, 1, 1, lastColumn).getDisplayValues()[0];
  const updated = {};
  headers.forEach(function (header, index) {
    if (header !== '') updated[header] = String(updatedValues[index] === undefined ? '' : updatedValues[index]);
  });
  return updated;
}

function findOrCreateFolder_(parent, name) {
  const folderName = String(name || '').trim();
  if (!folderName || folderName === '.' || folderName === '..') {
    throw new Error('Nombre de carpeta no válido.');
  }
  const matches = parent.getFoldersByName(folderName);
  return matches.hasNext() ? matches.next() : parent.createFolder(folderName);
}

function uploadReport_(body) {
  const filename = String(body.filename || '').trim();
  const mimeType = String(body.mime_type || 'application/octet-stream');
  const year = String(body.year || '').trim();
  const category = String(body.category || '').trim();
  const encoded = String(body.content_base64 || '');
  if (!filename || !year || !category || !encoded) {
    throw new Error('Faltan datos para guardar el reporte.');
  }
  // El tamaño máximo de la aplicación Python es 8 MB; esta protección evita
  // solicitudes excesivamente grandes si el servicio se utiliza por separado.
  if (encoded.length > 12 * 1024 * 1024) {
    throw new Error('El reporte supera el tamaño admitido por esta conexión.');
  }
  const root = reportsFolder_();
  const yearFolder = findOrCreateFolder_(root, year);
  const categoryFolder = findOrCreateFolder_(yearFolder, category);
  const bytes = Utilities.base64Decode(encoded);
  const blob = Utilities.newBlob(bytes, mimeType, filename);
  const file = categoryFolder.createFile(blob);
  return { id: file.getId(), name: file.getName(), url: file.getUrl() };
}

/** Pruebas manuales de solo lectura; no alteran datos. */
function probarPuenteControlPesquero() {
  const secret = PropertiesService.getScriptProperties().getProperty(PROP_SECRET);
  if (!secret) throw new Error('Falta configurar CP_API_SECRET.');
  const result = JSON.parse(doPost({
    postData: { contents: JSON.stringify({ secret: secret, action: 'ping' }) }
  }).getContent());
  if (!result.ok) throw new Error(result.error || 'Falló ping.');
  Logger.log('PRUEBA DE CONEXIÓN CORRECTA');
  Logger.log(JSON.stringify(result.data));
}

function probarLecturaEmbarcaciones() {
  const secret = PropertiesService.getScriptProperties().getProperty(PROP_SECRET);
  if (!secret) throw new Error('Falta configurar CP_API_SECRET.');
  const result = JSON.parse(doPost({
    postData: { contents: JSON.stringify({ secret: secret, action: 'get_all', tab: 'EMBARCACIONES' }) }
  }).getContent());
  if (!result.ok) throw new Error(result.error || 'Falló lectura.');
  const count = Array.isArray(result.data) ? result.data.length : 0;
  Logger.log('LECTURA CORRECTA');
  Logger.log('Filas de EMBARCACIONES (incluye filas vacías intermedias): ' + count);
}
