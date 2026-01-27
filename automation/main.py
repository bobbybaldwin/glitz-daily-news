import os
import json
import requests
import feedparser
import time
import re
import random
import warnings 
from datetime import datetime
from slugify import slugify
from io import BytesIO
from PIL import Image, ImageEnhance
from groq import Groq

# --- SUPPRESS WARNINGS ---
warnings.filterwarnings("ignore", category=FutureWarning, module="google.api_core")

# --- 🟢 GOOGLE INDEXING LIBS ---
try:
    from oauth2client.service_account import ServiceAccountCredentials
    from googleapiclient.discovery import build
except ImportError:
    print("⚠️  Google API Library belum terinstall. Indexing Google akan dilewati.")
    GOOGLE_JSON_KEY = None

# --- CONFIGURATION ---
GROQ_KEYS_RAW = os.environ.get("GROQ_API_KEY", "")
GROQ_API_KEYS = [k.strip() for k in GROQ_KEYS_RAW.split(",") if k.strip()]

WEBSITE_URL = "https://glitz-daily-news.vercel.app" 
INDEXNOW_KEY = "5b3e50c6d7b845d3ba6768de22595f94"
GOOGLE_JSON_KEY = os.environ.get("GOOGLE_INDEXING_KEY", "") 

if not GROQ_API_KEYS:
    print("❌ FATAL ERROR: Groq API Key is missing!")
    exit(1)

# --- 🟢 CONSTANTS ---
AUTHOR_PROFILES = [
    "Jessica Hart (Film Critic)", "Marcus Cole (Music Editor)",
    "Sarah Jenkins (Streaming Analyst)", "David Choi (K-Pop Insider)",
    "Amanda Lee (Celebrity News)", "Tom Baker (Gaming & Esports)",
    "The Pop Culture Desk"
]

VALID_CATEGORIES = [
    "Movies & Film", 
    "TV Shows & Streaming", 
    "Music & Concerts", 
    "Celebrity & Lifestyle", 
    "Anime & Manga", 
    "Gaming & Esports",
    "Pop Culture Trends"
]

RSS_SOURCES = {
    "Entertainment US": "https://news.google.com/rss/headlines/section/topic/ENTERTAINMENT?hl=en-US&gl=US&ceid=US:en",
    "Gaming News": "https://news.google.com/rss/search?q=gaming+news+esports&hl=en-US&gl=US&ceid=US:en",
    "Pop Culture": "https://news.google.com/rss/search?q=pop+culture+trends&hl=en-US&gl=US&ceid=US:en"
}

# 🟢 MASSIVE UNIQUE DATABASE (Supaya Gak Kembar)
# Format: Kategori -> List URL
RAW_IMAGE_DB = {
    "Movies & Film": [
        "https://images.unsplash.com/photo-1489599849927-2ee91cede3ba?w=1200&q=90", 
        "https://images.unsplash.com/photo-1536440136628-849c177e76a1?w=1200&q=90",
        "https://images.unsplash.com/photo-1478720568477-152d9b164e63?w=1200&q=90",
        "https://images.unsplash.com/photo-1594909122845-11baa439b7bf?w=1200&q=90",
        "https://images.unsplash.com/photo-1440404653325-ab127d49abc1?w=1200&q=90",
        "https://images.unsplash.com/photo-1517604931442-71053e683597?w=1200&q=90",
        "https://images.unsplash.com/photo-1598899134739-24c46f58b8c0?w=1200&q=90"
    ],
    "TV Shows & Streaming": [
        "https://images.unsplash.com/photo-1574375927938-d5a98e8ffe85?w=1200&q=90",
        "https://images.unsplash.com/photo-1522869635100-1f4906a1f07d?w=1200&q=90", 
        "https://images.unsplash.com/photo-1593784697956-14f46924c560?w=1200&q=90",
        "https://images.unsplash.com/photo-1626814026160-2237a95fc5a0?w=1200&q=90",
        "https://images.unsplash.com/photo-1611162617474-5b21e879e113?w=1200&q=90",
        "https://images.unsplash.com/photo-1585776245991-cf89dd7fc171?w=1200&q=90",
        "https://images.unsplash.com/photo-1485846234645-a62644f84728?w=1200&q=90"
    ],
    "Music & Concerts": [
        "https://images.unsplash.com/photo-1493225255756-d9584f8606e9?w=1200&q=90",
        "https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=1200&q=90",
        "https://images.unsplash.com/photo-1470225620780-dba8ba36b745?w=1200&q=90",
        "https://images.unsplash.com/photo-1501281668745-f7f57925c3b4?w=1200&q=90",
        "https://images.unsplash.com/photo-1514525253440-b393452e8d26?w=1200&q=90",
        "https://images.unsplash.com/photo-1459749411177-0473ef7161a8?w=1200&q=90",
        "https://images.unsplash.com/photo-1506157786151-b8491531f063?w=1200&q=90"
    ],
    "Gaming & Esports": [
        "https://images.unsplash.com/photo-1542751371-adc38448a05e?w=1200&q=90",
        "https://images.unsplash.com/photo-1538481199705-c710c4e965fc?w=1200&q=90",
        "https://images.unsplash.com/photo-1592840496694-26d035b52b48?w=1200&q=90",
        "https://images.unsplash.com/photo-1616469829581-73993eb86b02?w=1200&q=90",
        "https://images.unsplash.com/photo-1511512578047-dfb367046420?w=1200&q=90",
        "https://images.unsplash.com/photo-1542831371-29b0f74f9713?w=1200&q=90",
        "https://images.unsplash.com/photo-1552820728-8b83bb6b773f?w=1200&q=90",
        "https://images.unsplash.com/photo-1612287230217-12ad00f54266?w=1200&q=90"
    ],
    "Celebrity & Lifestyle": [
        "https://images.unsplash.com/photo-1515634928627-2a4e0dae3ddf?w=1200&q=90",
        "https://images.unsplash.com/photo-1496747611176-843222e1e57c?w=1200&q=90",
        "https://images.unsplash.com/photo-1529626455594-4ff0802cfb7e?w=1200&q=90",
        "https://images.unsplash.com/photo-1583195764036-6dc248ac07d9?w=1200&q=90",
        "https://images.unsplash.com/photo-1504196606672-aef5c9cefc92?w=1200&q=90",
        "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=1200&q=90",
        "https://images.unsplash.com/photo-1483985988355-763728e1935b?w=1200&q=90"
    ],
    "General": [
        "https://images.unsplash.com/photo-1492684223066-81342ee5ff30?w=1200&q=90",
        "https://images.unsplash.com/photo-1505373877841-8d25f7d46678?w=1200&q=90",
        "https://images.unsplash.com/photo-1516280440614-6697288d5d38?w=1200&q=90",
        "https://images.unsplash.com/photo-1550133730-695473e544be?w=1200&q=90"
    ]
}

CONTENT_DIR = "content/articles"
IMAGE_DIR = "static/images"
DATA_DIR = "automation/data"
MEMORY_FILE = f"{DATA_DIR}/link_memory.json"
TARGET_PER_SOURCE = 2 

# GLOBAL STATE untuk AI
AI_ENABLED_SESSION = True  # Default nyala, akan mati otomatis jika error

# --- HELPER FUNCTIONS ---
def load_link_memory():
    if not os.path.exists(MEMORY_FILE): return {}
    try:
        with open(MEMORY_FILE, 'r') as f: return json.load(f)
    except: return {}

def save_link_to_memory(title, slug):
    os.makedirs(DATA_DIR, exist_ok=True)
    memory = load_link_memory()
    memory[title] = f"/{slug}/"
    if len(memory) > 50:
        memory = dict(list(memory.items())[-50:])
    with open(MEMORY_FILE, 'w') as f: json.dump(memory, f, indent=2)

def get_internal_links():
    memory = load_link_memory()
    items = list(memory.items())
    if not items: return ""
    count = min(len(items), 3)
    items = random.sample(items, count)
    links = []
    for title, url in items:
        links.append(f"- [{title}]({url})")
    return "\n".join(links)

def clean_camel_case(text):
    if not text: return ""
    text = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', text)
    text = re.sub(r'(?<=[a-zA-Z])(?=\d)', ' ', text)
    text = re.sub(r'(?<=\d)(?=[a-zA-Z])', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()

def repair_json(json_str):
    try:
        return json.loads(json_str) 
    except:
        json_str = re.sub(r'(\w+):', r'"\1":', json_str) 
        try: return json.loads(json_str)
        except: return None

# --- 🛠️ REPAIR MARKDOWN ---
def repair_markdown_formatting(text):
    if not text: return ""
    text = text.replace("| — |", "|---|").replace("|—|", "|---|")
    text = re.sub(r'\|\s*\|', '|\n|', text)
    text = text.replace('|---|---|', '|---|---|\n').replace('|---|', '|---|\n')
    text = re.sub(r'(?<!\n)\s-\s\[', '\n- [', text) 
    text = re.sub(r'(?<!\n)\s-\s\*\*', '\n- **', text)
    text = text.replace("###", "\n\n###").replace("##", "\n\n##")
    return text

# --- 🟢 UNIQUE IMAGE ENGINE ---
def get_unique_stock_image(category):
    """
    Mengambil gambar dari database DAN MENGHAPUSNYA dari list
    agar tidak pernah ada gambar duplikat dalam satu sesi.
    """
    global RAW_IMAGE_DB
    
    # Ambil list berdasarkan kategori, atau fallback ke General
    target_list = RAW_IMAGE_DB.get(category, RAW_IMAGE_DB["General"])
    
    # Jika stok habis di kategori itu, ambil dari General
    if not target_list:
        target_list = RAW_IMAGE_DB["General"]
        
    # Jika General juga habis (sangat jarang), reset atau pakai default
    if not target_list:
        return "https://images.unsplash.com/photo-1492684223066-81342ee5ff30?w=1200&q=90"

    # PILIH SECARA ACAK
    selected_url = random.choice(target_list)
    
    # HAPUS DARI LIST AGAR TIDAK DIPAKAI LAGI (NO DUPLICATE)
    target_list.remove(selected_url)
    
    return selected_url

def save_image_from_url(url, path):
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            img = Image.open(BytesIO(r.content)).convert("RGB")
            img = img.resize((1200, 675), Image.Resampling.LANCZOS)
            # Optimize
            enhancer_color = ImageEnhance.Color(img)
            img = enhancer_color.enhance(1.1)
            img.save(path, "WEBP", quality=85)
            return True
    except:
        pass
    return False

def clean_prompt_for_ai(text):
    text = re.sub(r'[^a-zA-Z0-9\s]', '', text)
    return text[:100]

def download_image_smart(query, category, filename):
    global AI_ENABLED_SESSION
    
    if not filename.endswith(".webp"): filename += ".webp"
    path = os.path.join(IMAGE_DIR, filename)
    
    # 1. Skip jika file sudah ada
    if os.path.exists(path) and os.path.getsize(path) > 5000:
        return f"/images/{filename}"

    print(f"      🎨 Processing Image: {query[:20]}...")

    # 2. LOGIKA AI DENGAN SAKLAR OTOMATIS
    # Jika AI masih menyala, coba pakai AI
    if AI_ENABLED_SESSION:
        print("         🤖 Attempting AI Generation...")
        clean_query = clean_prompt_for_ai(query)
        try:
            prompt = f"cinematic photo of {clean_query}, 4k, realistic, detailed"
            safe_prompt = requests.utils.quote(prompt)
            url = f"https://image.pollinations.ai/prompt/{safe_prompt}?width=1280&height=720&nologo=true&model=flux&seed={random.randint(1,99999)}"
            
            resp = requests.get(url, timeout=30)
            
            # CEK APAKAH INI GAMBAR RATE LIMIT?
            # Gambar Rate Limit biasanya ukurannya spesifik atau kecil, tapi kadang besar.
            # Cara paling aman: Jika kita sering gagal, matikan AI.
            if resp.status_code == 200 and len(resp.content) > 15000:
                # Kita anggap sukses DULU
                img = Image.open(BytesIO(resp.content)).convert("RGB")
                img = img.resize((1200, 675), Image.Resampling.LANCZOS)
                img.save(path, "WEBP", quality=90)
                print("         ✅ AI Generated Successfully")
                return f"/images/{filename}"
            else:
                print("         ⚠️ AI Rate Limit / Error. Disabling AI for this session.")
                AI_ENABLED_SESSION = False # MATIKAN AI UNTUK SISA SESI
        except Exception as e:
            print(f"         ⚠️ AI Connection Error. Disabling AI. ({e})")
            AI_ENABLED_SESSION = False

    # 3. FALLBACK: UNIQUE STOCK PHOTO (Anti-Duplicate)
    print(f"         📸 Using Unique Stock Photo for {category}...")
    stock_url = get_unique_stock_image(category)
    
    if save_image_from_url(stock_url, path):
        return f"/images/{filename}"
    
    return "/images/default-glitz.jpg"

# --- 🟢 INDEXING ---
def submit_to_google(url):
    if not GOOGLE_JSON_KEY: return
    try:
        creds_dict = json.loads(GOOGLE_JSON_KEY)
        SCOPES = ["https://www.googleapis.com/auth/indexing"]
        credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPES)
        service = build("indexing", "v3", credentials=credentials)
        body = {"url": url, "type": "URL_UPDATED"}
        service.urlNotifications().publish(body=body).execute()
        print(f"      🚀 Google Indexing Submitted")
    except: pass

def submit_to_indexnow(url):
    try:
        endpoint = "https://api.indexnow.org/indexnow"
        host = WEBSITE_URL.replace("https://", "").replace("http://", "")
        data = {
            "host": host,
            "key": INDEXNOW_KEY,
            "keyLocation": f"https://{host}/{INDEXNOW_KEY}.txt",
            "urlList": [url]
        }
        requests.post(endpoint, json=data, headers={'Content-Type': 'application/json; charset=utf-8'}, timeout=10)
        print(f"      🚀 IndexNow Submitted")
    except: pass

# --- 🟢 CONTENT FORMATTER ---
def format_content_structure(text):
    text = repair_markdown_formatting(text)
    parts = text.split("\n\n")
    if len(parts) > 3:
        parts.insert(3, "\n{{< ad >}}\n")
    elif len(parts) > 1:
        parts.insert(1, "\n{{< ad >}}\n")
    text = "\n\n".join(parts)
    text = re.sub(r'(?i)\*\*Q:\s*(.*?)\*\*', r'\n\n**Q: \1**', text) 
    text = re.sub(r'(?i)\*\*A:\s*(.*?)\*\*', r'\n**A:** \1', text)   
    text = text.replace("Q: ", "\n\n**Q:** ").replace("A: ", "\n**A:** ")
    return text

# --- 🤖 AI WRITER ---
def get_metadata(title, summary):
    api_key = random.choice(GROQ_API_KEYS)
    client = Groq(api_key=api_key)
    categories_str = ", ".join(VALID_CATEGORIES)
    
    prompt = f"""
    Analyze: "{title}"
    Task: Create a click-worthy title. Use proper English spacing. NO CamelCase.
    Return JSON ONLY:
    {{
        "title": "Title With Spaces",
        "category": "One of [{categories_str}]",
        "description": "SEO Description 150 chars",
        "keywords": ["tag1", "tag2"]
    }}
    """
    try:
        chat = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.6
        )
        return repair_json(chat.choices[0].message.content)
    except: return None

def write_article(metadata, summary, internal_links, author, external_sources_str):
    api_key = random.choice(GROQ_API_KEYS)
    client = Groq(api_key=api_key)
    
    prompt = f"""
    You are {author}. Write a 1000-word article on: "{metadata['title']}"
    Context: {summary}
    
    INTERNAL LINKS (Inject these exactly as a Bullet List):
    {internal_links}
    
    EXTERNAL SOURCES: {external_sources_str}
    
    STRUCTURE RULES:
    1. **Hook**: Strong opening.
    2. **Unique H2 Headline**: Creative title.
    3. **Key Details (H2)**: Create a MARKDOWN TABLE. 
       ⚠️ IMPORTANT: Put a blank line BEFORE and AFTER the table. 
       Format: | Header | Header |
    4. **Must Read (H2)**: Paste the INTERNAL LINKS as a vertical Bullet List.
       ⚠️ IMPORTANT: Start each link on a NEW LINE with a dash.
    5. **Industry Insight (H2)**: Analysis citing {external_sources_str}.
    6. **Conclusion (H2)**: Summary.
    7. **FAQ (H2)**: 3 Q&A.

    Output MARKDOWN only.
    """
    try:
        chat = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.75, 
            max_tokens=6500 
        )
        return chat.choices[0].message.content
    except: return None

# --- MAIN LOOP ---
def main():
    print("🎬 Starting glitz Daily Automation (Zero Duplicate Mode)...")
    os.makedirs(CONTENT_DIR, exist_ok=True)
    os.makedirs(IMAGE_DIR, exist_ok=True)
    
    # SHUFFLE IMAGE DB AGAR SETIAP RUN BEDA URUTAN
    for cat in RAW_IMAGE_DB:
        random.shuffle(RAW_IMAGE_DB[cat])
    
    for source, url in RSS_SOURCES.items():
        print(f"\n📡 Scanning: {source}...")
        feed = feedparser.parse(url)
        if not feed.entries: continue
        
        success_count = 0
        for entry in feed.entries:
            if success_count >= TARGET_PER_SOURCE: break
            
            clean_title = clean_camel_case(entry.title.split(" - ")[0])
            print(f"   ✨ Analyzing: {clean_title[:30]}...")

            meta = get_metadata(clean_title, entry.summary)
            if not meta: continue
            
            meta['title'] = clean_camel_case(meta['title'])
            if meta['category'] not in VALID_CATEGORIES:
                meta['category'] = "Pop Culture Trends"
            
            slug = slugify(meta['title'])
            filename = f"{slug}.md"
            filepath = os.path.join(CONTENT_DIR, filename)
            
            if os.path.exists(filepath):
                print(f"      ⏭️  Skipped (Exists)")
                continue
            
            author = random.choice(AUTHOR_PROFILES)
            links = get_internal_links()
            selected_external = random.sample(AUTHORITY_SOURCES, 2)
            external_str = ", ".join(selected_external)
            
            raw_content = write_article(meta, entry.summary, links, author, external_str)
            if not raw_content: continue
            
            final_content = format_content_structure(raw_content)
            
            # 🟢 IMAGE PROCESS (SMART)
            image_query = meta.get('keywords', [meta['title']])[0] 
            img_path = download_image_smart(image_query, meta['category'], slug)
            
            date_now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+07:00")
            tags_json = json.dumps(meta['keywords'])
            
            md_content = f"""---
title: "{meta['title'].replace('"', "'")}"
date: {date_now}
author: "{author}"
categories: ["{meta['category']}"]
tags: {tags_json}
featured_image: "{img_path}"
featured_image_alt: "{meta['title']}"
description: "{meta['description'].replace('"', "'")}"
draft: false
slug: "{slug}"
url: "/{slug}/"
---

{final_content}

---
*Disclaimer: Content generated by AI Analyst {author}.*
"""
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(md_content)
            
            save_link_to_memory(meta['title'], slug)
            
            full_url = f"{WEBSITE_URL}/{slug}/"
            submit_to_indexnow(full_url)
            submit_to_google(full_url)
            
            print(f"      ✅ Published: {filename}")
            success_count += 1
            
            # 🛑 JEDA WAKTU LAMA (60 Detik) AGAR API DINGIN
            print("      ⏳ Cooling down request for 60s...")
            time.sleep(60) 

    print("\n🎉 DONE! Automation Finished.")

if __name__ == "__main__":
    main()
