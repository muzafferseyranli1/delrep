/** Fatura yükleme sayfası (/yukle). Dış kaynak yok; yalnız kendi sunucusuna istek atabilir. */
export const YUKLE_CSP =
  "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; img-src data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'";

export const YUKLE_HTML = `<!doctype html>
<html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Fatura yükle</title>
<style>
:root{--bg:#f6f7f9;--kart:#fff;--yazi:#1c2026;--soluk:#68707c;--cizgi:#dde1e7;--vurgu:#2f5fd0;--vurgu-y:#fff;--iyi:#1c7a43;--kotu:#b3261e;--uyari:#8a5a00}
@media (prefers-color-scheme:dark){:root{--bg:#14171b;--kart:#1d2228;--yazi:#e8ebef;--soluk:#97a0ac;--cizgi:#303741;--vurgu:#6d96f0;--vurgu-y:#101419;--iyi:#58c486;--kotu:#f08c85;--uyari:#e0b050}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--yazi);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:860px;margin:0 auto;padding:20px 16px 48px}
h1{font-size:22px;margin:0 0 4px}p.alt{color:var(--soluk);margin:0 0 18px}
a{color:var(--vurgu)}
.kart{background:var(--kart);border:1px solid var(--cizgi);border-radius:10px;padding:16px;margin-bottom:16px}
#birak{border:2px dashed var(--cizgi);border-radius:10px;padding:28px 16px;text-align:center;cursor:pointer}
#birak.uzerinde{border-color:var(--vurgu)}
button{font:inherit;border:1px solid var(--cizgi);background:var(--kart);color:var(--yazi);border-radius:8px;padding:8px 14px;cursor:pointer}
button.ana{background:var(--vurgu);color:var(--vurgu-y);border-color:var(--vurgu)}
button:disabled{opacity:.5;cursor:default}
ul#durum{list-style:none;padding:0;margin:12px 0 0}ul#durum li{padding:3px 0;font-size:14px;overflow-wrap:anywhere}
.iyi{color:var(--iyi)}.kotu{color:var(--kotu)}.uyari{color:var(--uyari)}
table{width:100%;border-collapse:collapse;font-size:14px}th,td{text-align:left;padding:7px 6px;border-bottom:1px solid var(--cizgi);overflow-wrap:anywhere}
th{color:var(--soluk);font-weight:600}td.sag,th.sag{text-align:right;white-space:nowrap}
.rozet{font-size:12px;border:1px solid var(--cizgi);border-radius:999px;padding:1px 8px;color:var(--soluk);white-space:nowrap}
.satir{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.bosluk{flex:1}
</style></head><body><main>
<h1>Rapor dosyalarını yükle</h1>
<p class="alt">Trendyol Go ve Yemeksepeti panellerinden indirdiğiniz dosyaları yükleyin (.xlsx, .csv ya da bunları içeren .zip). Dosya adının önemi yok: hangi rapor olduğu içeriğinden anlaşılır. Aynı dosyayı ya da tarihleri çakışan dosyaları yüklemek sorun değil; aynı kayıt için en son yüklenen kullanılır. Yüklemeden sonra rapor yeniden hesaplanır. <a href="/">Raporu aç</a></p>

<details class="kart"><summary><strong>Her hafta hangi dosyalar?</strong></summary>
<p><b>Trendyol Go</b> (her mağaza için): komisyon fatura detayı (yeni kesilen haftalık fatura), kapıda ödeme komisyon detayları (yeni kesilenler), fatura listesi, reklam raporu, değerlendirmeler.</p>
<p><b>Yemeksepeti</b>: sipariş listesi, fatura özeti (her mağaza için), günlük performans, değerlendirmeler; isteğe bağlı ürün satışları.</p>
<p class="alt" style="margin:0">Trendyol haftalık faturası haftanın bitiminden sonraki gün kesilir; o fatura gelmeden son hafta rapora girmez.</p>
</details>

<div class="kart">
  <div id="birak" tabindex="0" role="button">Dosyaları buraya bırakın ya da seçmek için tıklayın<br><small style="color:var(--soluk)">.xlsx, .csv ve .zip, birden çok dosya seçilebilir</small></div>
  <input id="sec" type="file" multiple accept=".xlsx,.csv,.zip" hidden>
  <ul id="durum" aria-live="polite"></ul>
</div>

<div class="kart">
  <div class="satir"><strong>Saklanan dosyalar</strong><span id="ozet" class="rozet"></span><span class="bosluk"></span>
    <button id="analizBtn" class="ana">Raporu yeniden hesapla</button></div>
  <p id="analizDurum" class="alt" style="margin:8px 0 0"></p>
  <table style="margin-top:10px"><thead><tr><th>Dosya</th><th class="sag">Boyut</th><th>Tarih</th><th></th></tr></thead><tbody id="liste"></tbody></table>
  <p id="bos" class="alt" hidden style="margin-top:12px">Henüz dosya yüklenmedi.</p>
</div>

<script>
(function(){
  var H={"X-Requested-With":"delrep"};
  var $=function(i){return document.getElementById(i)};
  var meşgul=false;
  function not(metin,sinif){var li=document.createElement("li");li.textContent=metin;if(sinif)li.className=sinif;$("durum").appendChild(li);return li}
  function boyut(b){return b>1048576?(b/1048576).toFixed(1)+" MB":Math.max(1,Math.round(b/1024))+" KB"}
  function tarih(s){return new Date(s).toLocaleString("tr-TR")}
  async function json(r){try{return await r.json()}catch(e){return {}}}

  async function listele(){
    var r=await fetch("/api/dosyalar",{headers:H});
    var v=await json(r);var d=v.dosyalar||[];
    var g=$("liste");g.textContent="";
    d.forEach(function(f){
      var tr=document.createElement("tr");
      var a=document.createElement("td");a.textContent=f.ad;
      var z=document.createElement("span");z.className="rozet";z.style.marginLeft="8px";
      if(!f.durum){z.textContent="henüz analiz edilmedi"}
      else if(f.durum==="okundu"){z.textContent=f.tur||"okundu";z.classList.add("iyi")}
      else{z.textContent=(f.tur?f.tur+": ":"")+f.durum;if(/tanınmadı|okunamadı/.test(f.durum))z.classList.add("kotu")}
      a.appendChild(document.createElement("br"));a.appendChild(z);z.style.marginLeft="0"
      var b=document.createElement("td");b.className="sag";b.textContent=boyut(f.bayt);
      var t=document.createElement("td");t.textContent=tarih(f.tarih);
      var s=document.createElement("td");s.className="sag";
      var btn=document.createElement("button");btn.textContent="Sil";
      btn.onclick=async function(){
        if(!confirm(f.ad+" silinsin mi?"))return;
        var rr=await fetch("/api/dosyalar/"+encodeURIComponent(f.ad),{method:"DELETE",headers:H});
        if(!rr.ok){alert("Silinemedi.");return}
        await listele();
      };
      s.appendChild(btn);tr.append(a,b,t,s);g.appendChild(tr);
    });
    var okunan=d.filter(function(f){return f.durum==="okundu"}).length;
    $("ozet").textContent=d.length+" dosya, "+okunan+" tanesi analizde kullanıldı";
    $("bos").hidden=d.length>0;
  }

  async function analiz(){
    $("analizDurum").textContent="Rapor hesaplanıyor...";
    $("analizDurum").className="alt";
    try{
      var r=await fetch("/api/analiz",{method:"POST",headers:H});
      var v=await json(r);
      $("analizDurum").textContent=(v.ok?"Rapor güncellendi: ":"Rapor üretilemedi: ")+(v.mesaj||v.error||"");
      $("analizDurum").className="alt "+(v.ok?"iyi":"kotu");
    }catch(e){$("analizDurum").textContent="Rapor isteği başarısız.";$("analizDurum").className="alt kotu"}
  }

  async function yukle(dosyalar){
    if(meşgul||!dosyalar.length)return;
    meşgul=true;$("analizBtn").disabled=true;$("durum").textContent="";
    var basarili=0;
    for(var i=0;i<dosyalar.length;i++){
      var f=dosyalar[i];var li=not(f.name+" yükleniyor...");
      try{
        var r=await fetch("/api/dosyalar/"+encodeURIComponent(f.name),{method:"PUT",headers:Object.assign({"Content-Type":"application/octet-stream"},H),body:f});
        var v=await json(r);
        if(r.ok){
          var n=(v.kaydedilen||[]).length,zv=(v.zatenVar||[]).length;if(n)basarili++;
          var parca=[];if(n)parca.push(n+" dosya kaydedildi");if(zv)parca.push(zv+" dosya zaten yüklüydü");if(v.atlanan)parca.push(v.atlanan+" dosya .xlsx/.csv olmadığı için atlandı");
          li.textContent=f.name+": "+parca.join(", ");li.className=v.atlanan?"uyari":"iyi"}
        else{li.textContent=f.name+": "+(v.error||"yüklenemedi");li.className="kotu"}
      }catch(e){li.textContent=f.name+": bağlantı hatası";li.className="kotu"}
    }
    await listele();
    if(basarili)await analiz();
    meşgul=false;$("analizBtn").disabled=false;
  }

  var birak=$("birak"),sec=$("sec");
  birak.onclick=function(){sec.click()};
  birak.onkeydown=function(e){if(e.key==="Enter"||e.key===" "){e.preventDefault();sec.click()}};
  sec.onchange=function(){yukle(Array.from(sec.files));sec.value=""};
  ["dragenter","dragover"].forEach(function(o){birak.addEventListener(o,function(e){e.preventDefault();birak.classList.add("uzerinde")})});
  ["dragleave","drop"].forEach(function(o){birak.addEventListener(o,function(e){e.preventDefault();birak.classList.remove("uzerinde")})});
  birak.addEventListener("drop",function(e){yukle(Array.from(e.dataTransfer.files))});
  $("analizBtn").onclick=async function(){if(meşgul)return;meşgul=true;$("analizBtn").disabled=true;await analiz();meşgul=false;$("analizBtn").disabled=false};
  listele();
})();
</script></main></body></html>`;
