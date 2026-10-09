import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import time
import json

def crawl_multiple_seeds(seed_urls, max_pages=50):

    allowed_domains = {urlparse(url).netloc for url in seed_urls}
    
    # Initialize the queue with all seed URLs
    queue = seed_urls.copy()
    visited = set()
    scraped_data = []
    
    ignore_extensions = ['.pdf', '.jpg', '.jpeg', '.png', '.gif', '.mp4', '.zip', '.docx']

    print(f"Starting deep scrape across {len(seed_urls)} seed URLs...")
    print(f"Allowed domains: {', '.join(allowed_domains)}\n")

    while queue and len(visited) < max_pages:
        current_url = queue.pop(0)
        
        if current_url in visited:
            continue
            
        print(f"[{len(visited) + 1}/{max_pages}] Scraping: {current_url}")
        
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            response = requests.get(current_url, headers=headers, timeout=10)
            
            visited.add(current_url)
            
            if response.status_code != 200:
                continue

            soup = BeautifulSoup(response.text, 'html.parser')
            
            for element in soup(["nav", "footer", "header", "script", "style"]):
                element.decompose()
                
            title = soup.title.string.strip() if soup.title else "No Title"
            content = " ".join([p.get_text(strip=True) for p in soup.find_all(['p', 'h1', 'h2', 'h3', 'li'])])
            
            if len(content) > 50:
                scraped_data.append({
                    "url": current_url,
                    "title": title,
                    "content": content
                })
            
            for a_tag in soup.find_all('a', href=True):
                href = a_tag['href']
                full_url = urljoin(current_url, href).split('#')[0]
                
                link_domain = urlparse(full_url).netloc
                is_allowed_domain = link_domain in allowed_domains
                
                is_new = full_url not in visited and full_url not in queue
                is_not_file = not any(full_url.lower().endswith(ext) for ext in ignore_extensions)
                
                if is_allowed_domain and is_new and is_not_file:
                    queue.append(full_url)
                    
            time.sleep(1)

        except requests.exceptions.RequestException as e:
            print(f"  -> Failed to load {current_url}: {e}")

    return scraped_data

if __name__ == "__main__":
    SEEDS = [
        "https://www.engr.psu.edu/partnership-opportunities/index.aspx",
        "https://career.engr.psu.edu/index.aspx",
        "https://www.engr.psu.edu/academics/organizations.aspx",
        "https://lf.psu.edu/sponsors/sponsor-a-project/",
        "https://www.engr.psu.edu/research/index.aspx",
        "https://www.me.psu.edu/industry/index.aspx"
    ]
    
    # Run the crawler
    data = crawl_multiple_seeds(SEEDS, max_pages=100)
    
    # Save the output
    with open('multi_seed_scrape_data.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
        
    print(f"\nFinished! Scraped {len(data)} pages.")