export const MAX_PDF_BYTES = 20 * 1024 * 1024;

export function formatFileSize(bytes) {
  const value = Number(bytes) || 0;
  if (value >= 1024 * 1024) return `${(value / (1024 * 1024)).toFixed(1)} MB`;
  if (value >= 1024) return `${Math.round(value / 1024)} KB`;
  return `${value} B`;
}

/** Mensaje de error si el archivo no sirve como adjunto (el backend vuelve a validar), o "". */
export function validatePdfFile(file) {
  if (!file) return "Selecciona un archivo.";
  const isPdf = /\.pdf$/i.test(file.name || "");
  if (!isPdf) return "Solo se permiten archivos PDF.";
  if (!file.size) return "El archivo esta vacio.";
  if (file.size > MAX_PDF_BYTES) return `El archivo supera el maximo de ${MAX_PDF_BYTES / (1024 * 1024)} MB.`;
  return "";
}
