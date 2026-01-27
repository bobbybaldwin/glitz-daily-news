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

RSS_SOURCES = {
    "Entertainment US": "https://news.google.com/rss/headlines/section/topic/ENTERTAINMENT?hl=en-US&gl=US&ceid=US:en",
    "Gaming News": "https://news.google.com/rss/search?q=gaming+news+esports&hl=en-US&gl=US&ceid=US:en",
    "Pop Culture": "https://news.google.com/rss/search?q=pop+culture+trends&hl=en-US&gl=US&ceid=US:en"
}

# 🟢 SMART CATEGORY FALLBACKS (Jika AI Gagal Total)
CATEGORY_FALLBACKS = {
    "Movies & Film": "https://images.unsplash.com/photo-1489599849927-2ee91cede3ba?w=1200&q=80",
    "TV Shows & Streaming": "https://images.unsplash.com/photo-1574375927938-d5a98e8ffe85?w=1200&q=80",
    "Music & Concerts": "https://images.unsplash.com/photo-1493225255756-d9584f8606e9?w=1200&q=80",
    "Celebrity & Lifestyle": "https://images.unsplash.com/photo-1515634928627-2a4e0dae3ddf?w=1200&q=80",
    "Anime & Manga": "https://images.unsplash.com/photo-1541562232579-512a21360020?w=1200&q=80",
    "Gaming & Esports": "https://images.unsplash.com/photo-1542751371-adc38448a05e?w=1200&q=80",
    "Pop Culture Trends": "https://images.unsplash.com/photo-1598899134739-24c46f58b8c0?w=1200&q=80",
    "General": "https://images.unsplash.com/photo-1492684223066-81342ee5ff30?w=1200&q=80"
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

# --- 🛠️ REPAIR MARKDOWN (Format Fixer) ---
def repair_markdown_formatting(text):
    if not text: return ""
    # Fix Tables
    text = text.replace("| — |", "|---|").replace("|—|", "|---|")
    text = re.sub(r'\|\s*\|', '|\n|', text)
    text = text.replace('|---|---|', '|---|---|\n').replace('|---|', '|---|\n')
    # Fix Lists
    text = re.sub(r'(?<!\n)\s-\s\[', '\n- [', text) 
    text = re.sub(r'(?<!\n)\s-\s\*\*', '\n- **', text)
    # Fix Headers spacing
    text = text.replace("###", "\n\n###").replace("##", "\n\n##")
    return text

# --- 🟢 ULTIMATE IMAGE ENGINE (Google Discover Optimized) ---
def clean_prompt_for_ai(text):
    # Hapus karakter aneh, ambil intinya saja
    text = re.sub(r'[^a-zA-Z0-9\s]', '', text)
    return text[:100] # Batasi panjang agar AI fokus

def save_and_optimize_image(content, path):
    """Fungsi pembantu untuk memproses gambar"""
    try:
        img = Image.open(BytesIO(content)).convert("RGB")
        img = img.resize((1200, 675), Image.Resampling.LANCZOS)
        
        # Tuning untuk Google Discover (Lebih tajam & Vivid)
        enhancer_color = ImageEnhance.Color(img)
        img = enhancer_color.enhance(1.15) # +15% Vibrance
        enhancer_sharp = ImageEnhance.Sharpness(img)
        img = enhancer_sharp.enhance(1.25) # +25% Tajam
        
        img.save(path, "WEBP", quality=90)
        return True
    except Exception as e:
        print(f"         ❌ Optimization Error: {e}")
        return False

def download_image_safe(query, category, filename):
    if not filename.endswith(".webp"): filename += ".webp"
    path = os.path.join(IMAGE_DIR, filename)
    
    # Cek cache file
    if os.path.exists(path) and os.path.getsize(path) > 5000:
        return f"/images/{filename}"

    print(f"      🎨 Generating Discover Image for: {query[:20]}...")
    clean_query = clean_prompt_for_ai(query)
    headers = {'User-Agent': 'Mozilla/5.0'}

    # ---------------------------------------------------------
    # TIER 1: FLUX-REALISM (Target: Google Discover)
    # ---------------------------------------------------------
    try:
        # Prompt khusus Realism
        prompt_realism = f"editorial photography of {clean_query}, award winning photo, 8k, highly detailed, dramatic lighting, depth of field, f/1.8, bokeh, no text"
        safe_prompt = requests.utils.quote(prompt_realism)
        
        # Timeout kita naikkan jadi 45 detik demi kualitas
        url_realism = f"https://image.pollinations.ai/prompt/{safe_prompt}?width=1280&height=720&nologo=true&model=flux-realism&seed={random.randint(1,10000)}"
        
        resp = requests.get(url_realism, headers=headers, timeout=45)
        
        if resp.status_code == 200 and len(resp.content) > 20000:
            if save_and_optimize_image(resp.content, path):
                print("         ✅ Tier 1: Flux-Realism Success")
                return f"/images/{filename}"
        
        print("         ⚠️ Tier 1 Failed/Timeout. Switching to Tier 2...")
    except Exception as e:
        print(f"         ⚠️ Tier 1 Error: {e}")

    # ---------------------------------------------------------
    # TIER 2: FLUX STANDARD + "FAKE REALISM" PROMPT
    # (Jauh lebih stabil, tapi kita paksa jadi realistis via prompt)
    # ---------------------------------------------------------
    try:
        # Prompt kita perkeras agar Flux biasa terlihat seperti Realism
        prompt_fake_realism = f"hyperrealistic photo of {clean_query}, 4k resolution, cinematic focus, sharp details, professional photography, vivid colors"
        safe_prompt_2 = requests.utils.quote(prompt_fake_realism)
        
        url_flux = f"https://image.pollinations.ai/prompt/{safe_prompt_2}?width=1280&height=720&nologo=true&model=flux&seed={random.randint(1,10000)}"
        
        resp = requests.get(url_flux, headers=headers, timeout=30)
        
        if resp.status_code == 200 and len(resp.content) > 20000:
            if save_and_optimize_image(resp.content, path):
                print("         ✅ Tier 2: Flux (Enhanced) Success")
                return f"/images/{filename}"
            
    except Exception as e:
        print(f"         ⚠️ Tier 2 Error: {e}")

    # ---------------------------------------------------------
    # TIER 3: SMART CATEGORY STOCK (Anti-Gagal)
    # ---------------------------------------------------------
    print(f"      ❌ AI Gen Failed. Using Fallback for: {category}")
    return download_category_fallback(category, path, filename)

def download_category_fallback(category, path, filename):
    fallback_url = CATEGORY_FALLBACKS.get(category, CATEGORY_FALLBACKS["General"])
    try:
        r = requests.get(fallback_url, timeout=15)
        if r.status_code == 200:
            img = Image.open(BytesIO(r.content)).convert("RGB")
            img = img.resize((1200, 675), Image.Resampling.LANCZOS)
            img.save(path, "WEBP", quality=85)
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
    print("🎬 Starting glitz Daily Automation (Ultimate Edition)...")
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
            
            final_content = format_content_structure(raw_content)
            
            # 🟢 SMART IMAGE GENERATION (Tiered Strategy)
            # Prioritas keyword untuk gambar: Main Keyword -> Title
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
            time.sleep(15) 

    print("\n🎉 DONE! Automation Finished.")

if __name__ == "__main__":
    main()
