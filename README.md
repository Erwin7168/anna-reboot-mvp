# Anna — Reboot MVP (NL/BE, directe productlinks)

Doel: 1) intake in 6 stappen (1 vraag per bericht), 2) 2–3 outfits met producten uit NL/BE shops,
3) alleen **directe productlinks** tonen (geen Google-redirects), 4) live via SerpAPI.

## Snel starten

### Backend (Render)
1. Maak een nieuwe **Web Service** op Render, met deze map `backend/` als bron.
2. **Root Directory**: `backend`
3. **Build Command**: `pip install -r requirements.txt`
4. **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. **Environment Variable**: voeg toe
   - Key: `SERPAPI_API_KEY`
   - Value: *jouw SerpAPI-sleutel*
6. Deploy.

Test: open `https://<jouw-render>.onrender.com/api/meta` → `"has_serpapi": true`.

### Frontend (Netlify)
1. Ga naar Netlify → **Add new site → Deploy manually**.
2. **Sleep alleen de map `frontend/`** naar het uploadvlak.
3. Na deploy: open de site → klik **Instellingen** (rechtsboven).
4. Vul **Back-end API URL** in, bv. `https://<jouw-render>.onrender.com`. Opslaan.
5. Doorloop de intake → typ **ja** → je krijgt outfits met **directe winkel-links**.

## Belangrijk
- De SerpAPI-sleutel staat **alleen server-side** (Render).
- De frontend dwingt **altijd** live-modus af (`mode: "serpapi"`).
