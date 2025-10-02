/** Anna — Reboot MVP: 1 vraag per bericht, NL/BE, directe productlinks **/

const qs = (sel, el=document) => el.querySelector(sel);
const BUBBLE = qs("#bubbleTemplate").content.firstElementChild;

const state = {
  step: 1, // 1..6 intake
  pendingConfirm: false,
  apiBase: localStorage.getItem("apiBase") || "http://localhost:8000",
  intake: {
    purpose: "", styles: [], gender: "unisex", fit: "",
    age_range: "", country: "NL", currency: "EUR",
    budget_total: 250, budget_per_item: null,
    sizes: {}, favorite_colors: [], materials_avoid: [],
    accessibility: {}, sustainability_preference: false
  },
  notes: { occasion:"", feeling:"", prefs:"", practical:"", extra:"" },
};

function addBubble(html, who="anna"){
  const b = BUBBLE.cloneNode(true);
  b.classList.add(who);
  b.querySelector("p").innerHTML = html;
  qs("#chat").appendChild(b);
  b.scrollIntoView({behavior:"smooth", block:"end"});
}
function addUser(text){ addBubble(escapeHtml(text), "user"); }
function escapeHtml(str){ return String(str).replace(/[&<>\"']/g, m => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#039;"}[m])); }

function ask(){
  const s = state.step;
  if(state.pendingConfirm){ addBubble("Klinkt dit goed? Antwoord met <strong>ja</strong> of geef aan wat je wilt aanpassen."); return; }
  switch(s){
    case 1: addBubble("🔹 <strong>Algemeen</strong> — noem je <em>geslacht</em>, <em>leeftijd</em>, <em>lengte</em>, <em>land/regio</em> (bv. NL) en (optioneel) <em>maten</em> (bv. boven L, broek 50, schoen 43)."); break;
    case 2: addBubble("🔹 <strong>Occasion</strong> — voor welke gelegenheid zoek je kledingadvies?"); break;
    case 3: addBubble("🔹 <strong>Gevoel</strong> — hoe wil je dat je kleding je laat voelen?"); break;
    case 4: addBubble("🔹 <strong>Voorkeuren</strong> — kleuren/materialen/silhouet die je fijn vindt of vermijdt."); break;
    case 5: addBubble("🔹 <strong>Praktisch</strong> — leefstijl & eisen (mobiliteit, kreukarm, wasbaar, weer)."); break;
    case 6: addBubble("🔹 <strong>Extra</strong> — budget per item/totaal en evt. pasvorm/dresscode."); break;
    default: summarizeAndConfirm();
  }
}

function parseInput(text){
  const t = text.trim();
  if(!t) return;
  if(state.pendingConfirm){
    if(/^j(a|aa)?$/i.test(t)) return generateOutfits();
    addBubble("Helder — pas gerust aan wat je wilt. Zeg <strong>ja</strong> zodra je klaar bent.");
    return;
  }
  const s = state.step;
  addUser(text);

  switch(s){
    case 1: parseGeneral(t); break;
    case 2: state.notes.occasion = t; state.intake.purpose = t.toLowerCase(); break;
    case 3: state.notes.feeling = t; break;
    case 4: parsePrefs(t); break;
    case 5: state.notes.practical = t; parseAccessibility(t); break;
    case 6: parseExtra(t); break;
  }
  state.step++;
  if(state.step===7) summarizeAndConfirm(); else ask();
}

function parseGeneral(t){
  const lower = t.toLowerCase();
  if(/\b(vrouw|female)\b/.test(lower)) state.intake.gender = "female";
  else if(/\b(man|male)\b/.test(lower)) state.intake.gender = "male";
  else state.intake.gender = "unisex";

  const age = (t.match(/\b(\d{2})\b/)||[])[1];
  if(age){
    const a = parseInt(age,10);
    state.intake.age_range = a<=25 ? "18–25" : a<=35 ? "26–35" : a<=45 ? "36–45" : a<=55 ? "46–55" : "56+";
  }
  if(/\bnl|nederland\b/.test(lower)) state.intake.country="NL";
  else if(/\bbe|belgi(ë|e)\b/.test(lower)) state.intake.country="BE";

  const sizes = {};
  const broek = lower.match(/broek\w*\D+(\d{2,3}(?:\/\d{2})?)/); if(broek) sizes.bottom = broek[1];
  const boven = lower.match(/boven\w*\D+\b(xs|s|m|l|xl|xxl)\b/); if(boven) sizes.top = boven[1].toUpperCase();
  const schoen = lower.match(/schoen\w*\D+(\d{2,3})/); if(schoen) sizes.shoes = schoen[1];
  if(Object.keys(sizes).length) state.intake.sizes = sizes;
}

function parsePrefs(t){
  state.notes.prefs = t;
  const colors = [];
  const colorWords = ["navy","blauw","denim","zwart","wit","grijs","groen","olijf","beige","bruin","taupe","bordeaux"];
  colorWords.forEach(c => { if(new RegExp(`\\b${c}\\b`,'i').test(t)) colors.push(c); });
  if(colors.length) state.intake.favorite_colors = Array.from(new Set(colors)).slice(0,4);

  if(/\b(slank|slim|getailleerd)\b/i.test(t)) state.intake.fit = "getailleerd";
  else if(/\b(relaxed|wijd|los)\b/i.test(t)) state.intake.fit = "relaxed";
  else if(/\b(recht|regular)\b/i.test(t)) state.intake.fit = "recht";

  const avoid = [];
  if(/\bwol\b/i.test(t)) avoid.push("wol");
  if(/\blatex\b/i.test(t)) avoid.push("latex");
  if(/\bpolyester\b/i.test(t)) avoid.push("polyester");
  if(avoid.length) state.intake.materials_avoid = avoid;
}

function parseAccessibility(t){
  const flags = {
    "elastic waist":"elastic_waist","elastische taille":"elastic_waist",
    "easy closures":"easy_closures","makkelijke sluit":"easy_closures",
    "soft fabrics":"soft_fabrics","zachte stof":"soft_fabrics",
    "pull-on":"pull_on","pull on":"pull_on"
  };
  Object.entries(flags).forEach(([k,v])=>{ if(t.toLowerCase().includes(k)) state.intake.accessibility[v]=true; });
}

function parseExtra(t){
  state.notes.extra = t;
  const euros = t.match(/(\d+[.,]?\d*)/g);
  if(euros && euros.length){
    const val = parseFloat(euros[0].replace(",", "."));
    if(/per\s*item/i.test(t)) state.intake.budget_per_item = val;
    else state.intake.budget_total = val;
  }
  if(/\bslim\b/i.test(t)) state.intake.fit = "getailleerd";
  if(/\brelaxed|los\b/i.test(t)) state.intake.fit = "relaxed";
  if(/\bsmart[- ]?casual|business casual|zakelijk\b/i.test(t)) state.intake.purpose = "smart-casual";
}

function summarizeAndConfirm(){
  if(!state.intake.styles.length){
    const guess = ["casual"]; state.intake.styles = guess;
  }
  const bullets = [
    `Doel/gelegenheid: <strong>${escapeHtml(state.intake.purpose || state.notes.occasion || "dagelijks")}</strong>`,
    `Smaak & pasvorm: <strong>${escapeHtml((state.intake.styles||[]).join(", ")||"casual")}</strong> • ${escapeHtml(state.intake.fit||"recht")}`,
    `Land & budget: <strong>${escapeHtml(state.intake.country)}</strong> • ${fmt€(state.intake.budget_total||250)}`,
    state.intake.favorite_colors?.length ? `Kleuren: ${state.intake.favorite_colors.slice(0,3).join(", ")}` : null
  ].filter(Boolean);
  addBubble(`Samenvatting:<br>• ${bullets.join("<br>• ")}`);
  state.pendingConfirm = true;
  addBubble("Zal ik 2–3 outfits zoeken die je direct online kunt bestellen? Antwoord met <strong>ja</strong>.");
}

async function generateOutfits(){
  state.pendingConfirm = false;
  addBubble("Top — ik ga voor je aan de slag ✅ Een momentje…");
  try{
    const res = await fetch(state.apiBase + "/api/generate", {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({
        intake: state.intake,
        mode: "serpapi",
        serpapi_api_key: null,
        outfits_count: 3
      })
    });
    if(!res.ok){
      const err = await res.json().catch(()=>({detail: res.statusText}));
      throw new Error(err.detail || "Onbekende fout");
    }
    const data = await res.json();
    renderOutfitsAsCards(data);
  }catch(e){
    addBubble("Hm, dit lukt nu niet. Probeer later opnieuw of check je Instellingen.", "anna");
  }
}

function renderOutfitsAsCards(data){
  const badge = document.createElement("div");
  badge.className = "outfits badge";
  badge.textContent = "modus: live via SerpAPI";
  qs("#chat").appendChild(badge);

  (data.outfits||[]).slice(0,3).forEach((out, idx) => {
    const items = (out.items||[]).map(sanitizeItem).filter(onlyDirectProduct);
    const lines = items.map(it => {
      const shop = shopDomain(it.link);
      return [
        `<strong>${escapeHtml(it.title)}</strong> (${escapeHtml(it.role)})`,
        `${fmt€(it.price)} • ${escapeHtml(shop)} — <a href="${it.link}" target="_blank" rel="noopener">bekijk</a>`
      ].join("<br>");
    });

    let total = items.reduce((acc, it)=> acc + (isFinite(it.price)? it.price:0), 0);

    const card = document.createElement("div"); card.className = "card";
    card.innerHTML = `
      <h3>Outfit ${idx+1}</h3>
      ${lines.join("<br>")}
      <div class="total"><span class="label">Totaal</span><strong>${fmt€(total)}</strong></div>
    `;
    qs("#chat").appendChild(card);
  });

  if(data.explanation) addBubble(`Waarom dit werkt: ${escapeHtml(data.explanation)}`);
  if(data.palette?.colors?.length){
    addBubble(`Palet: ${data.palette.colors.slice(0,3).join(", ")}${data.palette.colors[3] ? " + " + data.palette.colors[3] : ""}.`);
  }
  addBubble("Onthoud: ik ben onafhankelijk — geen affiliate of commissies.");
  addBubble("Wil je meer alternatieven zien (goedkoper/duurzamer/chiquer), of zal ik hier een <strong>complete shoppinglijst</strong> met maatadvies van maken? Wil je een <em>veiligere</em> optie of juist iets <em>gedurfder</em>?");
}

function sanitizeItem(raw){
  if(!raw) return null;
  const role = raw.category || raw.role || "accessory";
  let url = (raw.link || "").trim();
  if(!url) return null;
  try{
    const u = new URL(url);
    const bad = ["utm_source","utm_medium","utm_campaign","utm_content","gclid","fbclid","msclkid","aff","affid","cjevent","irclickid","irgwc","_ga","_gl"];
    bad.forEach(k=>u.searchParams.delete(k));
    url = u.origin + u.pathname + (u.searchParams.toString()? "?"+u.searchParams.toString() : "");
  }catch(e){}
  return { role, title: raw.title||"—", price: toNumber(raw.price), link:url, image: raw.image||null };
}
function onlyDirectProduct(it){
  if(!it || !it.link) return false;
  try{
    const u = new URL(it.link);
    const host = u.hostname;
    if(/google\.com|shopping\.google|googleadservices|doubleclick/i.test(host)) return false;
    if(u.pathname === "/" || u.pathname.split("/").filter(Boolean).length < 1) return false;
    return true;
  }catch(e){ return false; }
}
function shopDomain(url){
  try{
    const u = new URL(url);
    const host = u.hostname.replace(/^www\./,"");
    const seg0 = u.pathname.split("/").filter(Boolean)[0] || "";
    if(["nl","be"].includes(seg0.toLowerCase())) return `${host}/${seg0.toLowerCase()}`;
    return host;
  }catch(e){ return "shop"; }
}
function toNumber(v){ if(typeof v==="number") return v; const n = parseFloat(String(v||"").replace(",", ".")); return isNaN(n)?0:n; }
function fmt€(n){ try{ return new Intl.NumberFormat("nl-NL",{style:"currency",currency:"EUR"}).format(n||0); }catch(e){ return `€ ${Number(n||0).toFixed(2).replace(".",",")}`; } }

qs("#inputForm").addEventListener("submit",(e)=>{ e.preventDefault(); const val = qs("#userInput").value; if(!val.trim())return; qs("#userInput").value=""; parseInput(val); });
const modal = qs("#settingsModal");
qs("#settingsBtn").addEventListener("click", ()=>{ modal.classList.remove("hidden"); qs("#apiBase").value = state.apiBase; });
qs("#closeSettings").addEventListener("click", ()=> modal.classList.add("hidden"));
qs("#saveSettings").addEventListener("click", ()=>{ state.apiBase = qs("#apiBase").value || state.apiBase; localStorage.setItem("apiBase", state.apiBase); modal.classList.add("hidden"); addBubble("Instellingen opgeslagen ✅"); });

ask();
