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

# 🟢 AUTHORITY SOURCES (External Links Candidates)
AUTHORITY_SOURCES = [
    "Variety", "The Hollywood Reporter", "Rolling Stone", "Billboard",
    "Deadline", "IGN", "Rotten Tomatoes", "Pitchfork", "Vulture",
    "Entertainment Weekly", "Polygon", "Kotaku", "ScreenRant"
]

# 🟢 FALLBACK IMAGES
FALLBACK_IMAGES = [
    "https://images.unsplash.com/photo-1489599849927-2ee91cede3ba?w=1200&q=80", # Cinema
    "https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=1200&q=80", # Music Mic
    "https://images.unsplash.com/photo-1492684223066-81342ee5ff30?w=1200&q=80", # Concert
    "https://images.unsplash.com/photo-1536440136628-849c177e76a1?w=1200&q=80", # Hollywood
    "https://images.unsplash.com/photo-1542751371-adc38448a05e?w=1200&q=80",  # Gaming
    "https://images.unsplash.com/photo-1598899134739-24c46f58b8c0?w=1200&q=80", # Movie Set
    "https://images.unsplash.com/photo-1574375927938-d5a98e8ffe85?w=1200&q=80", # Netflix
    "https://images.unsplash.com/photo-1514525253440-b393452e8d26?w=1200&q=80", # Club
    "https://images.unsplash.com/photo-1616469829581-73993eb86b02?w=1200&q=80", # Esports
    "https://images.unsplash.com/photo-1478720568477-152d9b164e63?w=1200&q=80", # Reels
    "https://images.unsplash.com/photo-1470225620780-dba8ba36b745?w=1200&q=80", # DJ
    "https://images.unsplash.com/photo-1511512578047-dfb367046420?w=1200&q=80", # Gamer
    "https://images.unsplash.com/photo-1586899028174-e7098604235b?w=1200&q=80", # Popcorn
    "https://images.unsplash.com/photo-1460723237483-7a6dc9d0b212?w=1200&q=80", # Red Carpet
    "https://images.unsplash.com/photo-1533174072545-e8d4aa97edf9?w=1200&q=80", # Spotlight
    "https://images.unsplash.com/photo-1493225255756-d9584f8606e9?w=1200&q=80", # Surfer
    "https://images.unsplash.com/photo-1515634928627-2a4e0dae3ddf?w=1200&q=80", # Fashion
    "https://images.unsplash.com/photo-1501281668745-f7f57925c3b4?w=1200&q=80", # Event
    "https://images.unsplash.com/photo-1594909122845-11baa439b7bf?w=1200&q=80", # K-Pop
    "https://images.unsplash.com/photo-1516280440614-6697288d5d38?w=1200&q=80"  # Party
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
        links.append(f"- [{title}]({url})")
    return "\n".join(links)

# --- 🟢 JSON REPAIR ENGINE ---
def repair_json(json_str):
    try:
        return json.loads(json_str) 
    except:
        json_str = re.sub(r'(\w+):', r'"\1":', json_str) 
        try: return json.loads(json_str)
        except: return None

# --- 🟢 IMAGE ENGINE (STRICT FILTER) ---
def download_image_safe(query, filename):
    if not filename.endswith(".webp"): filename += ".webp"
    path = os.path.join(IMAGE_DIR, filename)
    if os.path.exists(path): return f"/images/{filename}"

    # 🟢 STRATEGI: 80% Pake Stock Photo (Biar Gak Limit & Kelihatan Pro)
    if random.random() < 0.80:
        return download_fallback_image(path, filename)

    print(f"      🎨 Generating Bright Image for: {query[:20]}...")

    try:
        prompt = f"{query}, bright studio lighting, vibrant colors, 8k resolution, hyperrealistic, high contrast, pop culture aesthetic, award winning photography, golden hour, clear focus"
        safe_prompt = requests.utils.quote(prompt[:300])
        url = f"https://image.pollinations.ai/prompt/{safe_prompt}?width=1280&height=720&nologo=true&model=flux-realism&seed={random.randint(1,10000)}"
        
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, headers=headers, timeout=25)
        
        # 🟢 STRICT CHECK: File harus > 50KB. 
        if resp.status_code == 200 and len(resp.content) > 50000: 
            img = Image.open(BytesIO(resp.content)).convert("RGB")
            img = img.resize((1200, 675), Image.Resampling.LANCZOS)
            
            enhancer_sharp = ImageEnhance.Sharpness(img)
            img = enhancer_sharp.enhance(1.4) 
            enhancer_color = ImageEnhance.Color(img)
            img = enhancer_color.enhance(1.25)
            enhancer_contrast = ImageEnhance.Contrast(img)
            img = enhancer_contrast.enhance(1.15)
            
            img.save(path, "WEBP", quality=90)
            return f"/images/{filename}"
        else:
            print("      ⚠️ Image Rate Limit / File Too Small. Using Stock Photo.")
            return download_fallback_image(path, filename)
    except Exception as e:
        print(f"      ⚠️ Image Gen Error: {e}")
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
    except Exception as e:
        pass

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
    Return JSON ONLY:
    {{
        "title": "Clickworthy Title (No quotes)",
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
    except Exception as e:
        print(f"      ❌ Groq Metadata Error: {e}")
        return None

def write_article(metadata, summary, internal_links, author, external_sources_str):
    api_key = random.choice(GROQ_API_KEYS)
    client = Groq(api_key=api_key)
    
    prompt = f"""
    You are {author}. Write a 1000-word article on: "{metadata['title']}"
    Context: {summary}
    
    INTERNAL LINKS (Inject these):
    {internal_links}
    
    EXTERNAL AUTHORITY (Cite these using MARKDOWN LINKS e.g. [Source](url)):
    {external_sources_str}
    
    STRUCTURE RULES:
    1. **Hook** (No "Introduction" header).
    2. **Unique H2 Headline**: Creative title.
    3. **Key Details (H2)**: Markdown Table required.
    4. **Social Reactions (H2)**: Specific header.
    5. **Must Read (H2)**: Paste INTERNAL LINKS here.
    6. **Industry Insight (H2)**: Discuss impact and CITATION of external sources ({external_sources_str}). You MUST create a hyperlink.
    7. **Conclusion (H2)**: Creative header.
    8. **FAQ (H2)**: 3 Questions/Answers (Q: / A: format).

    IMPORTANT: Output MARKDOWN only. Finish the article.
    """
    
    try:
        chat = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.75, 
            max_tokens=6500 
        )
        return chat.choices[0].message.content
    except Exception as e:
        print(f"      ❌ Groq Writing Error: {e}")
        return None

# --- MAIN LOOP ---
def main():
    print("🎬 Starting glitz Daily Automation (Safe Mode)...")
    os.makedirs(CONTENT_DIR, exist_ok=True)
    os.makedirs(IMAGE_DIR, exist_ok=True)
    
    for source, url in RSS_SOURCES.items():
        print(f"\n📡 Scanning: {source}...")
        feed = feedparser.parse(url)
        if not feed.entries: continue
        
        success_count = 0
        for entry in feed.entries:
            if success_count >= TARGET_PER_SOURCE: 
                print(f"   🛑 Target reached for {source}. Moving to next.")
                break
            
            clean_title = entry.title.split(" - ")[0]
            print(f"   ✨ Analyzing: {clean_title[:30]}...")

            # 1. Metadata
            meta = get_metadata(clean_title, entry.summary)
            if not meta: 
                continue
            
            if meta['category'] not in VALID_CATEGORIES:
                meta['category'] = "Movies & Film"
            
            slug = slugify(meta['title'])
            filename = f"{slug}.md"
            filepath = os.path.join(CONTENT_DIR, filename)
            
            if os.path.exists(filepath):
                print(f"      ⏭️  Skipped: {slug} (Already Exists)")
                continue
            
            # 2. Content Preparation (WITH EXTERNAL LINKS LOGGING)
            author = random.choice(AUTHOR_PROFILES)
            links = get_internal_links()
            
            # 🟢 PILIH 2 SUMBER EXTERNAL SECARA ACAK
            selected_external = random.sample(AUTHORITY_SOURCES, 2)
            external_str = ", ".join(selected_external)
            
            # 🟢 LOGGING UNTUK ANDA
            print(f"      🔗 Injecting External Sources: {external_str}")
            
            raw_content = write_article(meta, entry.summary, links, author, external_str)
            
            if not raw_content: continue
            
            # 3. Process
            final_content = format_content_structure(raw_content)
            
            # 4. Image
            img_path = download_image_safe(meta['title'], slug)
            
            # 5. Save
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
            
            # 6. Indexing
            full_url = f"{WEBSITE_URL}/{slug}/"
            submit_to_indexnow(full_url)
            submit_to_google(full_url)
            
            print(f"      ✅ Published: {filename}")
            
            success_count += 1
            time.sleep(15) 

    print("\n🎉 DONE! Automation Finished.")

if __name__ == "__main__":
    main()
