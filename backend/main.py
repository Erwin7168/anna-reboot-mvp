import os, re, urllib.parse, requests
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Chat (GPT-4o) – verwacht backend/llm.py en backend/prompts/anna_system_nl.md
from llm import chat_anna

load_dotenv()

app = FastAPI(title="Anna Reboot API", version="0.3.1")

# ----------------------------- CORS ---------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # MVP: open. Later beperken naar je Netlify-domein.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------- Pydantic models -------------------------
class Intake(BaseModel):
    purpose: str = Field(..., description="werk, vrije tijd, event, dagelijks, etc.")
    styles: List[str] = Field(default_factory=list, description="max 2 stijlen: minimalistisch, casual, klassiek, sportief, creatief")
    gender: str = Field("unisex", description="male/female/unisex/non-binary")
    fit: Optional[str] = Field(None, description="recht, getailleerd, relaxed")
    age_range: Optional[str] = Field(None, description="18–25, 26–35, 36–45, 46–55, 56+")
    country: str = Field("NL", description="NL, BE, DE, FR, UK, US, etc.")
    currency: Optional[str] = Field(None, description="EUR, GBP, USD (optioneel, afgeleid van land)")
    budget_total: Optional[float] = Field(250, description="Totaalbudget (bijv. 250)")
    budget_per_item: Optional[float] = Field(None, description="Budget per item (optioneel)")
    sizes: Optional[Dict[str, str]] = Field(None, description="maat per categorie (optioneel)")
    favorite_colors: Optional[List[str]] = Field(default_factory=list, description="voorkeurskleuren (0–3)")
    materials_avoid: Optional[List[str]] = Field(default_factory=list, description="materialen/allergieën (optioneel)")
    accessibility: Optional[Dict[str, Any]] = Field(default_factory=dict, description="toegankelijkheidswensen (optioneel)")
    sustainability_preference: Optional[bool] = Field(False, description="zacht criterium: bij voorkeur duurzaam")

class GenerateRequest(BaseModel):
    intake: Intake
    outfits_count: int = Field(3, description="aantal outfits (default 3)")

class ChatReq(BaseModel):
    history: List[Dict[str, str]] = []
    user_message: str
    intake: Optional[Dict[str, Any]] = None  # optioneel; later handig

# --------------------------- Utilities ------------------------------

_STRIP_QUERY_KEYS = {
    "utm_source","utm_medium","utm_campaign","utm_term","utm_content","utm_id",
    "gclid","fbclid","mc_eid","mc_cid","_ga","_gl","aff","aff_id","campaign",
}

_GOOGLE_HOSTS = {"www.google.com", "google.com", "www.google.nl", "google.nl"}

def strip_tracking(url: str) -> str:
    """Verwijder standaard tracking-parameters (utm/gclid/etc.)."""
    try:
        parsed = urllib.parse.urlsplit(url)
        if not parsed.query:
            return url
        q = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        kept = [(k, v) for (k, v) in q if k.lower() not in _STRIP_QUERY_KEYS]
        new_query = urllib.parse.urlencode(kept, doseq=True)
        return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, new_query, parsed.fragment))
    except Exception:
        return url

def is_google_product_link(url: str) -> bool:
    try:
        host = urllib.parse.urlsplit(url).netloc.lower()
        path = urllib.parse.urlsplit(url).path
        return (host in _GOOGLE_HOSTS) and (path.startswith("/shopping/product") or path.startswith("/aclk") or path.startswith("/url"))
    except Exception:
        return False

def prefer_direct_link(result: Dict[str, Any]) -> Optional[str]:
    """
    Kies de directe merchant-link:
    - 'product_link' heeft voorkeur
    - anders 'link', mits het GEEN Google-productpagina is
    """
    link = result.get("product_link") or result.get("product") or None
    if link and not is_google_product_link(link):
        return strip_tracking(link)

    link = result.get("link")
    if link and not is_google_product_link(link):
        return strip_tracking(link)

    # Probeer soms 'source' of 'seller' domain + 'product_id' (niet gegarandeerd aanwezig)
    # Als alles faalt: None (later vullen we een nette fallback in de output)
    return None

def display_domain(url: str) -> str:
    try:
        host = urllib.parse.urlsplit(url).netloc.lower()
        # Tover nette domeinstring, bv. shop.mango.com/nl -> Mango.com/nl
        parts = host.split(".")
        if len(parts) >= 2:
            host = f"{parts[-2]}.{parts[-1]}"
        # NL/BE pad hint
        path = urllib.parse.urlsplit(url).path
        if path:
            path_lower = path.lower()
            if "/nl" in path_lower:
                return f"{host}/nl"
            if "/be" in path_lower:
                return f"{host}/be"
        return host
    except Exception:
        return ""

def alloc_budget(total: float) -> Dict[str, float]:
    """Verdeel budget over categorieën; som ≈ total (kleine afronding)."""
    total = float(total or 250)
    alloc = {
        "outer": total * 0.25,
        "top1": total * 0.15,
        "top2": total * 0.15,
        "bottom": total * 0.20,
        "shoes": total * 0.20,
        "tee": total * 0.04,
        "accessory": total * 0.01,
    }
    alloc["_total"] = sum(v for k, v in alloc.items() if k != "_total")
    return alloc

_CATEGORY_TERMS = {
    "outer": "jacket blazer overshirt coat",
    "top1": "shirt knit sweater",
    "top2": "shirt knit sweater",
    "tee": "t-shirt tee",
    "bottom": "chino trousers jeans",
    "shoes": "sneakers shoes",
    "accessory": "belt scarf",
}

def build_query(category: str, intake: Dict[str, Any]) -> str:
    gender_raw = (intake.get("gender") or "unisex").lower()
    gender = {"male": "men", "female": "women"}.get(gender_raw, "unisex")
    styles = " ".join((intake.get("styles") or [])[:2])
    colors = " ".join((intake.get("favorite_colors") or [])[:3])
    terms = _CATEGORY_TERMS.get(category, "")
    return " ".join(x for x in [gender, styles, terms, colors] if x).strip()

def serp_search(q: str, gl: str, api_key: str, num: int = 16) -> List[Dict[str, Any]]:
    url = "https://serpapi.com/search.json"
    params = {
        "engine": "google_shopping",
        "q": q,
        "gl": gl.lower(),
        "hl": "nl",
        "num": num,
        "api_key": api_key,
    }
    r = requests.get(url, params=params, timeout=25)
    r.raise_for_status()
    return r.json().get("shopping_results", []) or []

def pick_item(results: List[Dict[str, Any]], max_price: float) -> Optional[Dict[str, Any]]:
    """Kies het best passende item ≤ 110% van max_price; anders goedkoopste met prijs."""
    best = None
    for r in results:
        price = r.get("extracted_price") or r.get("price") or 0
        try:
            price = float(price)
        except Exception:
            continue
        if price <= max_price * 1.10:
            if best is None:
                best = r
            else:
                # dichter bij max_price is beter
                prev = best.get("extracted_price") or best.get("price") or 0
                try:
                    prev = float(prev)
                except Exception:
                    prev = 0.0
                if abs(price - max_price) < abs(prev - max_price):
                    best = r
    if best is None:
        priced = []
        for x in results:
            p = x.get("extracted_price") or x.get("price")
            try:
                p = float(p)
                priced.append((p, x))
            except Exception:
                pass
        if priced:
            priced.sort(key=lambda t: t[0])
            best = priced[0][1]
    return best

def map_item(cat: str, r: Dict[str, Any]) -> Dict[str, Any]:
    price = r.get("extracted_price") or r.get("price") or 0
    try:
        price = float(price)
    except Exception:
        price = 0.0

    link = prefer_direct_link(r)
    if not link:
        # nette fallback i.p.v. Google "Nothing to see here"
        link = "#"

    merchant = r.get("source") or r.get("seller") or ""
    image = r.get("thumbnail") or r.get("image") or None

    return {
        "category": cat,
        "title": r.get("title", "—"),
        "price": round(price, 2),
        "currency": r.get("currency") or "EUR",
        "link": link,
        "image": image,
        "merchant": display_domain(link) if link and link != "#" else merchant,
        "cheaper_alternative": None,
    }

# ------------------------------ Routes ------------------------------

@app.get("/api/meta")
def meta():
    key_env = os.getenv("SERPAPI_API_KEY", "")
    return {
        "has_serpapi": bool(key_env),
        "environment": "dev",
        "version": "0.3.1"
    }

@app.post("/api/generate")
def generate(req: GenerateRequest):
    api_key = os.getenv("SERPAPI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="SerpAPI key ontbreekt op de server.")

    intake = req.intake.dict()
    gl = (intake.get("country") or "NL")[:2].lower()
    budget = float(intake.get("budget_total") or 250)
    alloc = alloc_budget(budget)
    categories = ["outer", "top1", "top2", "bottom", "shoes", "tee", "accessory"]

    palette = {"colors": (intake.get("favorite_colors") or ["navy", "white", "grey", "black", "stone"])}

    cache: Dict[str, List[Dict[str, Any]]] = {}
    outfits = []

    try:
        for n in range(max(1, int(req.outfits_count))):
            items = []
            total = 0.0
            for cat in categories:
                q = build_query(cat, intake)
                if q not in cache:
                    cache[q] = serp_search(q, gl, api_key, num=16)
                found = pick_item(cache[q], alloc[cat])
                if found:
                    item = map_item(cat, found)
                else:
                    # veilige fallback (zonder link)
                    item = {
                        "category": cat,
                        "title": "(Geen resultaat gevonden — alternatief binnen budget)",
                        "price": round(alloc[cat], 2),
                        "currency": "EUR",
                        "link": "#",
                        "image": None,
                        "merchant": "—",
                        "cheaper_alternative": None,
                    }
                items.append(item)
                try:
                    total += float(item.get("price") or 0.0)
                except Exception:
                    pass

            outfits.append({
                "name": f"Outfit {n+1}",
                "items": items,
                "total": round(total, 2),
                "currency": items[0].get("currency", "EUR") if items else "EUR",
            })

        return {
            "palette": palette,
            "allocation": alloc,
            "outfits": outfits,
            "explanation": "Producten gezocht via Google Shopping (SerpAPI) op jouw stijl, land en budget. Ik toon directe productlinks (geen Google-redirects).",
            "independent_note": "Anna is onafhankelijk — geen affiliate; links zijn puur gemak.",
            "country": intake.get("country") or "NL",
            "currency": outfits[0].get("currency", "EUR") if outfits else "EUR",
        }

    except requests.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"SerpAPI error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/chat")
def api_chat(req: ChatReq):
    """Kleine chat-endpoint voor de intake/gespreksflow met Anna (GPT-4o)."""
    try:
        reply = chat_anna(req.history, req.user_message)
        return {"assistant_message": reply}
    except Exception:
        # veilige fallback tekst
        return {"assistant_message": "Hm, er ging iets mis aan mijn kant. Kun je je laatste antwoord nog één keer sturen?"}

# --------------------------- Local runner ---------------------------
if __name__ == "__main__":
    # Voor lokaal testen; op Render start je via het Start Command (gunicorn/uvicorn)
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=True)
