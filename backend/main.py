import os
import re
import urllib.parse
import requests
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# pydantic v1/v2 compat
try:
    from pydantic import BaseModel, Field, ConfigDict, model_validator  # v2
    HAS_PYDANTIC_V2 = True
except Exception:
    from pydantic import BaseModel, Field, root_validator               # v1
    HAS_PYDANTIC_V2 = False

from dotenv import load_dotenv
load_dotenv()

app = FastAPI(title="Anna MVP API", version="0.3.5")

# CORS – open voor MVP
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------- Datamodellen ---------------------

class Intake(BaseModel):
    purpose: str = Field(..., description="werk, vrije tijd, event, dagelijks, etc.")
    styles: Optional[List[str]] = Field(None, description="max 2 stijlen (casual, klassiek, sportief, creatief, minimalistisch)")
    # Let op: we willen 'gender' als man/vrouw, maar accepteren ook 'geslacht' uit de frontend.
    gender: Optional[str] = Field(None, description="man of vrouw")
    fit: Optional[str] = None
    age_range: Optional[str] = None
    country: Optional[str] = Field("NL", description="NL, BE, DE, FR, UK, US")
    currency: Optional[str] = None
    budget_total: Optional[float] = Field(250, ge=0, description="Totaalbudget")
    budget_per_item: Optional[float] = None
    sizes: Optional[Dict[str, str]] = None
    favorite_colors: Optional[List[str]] = None
    materials_avoid: Optional[List[str]] = None
    accessibility: Optional[Dict[str, Any]] = None
    sustainability_preference: Optional[bool] = False

    if HAS_PYDANTIC_V2:
        # v2: negeer extra velden en laat populatie op naam toe
        model_config = ConfigDict(extra="ignore", populate_by_name=True)

        @model_validator(mode="before")
        def map_geslacht_to_gender(cls, values):
            """Zet 'geslacht' (man/vrouw) om naar 'gender' vóór validatie."""
            if isinstance(values, dict):
                data = dict(values)
                if "gender" not in data and "geslacht" in data:
                    data["gender"] = data.get("geslacht")
                # normaliseer
                g = str(data.get("gender") or "").strip().lower()
                if g in {"male", "m"}:
                    g = "man"
                if g in {"female", "f"}:
                    g = "vrouw"
                if g:
                    data["gender"] = g
                return data
            return values
    else:
        # v1: negeer extra velden
        class Config:
            extra = "ignore"
            allow_population_by_field_name = True

        @root_validator(pre=True)
        def map_geslacht_to_gender(cls, values):
            """Zet 'geslacht' (man/vrouw) om naar 'gender' vóór validatie (pydantic v1)."""
            if isinstance(values, dict):
                if "gender" not in values and "geslacht" in values:
                    values["gender"] = values.get("geslacht")
                g = str(values.get("gender") or "").strip().lower()
                if g in {"male", "m"}:
                    g = "man"
                if g in {"female", "f"}:
                    g = "vrouw"
                if g:
                    values["gender"] = g
            return values


class GenerateRequest(BaseModel):
    intake: Intake
    outfits_count: int = Field(3, ge=1, le=6, description="aantal outfits (1–6)")

# --------------------- Meta ---------------------

@app.get("/api/meta")
def meta():
    return {
        "has_serpapi": bool(os.getenv("SERPAPI_API_KEY", "")),
        "environment": "dev",
        "version": "0.3.5",
    }

# --------------------- Hulpfuncties (SerpAPI) ---------------------

def _alloc(budget: float) -> Dict[str, float]:
    alloc = {
        "outer": budget * 0.25,
        "top1": budget * 0.15,
        "top2": budget * 0.15,
        "bottom": budget * 0.20,
        "shoes": budget * 0.20,
        "tee": budget * 0.04,
        "accessory": budget * 0.01,
    }
    alloc["_total"] = sum(v for k, v in alloc.items() if k != "_total")
    return alloc

def _gender_token(g: Optional[str]) -> str:
    """Converteer man/vrouw (of tolerant: male/female, m/v) naar 'men' of 'women'."""
    if not g:
        return ""
    g = str(g).strip().lower()
    if g in {"man", "male", "m"}:
        return "men"
    if g in {"vrouw", "female", "v"}:
        return "women"
    return ""

def _build_query(category: str, intake: Dict[str, Any]) -> str:
    styles = " ".join((intake.get("styles") or ["casual"])[:2])
    colors = " ".join(intake.get("favorite_colors") or [])
    gender = _gender_token(intake.get("gender"))

    terms = {
        "outer": "jacket blazer overshirt coat",
        "top1": "shirt knit sweater",
        "top2": "shirt knit sweater",
        "tee": "t-shirt tee",
        "bottom": "chino trousers jeans",
        "shoes": "sneakers shoes",
        "accessory": "belt scarf",
    }[category]

    parts = [gender, styles, terms, colors]
    return " ".join(x for x in parts if x).strip()

def _serp_search(q: str, gl: str, api_key: str, num: int = 20) -> list:
    url = "https://serpapi.com/search.json"
    params = {
        "engine": "google_shopping",
        "q": q,
        "gl": gl.lower(),
        "hl": "nl",
        "num": num,
        "api_key": api_key,
    }
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    return r.json().get("shopping_results") or []

def _is_direct(url: str) -> bool:
    if not url:
        return False
    return "google." not in url.lower()

def _first_direct_link(r: dict) -> str:
    for key in ("link", "product_link", "source_url", "source_link"):
        url = (r.get(key) or "").strip()
        if _is_direct(url):
            return url
    return ""

def _price_of(x: dict) -> float:
    p = x.get("extracted_price") or x.get("price")
    try:
        return float(p)
    except Exception:
        return 0.0

def _pick_item_with_direct(results: list, max_price: float):
    ordered = sorted(results, key=lambda x: abs(_price_of(x) - max_price))
    for r in ordered:
        link = _first_direct_link(r)
        price = _price_of(r)
        if link and 0 < price <= max_price * 1.10:
            return r, link, price

    direct = [(r, _first_direct_link(r), _price_of(r)) for r in results]
    direct = [t for t in direct if t[1] and t[2] > 0]
    if not direct:
        return None, "", 0.0
    direct.sort(key=lambda t: t[2])
    return direct[0]

def _map_item(category: str, r: dict, link: str, price: float) -> dict:
    cur = r.get("currency") or "EUR"
    merchant = r.get("source") or r.get("seller") or ""
    title = r.get("title") or "—"
    img = r.get("thumbnail") or r.get("image")
    return {
        "category": category,
        "title": title,
        "price": round(price, 2),
        "currency": cur,
        "link": link,
        "image": img,
        "merchant": merchant,
        "cheaper_alternative": None,
    }

def generate_with_serpapi(intake: Dict[str, Any], api_key: str, outfits_count: int = 3) -> dict:
    budget = float(intake.get("budget_total") or 250)
    alloc = _alloc(budget)
    gl = (intake.get("country") or "NL")[:2]
    categories = ["outer", "top1", "top2", "bottom", "shoes", "tee", "accessory"]
    palette = {"colors": (intake.get("favorite_colors") or ["navy", "white", "grey"])}

    outfits = []
    cache: Dict[str, list] = {}

    for i in range(max(1, min(outfits_count, 6))):
        items = []
        total = 0.0
        for cat in categories:
            q = _build_query(cat, intake)
            if q not in cache:
                cache[q] = _serp_search(q, gl, api_key, num=20)

            r, link, price = _pick_item_with_direct(cache[q], alloc[cat])

            if r:
                item = _map_item(cat, r, link, price)
            else:
                item = {
                    "category": cat,
                    "title": "(geen directe shoplink gevonden — alternatief)",
                    "price": round(alloc[cat], 2),
                    "currency": "EUR",
                    "link": "#",
                    "image": None,
                    "merchant": "—",
                    "cheaper_alternative": None,
                }
            items.append(item)
            total += float(item.get("price") or 0)

        outfits.append({
            "name": f"Outfit {i + 1}",
            "items": items,
            "total": round(total, 2),
            "currency": items[0].get("currency", "EUR"),
        })

    return {
        "palette": palette,
        "allocation": alloc,
        "outfits": outfits,
        "explanation": "Producten gezocht via Google Shopping (SerpAPI) met directe shop‑links. Bij lege resultaten kies ik een veilig alternatief.",
        "independent_note": "Anna is onafhankelijk — geen affiliate; links zijn puur gemak.",
        "country": intake.get("country") or "NL",
        "currency": outfits[0].get("currency", "EUR"),
    }

# --------------------- Endpoint ---------------------

@app.post("/api/generate")
def generate(req: GenerateRequest):
    api_key = os.getenv("SERPAPI_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(status_code=500, detail="SERPAPI_API_KEY ontbreekt")

    try:
        intake_dict = req.intake.dict()
        return generate_with_serpapi(intake_dict, api_key, req.outfits_count)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --------------------- Local run ---------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=True)
