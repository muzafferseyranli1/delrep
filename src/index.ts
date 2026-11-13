import path from "node:path";
import { createApp } from "./app";

const port = Number(process.env.PORT) || 3000;
const dataDir = path.resolve(process.env.DATA_DIR?.trim() || "./data");
const uploadToken = process.env.UPLOAD_TOKEN?.trim();
const viewPassword = process.env.VIEW_PASSWORD?.trim();

if (!uploadToken || uploadToken.length < 32) console.warn("UYARI: UPLOAD_TOKEN yok ya da 32 karakterden kısa: rapor yükleme kapalı/çalışmaz.");
if (!viewPassword || viewPassword.length < 12) console.warn("UYARI: VIEW_PASSWORD yok ya da 12 karakterden kısa: rapor sayfası kapalı.");

createApp({ dataDir, uploadToken, viewPassword, viewUser: process.env.VIEW_USER }).listen(port, "0.0.0.0", () => {
  console.log(`delrep dinliyor: :${port}, veri klasörü: ${dataDir}`);
});
