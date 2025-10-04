// Anna — empathisch & dynamisch intake-gesprek, gekoppeld aan jouw Render-backend (SerpAPI-only)

const qs = (s, el=document) => el.querySelector(s);
const qsa = (s, el=document) => [...el.querySelectorAll(s)];
const TPL = qs('#tplBubble').content.firstElementChild;

const state = {
  step: -1,
  answers: {
    geslacht: null,          // "man" | "vrouw"
    leeftijd: null,          // vrije tekst/nummer
    lengte: null,            // cm (optioneel)
    land: "NL",              // land/regio
    maten: null,             // vrije tekst (optioneel)
    gelegenheid: null,       // purpose
    gevoel: null,            // gewenste vibe
    voorkeuren: null,        // kleuren/materialen/silhouet
    praktisch: null,         // eisen (mobiliteit, weer, onderhoud)
    budget_total: 250,       // default
    styles: [],              // afgeleid uit gevoel/voorkeuren
  },
  apiBase: localStorage.getItem("apiBase") || "https://anna-reboot-backend.onrender.com",
  history: []
};

// ---------- UI ----------
function addBubble(html, who="anna"){
  const b = TPL.cloneNode(true);
  b.classList.toggle("anna", who==="anna");
  b.classList.toggle("user", who==="user");
  b.querySelector("p").innerHTML = html;
  qs("#chat").appendChild(b);
  b.scrollIntoView({behavior:"smooth", block:"end"});
}
function addUser(text){ addBubble(escapeHtml(text), "user"); }
function clearChat(){ qs("#chat").innerHTML = ""; }

function chipButtons(values){
  return `<div class="chips">${values.map(v=>`<button class="chip btn chipbtn" data-val="${escapeHtml(v)}" style="cursor:pointer">${escapeHtml(v)}</button>`).join(" ")}</div>`;
}
document.addEventListener("click", (e)=>{
  const btn = e.target.closest(".chipbtn");
  if(btn){
    const val = btn.getAttribute("data-val");
    qs("#userInput").value = val;
    qs("#inputForm").dispatchEvent(new Event("submit", {cancelable:true, bubbles:true}));
  }
});

// ---------- Empathische feedback & parsing ----------
function ack(field, raw){
  const v = (raw||"").trim();
  switch(field){
    case "geslacht":
      return v.startsWith("v") ? "Fijn, ik noteer <strong>vrouw</strong>. Dan let ik extra op pasvormen en proporties die vaak mooi vallen."
                               : "Helder, <strong>man</strong>. Ik houd rekening met pasvormen en verhoudingen die meestal goed werken.";
    case "leeftijd_lengte":
      return "Top, daar kan ik rekening mee houden bij de lengte van broeken, mouwlengtes en silhouet.";
    case "land":
      return `Dank! Ik zoek dan vooral in winkels die leveren in <strong>${escapeHtml(v.toUpperCase())}</strong>.`;
    case "gelegenheid":
      return "Helder — dat geeft richting aan materialen en formaliteit.";
    case "gevoel":
      return `Snap ik. We gaan voor items die dat gevoel oproepen — zonder gedoe.`;
    case "voorkeuren":
      return "Dank! Ik neem je lievelingskleuren en ‘liever niets’ direct mee.";
    case "praktisch":
      return "Handig om te weten. Ik selecteer dingen die daar bij passen (comfort, onderhoud, weer).";
    case "budget":
      return `Prima. Met € ${fmt(Number(v)||state.answers.budget_total)} kan ik 2–3 outfits samenstellen met degelijke kwaliteit.`;
    case "maten":
      return v.toLowerCase()==="skip" ? "Geen probleem — ik kies items met brede maatbeschikbaarheid."
                                      : "Top, ik houd die maten aan waar mogelijk.";
    default: return "";
  }
}

function pickStylesFromText(txt){
  const s = txt.toLowerCase();
  const candidates = ["minimalistisch","casual","klassiek","sportief","creatief","smart","modern","stoer","vrouwelijk","zakelijk"];
  const hit = candidates.filter(c => s.includes(c));
  const map = {smart:"klassiek", modern:"minimalistisch", stoer:"sportief", zakelijk:"klassiek"};
  return [...new Set(hit.map(x => map[x] || x))]
    .filter(x => ["minimalistisch","casual","klassiek","sportief","creatief"].includes(x))
    .slice(0,2);
}

function pickColorsFromText(txt){
  const s = txt.toLowerCase();
  const colors = ["zwart","wit","navy","blauw","denim","grijs","grey","olijf","olive","groen","beige","bruin","camel","steen","stone"];
  return colors.filter(c => s.includes(c))
               .slice(0,3)
               .map(c => c.replace("grey","grijs").replace("olive","olijf"));
}
function pickAccessibility(txt){
  const s = txt.toLowerCase();
  const out = {};
  if(s.includes("elast") || s.includes("stretch")) out.elastic_waist = true;
  if(s.includes("sluiting") || s.includes("rits") || s.includes("makkelijk")) out.easy_closures = true;
  if(s.includes("zacht") || s.includes("comfort")) out.soft_fabrics = true;
  if(s.includes("instap") || s.includes("geen veters")) out.pull_on = true;
  return out;
}
function needsExamples(txt){
  const s = txt.toLowerCase();
  return s.includes("weet niet") || s.includes("geen idee") || s.includes("maakt niet uit") || s === "?" || s === "";
}
function suggestExamplesFor(step){
  switch(step){
    case 3: return chipButtons(["werk","dagelijks","date","bruiloft","feest","vrijetijd"]);
    case 4: return chipButtons(["zeker","rustig","stoer","creatief","minimalistisch","verzorgd"]);
    case 5: return chipButtons(["zwart","navy","wit","olijf","linnen","katoen","wol (liever niet)","geen print"]);
    case 7: return chipButtons(["150","250","400"]);
    default: return "";
  }
}

// ---------- Intake flow ----------
const QUESTIONS = [
  () => `Laten we beginnen. Ben je <strong>man</strong> of <strong>vrouw</strong>? ${chipButtons(["man","vrouw"])}`,
  () => `Dank! Hoe oud ben je? En wat is je <em>lengte</em> (cm)? <span class="small">Globaal antwoord is ook prima.</span>`,
  () => `In welk land/regio bestel je? (bijv. NL, BE, DE, FR).`,
  () => `Voor welke <strong>gelegenheid</strong> zoek je kledingadvies? (werk, dagelijks, event, vrije tijd) ${suggestExamplesFor(3)}`,
  () => `Hoe wil je dat je kleding je laat <strong>voelen</strong>? ${suggestExamplesFor(4)}`,
  () => `Vertel je <strong>voorkeuren</strong>: kleuren/materialen/silhouet die je fijn vindt of juist vermijdt. ${suggestExamplesFor(5)}`,
  () => `Praktisch: leefstijl & <strong>eisen</strong> (mobiliteit, kreukarm, wasbaar, weer, representatief, etc.).`,
  () => `Budget? Typ één <strong>totaalbedrag</strong> in euro's (bijv. 250). ${suggestExamplesFor(7)}`,
  () => `Optioneel: <strong>maten</strong> (confectie/schoen) die ik moet aanhouden? Of typ <em>skip</em>.`
];

function startIntake(){
  state.step = 0;
  clearChat();
  const hello = greeting();
  addBubble(`${hello} Ik stel je een paar korte vragen. Antwoord gewoon in je eigen woorden — ik vat alles samen en maak dan de voorstellen.`, "anna");
  askNext();
}
function greeting(){
  try{
    const h = new Date().getHours();
    if(h < 12) return "Goedemorgen!";
    if(h < 18) return "Goedemiddag!";
    return "Goedenavond!";
  }catch{ return "Hoi!"; }
}

function askNext(){
  if(state.step >= 0 && state.step < QUESTIONS.length){
    addBubble(QUESTIONS[state.step]());
  } else if (state.step === QUESTIONS.length){
    summaryAndConfirm();
  }
}

function handleAnswer(textRaw){
  const t = textRaw.trim();
  if(!t) return;
  addUser(t);
  state.history.push({role:"user", content:t});

  switch(state.step){
    case 0:{
      const v = t.toLowerCase();
      state.answers.geslacht = /vrouw|v|female|f/.test(v) ? "vrouw" : "man";
      addBubble(ack("geslacht", v));
      state.step++; break;
    }
    case 1:{
      // probeer leeftijd + lengte
      const nums = t.match(/\d+/g) || [];
      if(nums.length) {
        state.answers.leeftijd = nums[0];
        if(nums[1]) state.answers.lengte = nums[1];
      } else {
        state.answers.leeftijd = t;
      }
      addBubble(ack("leeftijd_lengte", t));
      state.step++; break;
    }
    case 2:{
      state.answers.land = t.slice(0,2).toUpperCase();
      addBubble(ack("land", state.answers.land));
      state.step++; break;
    }
    case 3:{
      if(needsExamples(t)){
        addBubble(`Geen zorgen — kies er gerust één uit: ${suggestExamplesFor(3)}`);
        return; // opnieuw zelfde stap
      }
      state.answers.gelegenheid = t;
      addBubble(ack("gelegenheid", t));
      state.step++; break;
    }
    case 4:{
      if(needsExamples(t)){
        addBubble(`Wat lijkt je fijn qua gevoel? Bijvoorbeeld: ${suggestExamplesFor(4)}`);
        return;
      }
      state.answers.gevoel = t;
      // stijlafleiding
      state.answers.styles = pickStylesFromText(t);
      addBubble(ack("gevoel", t));
      state.step++; break;
    }
    case 5:{
      if(needsExamples(t)){
        addBubble(`Geen punt — kies gerust een paar: ${suggestExamplesFor(5)}`);
        return;
      }
      state.answers.voorkeuren = t;
      state.answers.styles = [...new Set([...state.answers.styles, ...pickStylesFromText(t)])].slice(0,2);
      addBubble(ack("voorkeuren", t));
      state.step++; break;
    }
    case 6:{
      state.answers.praktisch = t;
      addBubble(ack("praktisch", t));
      state.step++; break;
    }
    case 7:{
      if(needsExamples(t)){
        addBubble(`Zeg maar een globaal bedrag (vb. 150, 250 of 400). ${suggestExamplesFor(7)}`);
        return;
      }
      const n = parseFloat(t.replace(",", "."));
      if(!isNaN(n) && n>0) state.answers.budget_total = n;
      addBubble(ack("budget", String(state.answers.budget_total)));
      state.step++; break;
    }
    case 8:{
      if(t.toLowerCase()!=="skip") state.answers.maten = t;
      addBubble(ack("maten", t));
      state.step++; break;
    }
  }

  askNext();
}

function summaryAndConfirm(){
  const a = state.answers;
  const bullets = [
    `• Geslacht: ${a.geslacht || "—"}`,
    `• Leeftijd/lengte: ${a.leeftijd || "—"} / ${a.lengte || "—"} • Land: ${a.land}`,
    `• Gelegenheid: ${a.gelegenheid || "—"} • Gevoel: ${a.gevoel || "—"}`,
    `• Voorkeuren: ${a.voorkeuren || "—"}`,
    `• Praktisch: ${a.praktisch || "—"}`,
    `• Budget totaal: € ${fmt(a.budget_total)} • Stijl(en): ${(a.styles||[]).join(", ")||"—"}`,
    a.maten ? `• Maten: ${a.maten}` : null
  ].filter(Boolean).join("<br>");

  addBubble(`<div class="panel sum"><strong>Samenvatting</strong><br>${bullets}</div>`);
  addBubble(`Klaar voor 2–3 concrete outfits? Typ <strong>ja</strong> om te starten.`, "anna");

  state.step++; // wacht op "ja"
}

function maybeGenerate(text){
  if(state.step === QUESTIONS.length+1){
    const v = text.trim().toLowerCase();
    if(v.startsWith("j")){
      generateOutfits();
      return true;
    }else{
      addBubble(`Geen probleem. Zeg het maar wanneer je klaar bent met <strong>ja</strong>.`, "anna");
      return true;
    }
  }
  return false;
}

// ---------- Generate ----------
async function generateOutfits(){
  addBubble(`Top — ik ga voor je aan de slag ✅ Een momentje…`, "anna");

  const a = state.answers;
  const intake = {
    purpose: a.gelegenheid || "dagelijks",
    styles: (a.styles && a.styles.length) ? a.styles.slice(0,2) : ["casual"],
    gender: a.geslacht === "vrouw" ? "female" : "male",
    fit: "",
    age_range: a.leeftijd ? String(a.leeftijd) : "",
    country: (a.land || "NL").toUpperCase(),
    currency: "EUR",
    budget_total: a.budget_total || 250,
    budget_per_item: null,
    sizes: a.maten ? { raw: a.maten } : null,
    favorite_colors: pickColorsFromText((a.voorkeuren||"") + " " + (a.gevoel||"")),
    materials_avoid: [],
    accessibility: pickAccessibility(a.praktisch || ""),
    sustainability_preference: false
  };

  try{
    const res = await fetch(state.apiBase.replace(/\/+$/,"") + "/api/generate", {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body: JSON.stringify({
        intake,
        mode: "serpapi",
        serpapi_api_key: null,
        outfits_count: 3
      })
    });
    if(!res.ok){
      const e = await res.json().catch(()=>({detail:res.statusText}));
      throw new Error(e.detail || "Onbekende fout");
    }
    const data = await res.json();
    renderOutfits(data);
  }catch(err){
    addBubble(`Hm, dat lukt nu niet. Probeer later opnieuw of check je <strong>Instellingen</strong>.`, "anna");
  }
}

function renderOutfits(data){
  const chat = qs("#chat");

  (data.outfits||[]).forEach((out, idx) => {
    const card = document.createElement("div");
    card.className = "card";

    const h = document.createElement("h3");
    h.textContent = `Outfit ${idx+1}`;
    card.appendChild(h);

    (out.items||[]).forEach(it => {
      const row = document.createElement("div");
      row.className = "item";
      const img = document.createElement("img");
      img.alt = it.title || "item";
      img.src = it.image || "data:image/svg+xml;charset=utf-8," + encodeURIComponent(`<svg xmlns='http://www.w3.org/2000/svg' width='60' height='60'><rect width='100%' height='100%' fill='#0F1420'/></svg>`);
      const col = document.createElement("div");

      const t = document.createElement("div");
      t.innerHTML = `<strong>${escapeHtml(it.title||"—")}</strong> <span class="label">(${it.category})</span>`;

      const m = document.createElement("div");
      m.className = "small";
      const shop = it.merchant ? ` • ${escapeHtml(it.merchant)}` : "";
      const url = it.link || "#";
      m.innerHTML = `€ ${fmt(it.price)}${shop} — <a href="${url}" target="_blank" rel="noopener">bekijk</a>`;

      col.appendChild(t); col.appendChild(m);
      row.appendChild(img); row.appendChild(col);
      card.appendChild(row);
    });

    const tot = document.createElement("div");
    tot.className = "total";
    tot.innerHTML = `<span class="label">Totaal</span><strong>€ ${fmt(out.total||0)}</strong>`;
    card.appendChild(tot);

    chat.appendChild(card);
  });

  if(data.explanation) addBubble(`Waarom dit werkt: ${escapeHtml(data.explanation)}`, "anna");
  if(data.palette?.colors?.length) addBubble(`Palet: ${data.palette.colors.slice(0,4).join(", ")}.`, "anna");
  addBubble(`Onthoud: ik ben onafhankelijk — geen affiliate of commissies.`, "anna");

  // afsluiter
  addBubble(`Wil je meer alternatieven zien (goedkoper/duurzamer/chiquer), of zal ik hier een <strong>complete shoppinglijst</strong> met maatadvies van maken?`, "anna");
}

// ---------- Utils ----------
function fmt(n){
  try{
    return new Intl.NumberFormat("nl-NL",{minimumFractionDigits:2, maximumFractionDigits:2}).format(Number(n||0));
  }catch{ return String(n) }
}
function escapeHtml(str){
  return String(str).replace(/[&<>"']/g, m => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#039;"}[m]));
}

// ---------- Settings ----------
const modal = qs("#settings");
qs("#btnSettings").addEventListener("click", ()=> {
  qs("#apiBase").value = state.apiBase;
  modal.classList.add("show");
});
qs("#closeSettings").addEventListener("click", ()=> modal.classList.remove("show"));
qs("#saveSettings").addEventListener("click", ()=> {
  state.apiBase = qs("#apiBase").value || state.apiBase;
  localStorage.setItem("apiBase", state.apiBase);
  modal.classList.remove("show");
  addBubble("Instellingen opgeslagen ✅", "anna");
});

// ---------- Input & start ----------
qs("#btnStart").addEventListener("click", startIntake);

qs("#inputForm").addEventListener("submit", (e)=>{
  e.preventDefault();
  const val = qs("#userInput").value;
  if(!val.trim()) return;
  if(maybeGenerate(val)) { qs("#userInput").value=""; return; }
  handleAnswer(val);
  qs("#userInput").value="";
});

startIntake(); // automatisch starten
