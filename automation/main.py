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

AUTHORITY_SOURCES = [
    "Variety", "The Hollywood Reporter", "Rolling Stone", "Billboard",
    "Deadline", "IGN", "Rotten Tomatoes", "Pitchfork", "Vulture",
    "Entertainment Weekly", "Polygon", "Kotaku", "ScreenRant"
]

FALLBACK_IMAGES = [
    "https://images.unsplash.com/photo-1489599849927-2ee91cede3ba?w=1200&q=80",
    "https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=1200&q=80",
    "https://images.unsplash.com/photo-1492684223066-81342ee5ff30?w=1200&q=80",
    "https://images.unsplash.com/photo-1536440136628-849c177e76a1?w=1200&q=80",
    "https://images.unsplash.com/photo-1542751371-adc38448a05e?w=1200&q=80",
    "https://images.unsplash.com/photo-1598899134739-24c46f58b8c0?w=1200&q=80",
    "https://images.unsplash.com/photo-1574375927938-d5a98e8ffe85?w=1200&q=80",
    "https://images.unsplash.com/photo-1514525253440-b393452e8d26?w=1200&q=80",
    "https://images.unsplash.com/photo-1616469829581-73993eb86b02?w=1200&q=80",
    "https://images.unsplash.com/photo-1478720568477-152d9b164e63?w=1200&q=80"
]

RSS_SOURCES = {
    "Entertainment US": "https://news.google.com/rss/headlines/section/topic/ENTERTAINMENT?hl=en-US&gl=US&ceid=US:en",
    "Gaming News": "https://news.google.com/rss/search?q=gaming+news+esports&hl=en-US&gl=US&ceid=US:en",
    "Pop Culture": "https://news.google.com/rss/search?q=pop+culture+trends&hl=en-US&gl=US&ceid=US:en"
}

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
        # Gunakan format bullet point yang tegas
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

# --- 🛠️ NEW: REPAIR MARKDOWN (TABEL & LIST) ---
def repair_markdown_formatting(text):
    """
    Memperbaiki tabel dan list yang 'gepeng' (satu baris) menjadi format Markdown yang benar.
    """
    if not text: return ""

    # 1. PERBAIKI TABEL (Penyebab utama layout berantakan)
    # Ganti separator em-dash (—) atau dash (-) yang nyangkut
    text = text.replace("| — |", "|---|").replace("|—|", "|---|")
    
    # Masalah: "| Col 1 | Col 2 | | Val 1 |" -> Baris nempel
    # Solusi: Jika ada "| |", itu tandanya baris baru yang hilang.
    text = re.sub(r'\|\s*\|', '|\n|', text)
    
    # Pastikan Header Table terpisah dari body
    text = text.replace('|---|---|', '|---|---|\n')
    text = text.replace('|---|', '|---|\n')

    # 2. PERBAIKI INTERNAL LINKS & LIST
    # Masalah: "articles: - Link 1 - Link 2"
    # Solusi: Paksa enter sebelum bullet point strip (-) ATAU bintang (*)
    # Regex lookbehind: Jika ada spasi sebelum strip, dan bukan di awal baris, beri enter.
    # Hati-hati: Jangan merusak kalimat biasa "word - word". 
    # Kita targetkan yang terlihat seperti list item "- [Link]" atau "- **Bold**"
    text = re.sub(r'(?<!\n)\s-\s\[', '\n- [', text) 
    text = re.sub(r'(?<!\n)\s-\s\*\*', '\n- **', text)

    # 3. PASTIKAN SPASI ANTAR SECTION
    text = text.replace("###", "\n\n###")
    text = text.replace("##", "\n\n##")
    
    return text

# --- 🟢 IMAGE ENGINE ---
def download_image_safe(query, filename):
    if not filename.endswith(".webp"): filename += ".webp"
    path = os.path.join(IMAGE_DIR, filename)
    if os.path.exists(path): return f"/images/{filename}"

    if random.random() < 0.80:
        return download_fallback_image(path, filename)

    print(f"      🎨 Generating Bright Image for: {query[:20]}...")

    try:
        prompt = f"{query}, bright studio lighting, vibrant colors, 8k resolution, hyperrealistic, high contrast, pop culture aesthetic, award winning photography, golden hour, clear focus"
        safe_prompt = requests.utils.quote(prompt[:300])
        url = f"https://image.pollinations.ai/prompt/{safe_prompt}?width=1280&height=720&nologo=true&model=flux-realism&seed={random.randint(1,10000)}"
        
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, headers=headers, timeout=25)
        
        if resp.status_code == 200 and len(resp.content) > 50000: 
            img = Image.open(BytesIO(resp.content)).convert("RGB")
            img = img.resize((1200, 675), Image.Resampling.LANCZOS)
            
            enhancer_sharp = ImageEnhance.Sharpness(img)
            img = enhancer_sharp.enhance(1.4) 
            enhancer_color = ImageEnhance.Color(img)
            img = enhancer_color.enhance(1.25)
            
            img.save(path, "WEBP", quality=90)
            return f"/images/{filename}"
        else:
            return download_fallback_image(path, filename)
    except:
        return download_fallback_image(path, filename)

def download_fallback_image(path, filename):
    try:
        url = random.choice(FALLBACK_IMAGES)
        r = requests.get(url, timeout=10)
        img = Image.open(BytesIO(r.content)).convert("RGB")
        img = img.resize((1200, 675))
        img.save(path, "WEBP")
        return f"/images/{filename}"
    except:
        return "/images/default-entertainment.jpg"

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
    # Panggil fungsi perbaikan Markdown TERLEBIH DAHULU
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
    
    # 🔴 PERBAIKAN PROMPT: Instruksi Tegas untuk Formatting
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
    print("🎬 Starting glitz Daily Automation (Markdown Fix Active)...")
    os.makedirs(CONTENT_DIR, exist_ok=True)
    os.makedirs(IMAGE_DIR, exist_ok=True)
    
    for source, url in RSS_SOURCES.items():
        print(f"\n📡 Scanning: {source}...")
        feed = feedparser.parse(url)
        if not feed.entries: continue
        
        success_count = 0
        for entry in feed.entries:
            if success_count >= TARGET_PER_SOURCE: 
                break
            
            clean_title = clean_camel_case(entry.title.split(" - ")[0])
            print(f"   ✨ Analyzing: {clean_title[:30]}...")

            meta = get_metadata(clean_title, entry.summary)
            if not meta: continue
            
            meta['title'] = clean_camel_case(meta['title'])
            if meta['category'] not in VALID_CATEGORIES:
                meta['category'] = "Movies & Film"
            
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
            
            # 🟢 STEP PENTING: FORMATTING
            final_content = format_content_structure(raw_content)
            
            img_path = download_image_safe(meta['title'], slug)
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
            time.sleep(15) 

    print("\n🎉 DONE! Automation Finished.")

if __name__ == "__main__":
    main()
