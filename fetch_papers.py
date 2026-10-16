import os
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import json
import time

RESEARCH_DIR = "C:\\Users\\Chidiebere\\Documents\\3. ZKP Compute\\Research"
os.makedirs(RESEARCH_DIR, exist_ok=True)

QUERIES = {
    "ZKML": 'all:"zero knowledge" AND all:"machine learning"',
    "TEE": 'all:"trusted execution environment" AND all:"machine learning"',
    "Cloud_Economics_Africa": 'all:"cloud computing" AND (all:"Africa" OR all:"latency")',
    "Data_Privacy": 'all:"data privacy" AND all:"federated learning"'
}

citations = {}

def fetch_arxiv_papers(category, query, max_results=5):
    print(f"[*] Searching for {category} papers...")
    
    url = f"http://export.arxiv.org/api/query?search_query={urllib.parse.quote(query)}&start=0&max_results={max_results}&sortBy=submittedDate&sortOrder=descending"
    
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'})
        response = urllib.request.urlopen(req)
        xml_data = response.read()
        root = ET.fromstring(xml_data)
        
        ns = {'arxiv': 'http://www.w3.org/2005/Atom'}
        
        count = 0
        for entry in root.findall('arxiv:entry', ns):
            title = entry.find('arxiv:title', ns).text.replace('\n', ' ').strip()
            published = entry.find('arxiv:published', ns).text[:4] # Get year
            
            # Skip older than 2020
            if int(published) < 2020:
                continue
                
            authors = [author.find('arxiv:name', ns).text for author in entry.findall('arxiv:author', ns)]
            author_str = ", ".join(authors[:3]) + (" et al." if len(authors) > 3 else "")
            
            pdf_url = None
            for link in entry.findall('arxiv:link', ns):
                if link.get('title') == 'pdf':
                    pdf_url = link.get('href')
                    break
                    
            if not pdf_url:
                continue
                
            pdf_url = pdf_url.replace("http://", "https://") + ".pdf"
            
            # Create safe filename
            safe_title = "".join([c for c in title if c.isalpha() or c.isdigit() or c==' ']).rstrip()
            filename = f"[{category}] {published} - {safe_title[:50]}.pdf"
            filepath = os.path.join(RESEARCH_DIR, filename)
            
            print(f"  -> Downloading: {filename}")
            try:
                pdf_req = urllib.request.Request(pdf_url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(pdf_req) as response_pdf, open(filepath, 'wb') as out_file:
                    out_file.write(response_pdf.read())
                
                # APA 7 formatting rough approximation
                apa_citation = f"{authors[0]} et al. ({published}). {title}. arXiv preprint."
                
                citations[filename] = {
                    "category": category,
                    "title": title,
                    "authors": authors,
                    "year": published,
                    "url": pdf_url,
                    "apa_7": apa_citation
                }
                
                count += 1
                time.sleep(1) # Be polite to arXiv API
            except Exception as e:
                print(f"  [!] Failed to download {pdf_url}: {e}")
                
        print(f"[+] Downloaded {count} papers for {category}")
        
    except Exception as e:
        print(f"[!] Search failed for {category}: {e}")

for cat, q in QUERIES.items():
    fetch_arxiv_papers(cat, q, 6) # Fetch 6 to guarantee we get ~5 after filtering

with open(os.path.join(RESEARCH_DIR, "citations.json"), "w") as f:
    json.dump(citations, f, indent=4)
    
print("\n[+] All papers downloaded and citations generated in citations.json!")
