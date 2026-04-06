# FieldSync — Streamlit Version

Convert raw GPS coordinates into a valid KML file.  
Auto-corrects formatting errors. Map preview included.

---

## Run Locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

App opens at: http://localhost:8501

---

## Deploy Free (2 minutes)

1. Push this folder to a GitHub repo
2. Go to share.streamlit.io
3. Sign in with GitHub
4. Select your repo → set main file as `app.py`
5. Click Deploy

Done. You get a live public URL instantly.

---

## Files

```
fieldsync_streamlit/
├── app.py            # Everything — UI, parser, KML generator, map
└── requirements.txt  # streamlit, folium, streamlit-folium
```
