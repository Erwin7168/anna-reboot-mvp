import os, re, urllib.parse, requests
from typing import List, Optional, Dict, Any
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(title="Anna MVP API (Reboot)", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

class Intake(BaseModel):
    purpose: str
    styles: List[str] = []
    gender: str = "unisex"
    fit: Optional[str] = None
    age_range: Optional[str] = None
    country: str = "NL"
    currency: Optional[str] = "EUR"
    budget_total: Optional[float] = 250
    budget_per_item: Optional[float] = None
    sizes: Optional[Dict[str, str]] = None
    favorite_colors: Optional[List[str]] = None
    materials_avoid: Optional[List[str]] = None
    accessibility: Optional[Dict[str, Any]] = None
    sustainability_preference: Optional[bool] = False

class GenerateRequest(BaseModel):
    intake: Intake
    mode: Optional[str] = "serpapi"
    serpapi_api_key: Optional[str] = None
    outfits_count: int = 3

@app.get("/api/meta")
def meta():
    return {
        "has_serpapi": bool(os.getenv("SERPAPI_API_KEY", "")),
        "version": "1.0.0"
    }

@app.post("/api/generate")
def generate(req: GenerateRequest):
    key = (req.serpapi_api_key or "").strip() or os.getenv("SERPAPI_API_KEY", "")
    if not key:
        return {"outfits": [], "palette": {"colors": []}, "explanation":"Geen SERPAPI key."}

    intake = _to_dict(req.intake)
    outfits = generate_with_serpapi(intake, key, req.outfits_count)
    return outfits

def _to_dict(obj):
    try:    return obj.model_dump()
    except: return obj.dict()

def _alloc(budget: float):
    alloc = {
        "outer": budget*0.25, "top1": budget*0.15, "top2": budget*0.15,
        "bottom": budget*0.20, "shoes": budget*0.20, "tee": budget*0.04, "belt": budget*0.01
    }
    alloc["_total"] = round(sum(v for k,v in alloc.items() if k!="_total"), 2)
    return alloc

def _build_query(cat: str, intake: dict) -> str:
    gender = {"male":"men","female":"women"}.get((intake.get("gender") or "unisex").lower(), "unisex")
    styles = " ".join(intake.get("styles") or [])
    colors = " ".join(intake.get("favorite_colors") or [])
    terms_map = {
        "outer":"jacket blazer overshirt coat",
        "top1":"shirt knit sweater",
        "top2":"shirt knit sweater",
        "tee":"t-shirt tee",
        "bottom":"chino trousers jeans",
        "shoes":"sneakers shoes",
        "belt":"belt",
    }
    terms = terms_map.get(cat,"clothing")
    return " ".join(x for x in [gender, styles, terms, colors] if x).strip()

def _serp_shopping(q: str, gl: str, key: str, num: int = 16):
    r = requests.get("https://serpapi.com/search.json",
        params={"engine":"google_shopping","q":q,"gl":gl,"hl":"nl","num":num,"api_key":key},
        timeout=20)
    r.raise_for_status()
    return r.json().get("shopping_results", []) or []

def _serp_product(product_id: str, gl: str, key: str):
    r = requests.get("https://serpapi.com/search.json",
        params={"engine":"google_shopping_product","product_id":product_id,"gl":gl,"hl":"nl","api_key":key},
        timeout=20)
    r.raise_for_status()
    return r.json()

def _serp_web(q: str, gl: str, key: str, num: int = 10):
    r = requests.get("https://serpapi.com/search.json",
        params={"engine":"google","q":q,"gl":gl,"hl":"nl","num":num,"api_key":key},
        timeout=20)
    r.raise_for_status()
    return r.json().get("organic_results", []) or []

def _price_of(x: dict) -> float:
    p = x.get("extracted_price") or x.get("price") or 0
    try: return float(p)
    except: return 0.0

def _first_url(d: dict) -> Optional[str]:
    fields = ("link","product_link","product_page_url","product_url","source_url","redirect_link","url")
    candidates = []
    for k in fields:
        v = d.get(k)
        if isinstance(v,str) and v.strip():
            candidates.append(v.strip())
    if not candidates: return None
    for u in candidates:
        if "google.com" not in u and "shopping.google" not in u:
            return u
    return candidates[0]

def _normalize_link(url: Optional[str], title: str="", merchant: str="") -> str:
    if not url:
        q = urllib.parse.quote_plus(f"{title} {merchant}".strip())
        return f"https://www.google.com/search?q={q}"
    u = url.strip()
    if u.startswith("//"): u = "https:" + u
    if not re.match(r"^https?://", u): u = "https://" + u
    try:
        pu = urllib.parse.urlparse(u)
        qs = urllib.parse.parse_qs(pu.query)
        junk = {"utm_source","utm_medium","utm_campaign","utm_content","gclid","fbclid","msclkid","aff","affid","cjevent","irclickid","irgwc","_ga","_gl"}
        for k in list(qs.keys()):
            if k in junk: qs.pop(k, None)
        new_q = urllib.parse.urlencode({k:v[0] for k,v in qs.items()})
        u = urllib.parse.urlunparse((pu.scheme,pu.netloc,pu.path,"",new_q,""))
    except: pass
    return u

def _prefer_nl_be(link: str) -> bool:
    try:
        host = urllib.parse.urlparse(link).netloc.lower()
        return host.endswith(".nl") or host.endswith(".be")
    except: return False

def _resolve_direct_link(item: dict, key: str, gl: str) -> str:
    title = item.get("title","")
    merchant = item.get("source") or item.get("seller") or ""
    u = _first_url(item)
    if u and "google.com" not in u and "shopping.google" not in u:
        return _normalize_link(u, title, merchant)

    pid = item.get("product_id")
    if not pid and u:
        m = re.search(r"/product/(\d+)", u)
        pid = m.group(1) if m else None

    if pid:
        try:
            data = _serp_product(pid, gl, key)
            sellers = data.get("sellers_results") or []
            if merchant:
                m0 = merchant.lower().split()[0]
                for s in sellers:
                    link = s.get("link") or ""
                    store = (s.get("source") or s.get("seller") or s.get("store") or "").lower()
                    if m0 and (m0 in store or m0 in link.lower()):
                        if link and "google.com" not in link:
                            return _normalize_link(link, title, store or merchant)
            best = None
            for s in sellers:
                link = s.get("link")
                if link and "google.com" not in link:
                    if _prefer_nl_be(link): return _normalize_link(link, title, merchant)
                    best = best or link
            if best: return _normalize_link(best, title, merchant)
        except: pass

    organics = _serp_web(f"{title} {merchant}".strip(), gl, key, num=10)
    kw = re.sub(r"[^a-z0-9]+","",(merchant or "").lower())
    for r in organics:
        link = r.get("link")
        if not isinstance(link,str): continue
        if "google.com" in link: continue
        host = urllib.parse.urlparse(link).netloc.lower().replace("www.","")
        host_flat = re.sub(r"[^a-z0-9]+","",host)
        if kw and kw in host_flat:
            return _normalize_link(link, title, merchant)
    for r in organics:
        link = r.get("link")
        if isinstance(link,str) and link.strip() and "google.com" not in link and _prefer_nl_be(link):
            return _normalize_link(link, title, merchant)
    for r in organics:
        link = r.get("link")
        if isinstance(link,str) and link.strip() and "google.com" not in link:
            return _normalize_link(link, title, merchant)

    return _normalize_link(None, title, merchant)

def _map(cat: str, item: dict, link: str):
    price = _price_of(item)
    cur = item.get("currency") or "EUR"
    return {
        "category": cat,
        "title": item.get("title","—"),
        "price": round(price,2),
        "currency": cur,
        "link": link,
        "image": item.get("thumbnail"),
        "merchant": item.get("source") or item.get("seller") or "",
    }

def _pick(results: list, max_price: float):
    cands = [r for r in results if _price_of(r) > 0]
    within = [r for r in cands if _price_of(r) <= max_price * 1.10]
    pool = within or cands
    if not pool: return None
    pool.sort(key=lambda r: abs(_price_of(r) - max_price))
    return pool[0]

def generate_with_serpapi(intake: dict, key: str, outfits_count: int = 3):
    budget = float(intake.get("budget_total") or 250.0)
    alloc = _alloc(budget)
    gl = (intake.get("country") or "NL")[:2].lower()
    palette = {"colors": (intake.get("favorite_colors") or ["navy","wit","grijs","zwart"])}

    categories = ["outer","top1","top2","bottom","shoes","tee","belt"]
    outfits = []
    cache: Dict[str, list] = {}

    for n in range(outfits_count or 3):
        items, total = [], 0.0
        for cat in categories:
            q = _build_query(cat, intake)
            if q not in cache:
                cache[q] = _serp_shopping(q, gl, key, num=16)
            found = _pick(cache[q], alloc[cat])
            if found:
                direct = _resolve_direct_link(found, key, gl)
                mapped = _map(cat, found, direct)
                if _is_direct_product_url(mapped["link"]):
                    items.append(mapped); total += mapped["price"]
        outfits.append({
            "name": f"Outfit {n+1}",
            "items": items,
            "total": round(total,2),
            "currency": "EUR"
        })

    explanation = "Selectie live gezocht in NL/BE shops; links leiden rechtstreeks naar productpagina’s (prijs/maat/bestellen aanwezig)."
    return {
        "palette": palette,
        "allocation": alloc,
        "outfits": outfits,
        "explanation": explanation,
        "independent_note": "Onpartijdig: geen affiliate.",
        "country": intake.get("country") or "NL",
        "currency": "EUR",
    }

def _is_direct_product_url(url: str) -> bool:
    try:
        u = urllib.parse.urlparse(url)
        host = u.netloc.lower()
        if any(b in host for b in ["google.com","shopping.google","googleadservices","doubleclick"]): return False
        segs = [s for s in u.path.split("/") if s]
        return len(segs) >= 1
    except:
        return False

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000)
