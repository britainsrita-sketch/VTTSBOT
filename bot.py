import os
import logging
import re
from collections import Counter
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# CONFIGURATION
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

def extract_domain(url):
    """Extracts a clean domain name from a URL."""
    parsed = urlparse(url)
    domain = parsed.netloc if parsed.netloc else parsed.path
    return domain.replace("www.", "")

def analyze_website(url):
    """Scrapes a target website to extract statistics and key topics."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        response = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 1. Gather Basic Statistics
        title = soup.title.string.strip() if soup.title else "No Title Found"
        links_count = len(soup.find_all('a'))
        images_count = len(soup.find_all('img'))
        
        # 2. Extract Meta Content for Similarity Analysis
        meta_desc = ""
        meta_keywords = []
        
        desc_tag = soup.find('meta', attrs={'name': 'description'}) or soup.find('meta', attrs={'property': 'og:description'})
        if desc_tag and desc_tag.get('content'):
            meta_desc = desc_tag['content'].strip()
            
        key_tag = soup.find('meta', attrs={'name': 'keywords'})
        if key_tag and key_tag.get('content'):
            meta_keywords = [k.strip().lower() for k in key_tag['content'].split(',') if k.strip()]

        # 3. Text Frequency Strategy (If meta tags are missing)
        if not meta_keywords and soup.body:
            text = soup.body.get_text()
            words = re.findall(r'\b[a-zA-Z]{4,15}\b', text.lower())
            # Simple stop-words filter
            stop_words = {'this', 'that', 'with', 'from', 'your', 'have', 'about', 'online', 'home', 'page'}
            filtered_words = [w for w in words if w not in stop_words]
            meta_keywords = [item[0] for item in Counter(filtered_words).most_common(5)]

        return {
            "success": True,
            "title": title,
            "links": links_count,
            "images": images_count,
            "description": meta_desc[:120] + "..." if len(meta_desc) > 120 else meta_desc,
            "keywords": meta_keywords[:5]
        }
    except Exception as e:
        logger.error(f"Error scraping {url}: {e}")
        return {"success": False, "error": str(e)}

def find_similar_sites(keywords, original_domain):
    """Finds alternative domains by parsing a search engine's duckduckgo HTML text."""
    if not keywords:
        return []
        
    search_query = "+".join(keywords[:3]) + "+website"
    url = f"https://html.duckduckgo.com/html/?q={search_query}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    
    similar_domains = []
    try:
        res = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # Scrape result links from DDG native HTML layout
        for a in soup.find_all('a', class_='result__url'):
            href = a.get('href', '')
            found_domain = extract_domain(href)
            
            if found_domain and found_domain != original_domain and found_domain not in similar_domains:
                similar_domains.append(found_domain)
                if len(similar_domains) >= 4:  # Return top 4 unique matches
                    break
    except Exception as e:
        logger.error(f"Error finding similar sites: {e}")
        
    return similar_domains

# TELEGRAM HANDLERS
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔍 **Welcome to Website Finder & Stats Bot!**\n\n"
        "Send me any website URL (e.g., https://example.com), and I will "
        "extract internal statistics and find structurally similar alternatives."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_url = update.message.text.strip()
    
    if not user_url.startswith("http"):
        user_url = "https://" + user_url

    status_msg = await update.message.reply_text("⏳ Analyzing code architecture and metrics...")
    
    # Run structural check
    domain = extract_domain(user_url)
    stats = analyze_website(user_url)
    
    if not stats["success"]:
        await status_msg.edit_text("❌ Could not pull statistics for that URL. Make sure it is public and valid.")
        return

    # Find alternatives using extracted target keywords
    alternatives = find_similar_sites(stats["keywords"], domain)
    
    # Format alternative display string
    if alternatives:
        similar_text = "\n".join([f"• `{site}`" for site in alternatives])
    else:
        similar_text = "No immediate alternative sites found with matching niches."

    response_text = (
        f"📊 **Website Statistics for:** `{domain}`\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 **Title:** {stats['title']}\n"
        f"📝 **Description:** {stats['description'] or 'N/A'}\n"
        f"🔗 **Total Outbound/Inbound Links:** {stats['links']}\n"
        f"🖼️ **Total Images Found:** {stats['images']}\n"
        f"🔑 **Extracted Category Focus:** {', '.join(stats['keywords'])}\n\n"
        f"🌎 **Similar Websites Found:**\n"
        f"{similar_text}"
    )
    
    await status_msg.edit_text(response_text, parse_mode="Markdown")

def main():
    logger.info("🤖 Launching Website Finder Background Worker...")
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Infinite polling mode safe for Background Workers
    application.run_polling()

if __name__ == "__main__":
    main()
