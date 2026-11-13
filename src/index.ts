import path from "node:path";
import { createApp, reportFile } from "./app";
import { gercekCalistirici } from "./analiz";

const port = Number(process.env.PORT) || 3000;
const dataDir = path.resolve(process.env.DATA_DIR?.trim() || "./data");
const uploadToken = process.env.UPLOAD_TOKEN?.trim();
const viewPassword = process.env.VIEW_PASSWORD?.trim();

if (!uploadToken || uploadToken.length < 32) console.warn("UYARI: UPLOAD_TOKEN yok ya da 32 karakterden kısa: PUT /api/paketrapor yüklemesi kapalı/çalışmaz.");
if (!viewPassword || viewPassword.length < 12) console.warn("UYARI: VIEW_PASSWORD yok ya da 12 karakterden kısa: rapor sayfası ve fatura yükleme kapalı.");

const analizCalistir = gercekCalistirici({
  dataDir,
  reportPath: reportFile(dataDir),
  pythonBin: process.env.PYTHON_BIN?.trim() || undefined,
  analizDir: process.env.ANALIZ_DIR?.trim() || undefined,
});

createApp({ dataDir, uploadToken, viewPassword, viewUser: process.env.VIEW_USER, analizCalistir }).listen(port, "0.0.0.0", () => {
  console.log(`delrep dinliyor: :${port}, veri klasörü: ${dataDir}`);
});
