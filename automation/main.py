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

# 🟢 DATABASE GAMBAR ASLI (HIGH RES - GOOGLE DISCOVER FRIENDLY)
# Kita gunakan ini sebagai UTAMA agar tidak kena Rate Limit AI lagi.
CATEGORY_IMAGES_DB = {
    "Movies & Film": [
        "https://images.unsplash.com/photo-1489599849927-2ee91cede3ba?w=1200&q=90", # Cinema
        "https://images.unsplash.com/photo-1536440136628-849c177e76a1?w=1200&q=90", # Movie Set
        "https://images.unsplash.com/photo-1598899134739-24c46f58b8c0?w=1200&q=90", # Popcorn
        "https://images.unsplash.com/photo-1478720568477-152d9b164e63?w=1200&q=90", # Film Roll
        "https://images.unsplash.com/photo-1594909122845-11baa439b7bf?w=1200&q=90"  # Premiere
    ],
    "TV Shows & Streaming": [
        "https://images.unsplash.com/photo-1574375927938-d5a98e8ffe85?w=1200&q=90", # Netflix
        "https://images.unsplash.com/photo-1522869635100-1f4906a1f07d?w=1200&q=90", # TV Remote
        "https://images.unsplash.com/photo-1593784697956-14f46924c560?w=1200&q=90", # Living Room TV
        "https://images.unsplash.com/photo-1626814026160-2237a95fc5a0?w=1200&q=90", # Streaming
        "https://images.unsplash.com/photo-1611162617474-5b21e879e113?w=1200&q=90"  # Tablet Streaming
    ],
    "Music & Concerts": [
        "https://images.unsplash.com/photo-1493225255756-d9584f8606e9?w=1200&q=90", # Concert Light
        "https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=1200&q=90", # Mic
        "https://images.unsplash.com/photo-1470225620780-dba8ba36b745?w=1200&q=90", # DJ
        "https://images.unsplash.com/photo-1501281668745-f7f57925c3b4?w=1200&q=90", # Crowd
        "https://images.unsplash.com/photo-1514525253440-b393452e8d26?w=1200&q=90"  # Club
    ],
    "Gaming & Esports": [
        "https://images.unsplash.com/photo-1542751371-adc38448a05e?w=1200&q=90", # Gaming Setup
        "https://images.unsplash.com/photo-1538481199705-c710c4e965fc?w=1200&q=90", # PC RGB
        "https://images.unsplash.com/photo-1592840496694-26d035b52b48?w=1200&q=90", # Controller
        "https://images.unsplash.com/photo-1616469829581-73993eb86b02?w=1200&q=90", # Esports Arena
        "https://images.unsplash.com/photo-1511512578047-dfb367046420?w=1200&q=90"  # Gamer
    ],
    "Celebrity & Lifestyle": [
        "https://images.unsplash.com/photo-1515634928627-2a4e0dae3ddf?w=1200&q=90", # Red Carpet
        "https://images.unsplash.com/photo-1496747611176-843222e1e57c?w=1200&q=90", # Fashion
        "https://images.unsplash.com/photo-1529626455594-4ff0802cfb7e?w=1200&q=90", # Model
        "https://images.unsplash.com/photo-1583195764036-6dc248ac07d9?w=1200&q=90", # Paparazzi vibes
        "https://images.unsplash.com/photo-1504196606672-aef5c9cefc92?w=1200&q=90"  # Lifestyle
    ],
    "General": [
        "https://images.unsplash.com/photo-1492684223066-81342ee5ff30?w=1200&q=90",
        "https://images.unsplash.com/photo-1505373877841-8d25f7d46678?w=1200&q=90",
        "https://images.unsplash.com/photo-1516280440614-6697288d5d38?w=1200&q=90"
    ]
}

AUTHORITY_SOURCES = [
    "Variety", "The Hollywood Reporter", "Rolling Stone", "Billboard",
    "Deadline", "IGN", "Rotten Tomatoes", "Pitchfork", "Vulture",
    "Entertainment Weekly", "Polygon", "Kotaku", "ScreenRant"
]

CONTENT_DIR = "content/articles"
IMAGE_DIR = "static/images"
DATA_DIR = "automation/data"
MEMORY_FILE = f"{DATA_DIR}/link_memory.json"
TARGET_PER_SOURCE = 5 

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

# --- 🟢 HYBRID IMAGE ENGINE (Anti-Ban Version) ---
def clean_prompt_for_ai(text):
    text = re.sub(r'[^a-zA-Z0-9\s]', '', text)
    return text[:100]

def save_and_optimize_image(content, path):
    try:
        img = Image.open(BytesIO(content)).convert("RGB")
        img = img.resize((1200, 675), Image.Resampling.LANCZOS)
        # Tuning Warna
        enhancer_color = ImageEnhance.Color(img)
        img = enhancer_color.enhance(1.15)
        enhancer_sharp = ImageEnhance.Sharpness(img)
        img = enhancer_sharp.enhance(1.25)
        img.save(path, "WEBP", quality=90)
        return True
    except Exception as e:
        print(f"         ❌ Optimization Error: {e}")
        return False

def download_image_safe(query, category, filename):
    if not filename.endswith(".webp"): filename += ".webp"
    path = os.path.join(IMAGE_DIR, filename)
    
    # 1. Cek Apakah File Sudah Ada (Dan Valid > 5KB)
    if os.path.exists(path) and os.path.getsize(path) > 5000:
        return f"/images/{filename}"

    print(f"      🎨 Processing Image for: {query[:20]}...")

    # 2. LOGIKA ANTI-BAN:
    # Hanya gunakan AI 20% dari waktu. 80% gunakan Stok Foto Asli.
    # Ini supaya IP anda "dingin" kembali.
    use_ai = random.random() < 0.20 

    if use_ai:
        print("         🤖 Method: AI Generation (Flux)...")
        clean_query = clean_prompt_for_ai(query)
        headers = {'User-Agent': 'Mozilla/5.0'}
        
        # Kita pakai model 'flux' biasa saja agar cepat & stabil
        # Jangan pakai realism dulu karena server sedang sibuk/limit
        try:
            prompt = f"cinematic photo of {clean_query}, 4k, hyperrealistic, detailed"
            safe_prompt = requests.utils.quote(prompt)
            url = f"https://image.pollinations.ai/prompt/{safe_prompt}?width=1280&height=720&nologo=true&model=flux&seed={random.randint(1,10000)}"
            
            resp = requests.get(url, headers=headers, timeout=25)
            
            # CEK PENTING: Jika redirect ke URL aneh atau size kecil -> Rate Limit
            if resp.status_code == 200 and len(resp.content) > 15000:
                if save_and_optimize_image(resp.content, path):
                    print("         ✅ AI Success")
                    return f"/images/{filename}"
            else:
                print("         ⚠️ AI Failed/Rate Limit Detected. Switching to Stock.")
        except Exception as e:
            print(f"         ⚠️ AI Error: {e}")

    # 3. FALLBACK UTAMA: STOK FOTO BERKUALITAS (Unsplash)
    # Ini dijamin 100% berhasil dan tidak akan kena ban.
    print(f"         📸 Method: High-Quality Stock Photo ({category})")
    
    # Pilih list gambar berdasarkan kategori
    image_list = CATEGORY_IMAGES_DB.get(category, CATEGORY_IMAGES_DB["General"])
    # Pilih satu gambar secara acak dari list
    selected_url = random.choice(image_list)
    
    try:
        r = requests.get(selected_url, timeout=15)
        if r.status_code == 200:
            img = Image.open(BytesIO(r.content)).convert("RGB")
            img = img.resize((1200, 675), Image.Resampling.LANCZOS)
            img.save(path, "WEBP", quality=90)
            return f"/images/{filename}"
    except: pass
    
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
    print("🎬 Starting glitz Daily Automation (Anti-Ban Mode)...")
    os.makedirs(CONTENT_DIR, exist_ok=True)
    os.makedirs(IMAGE_DIR, exist_ok=True)
    
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
            
            # 🟢 GENERATE IMAGE (Safe Mode)
            image_query = meta.get('keywords', [meta['title']])[0] 
            img_path = download_image_safe(image_query, meta['category'], slug)
            
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
            # 🛑 JEDA WAKTU DITAMBAH (45 DETIK) AGAR TIDAK DIBLOKIR LAGI
            print("      ⏳ Cooling down for 45 seconds...")
            time.sleep(45) 

    print("\n🎉 DONE! Automation Finished.")

if __name__ == "__main__":
    main()
