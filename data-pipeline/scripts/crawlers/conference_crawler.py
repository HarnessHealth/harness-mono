"""
Harness - Veterinary Conference Proceedings Crawler
Crawls proceedings from major veterinary conferences
"""
import os
import re
import time
import json
import logging
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
import boto3
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

logger = logging.getLogger(__name__)


class ConferenceCrawler:
    """Crawler for veterinary conference proceedings"""
    
    CONFERENCE_SOURCES = {
        'ACVIM': {
            'name': 'American College of Veterinary Internal Medicine',
            'url': 'https://www.acvim.org/Publications/Proceedings',
            'strategy': 'selenium',  # Some sites need JS rendering
        },
        'WSAVA': {
            'name': 'World Small Animal Veterinary Association',
            'url': 'https://wsava.org/global-guidelines/global-pain-council/',
            'strategy': 'requests',
        },
        'IVECCS': {
            'name': 'International Veterinary Emergency and Critical Care Symposium',
            'url': 'https://iveccs.org/proceedings/',
            'strategy': 'requests',
        },
        'BSAVA': {
            'name': 'British Small Animal Veterinary Association',
            'url': 'https://www.bsava.com/Resources/Veterinary-resources/Scientific-proceedings',
            'strategy': 'requests',
        },
        'ECVIM': {
            'name': 'European College of Veterinary Internal Medicine',
            'url': 'https://www.ecvim-ca.org/congress',
            'strategy': 'requests',
        },
        'VCS': {
            'name': 'Veterinary Cancer Society',
            'url': 'https://vetcancersociety.org/vcs-conference/',
            'strategy': 'requests',
        },
    }
    
    def __init__(self, s3_bucket: str = None):
        self.s3_bucket = s3_bucket
        self.s3_client = boto3.client('s3') if s3_bucket else None
        
        # Setup requests session
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (compatible; HarnessBot/1.0; +https://harness.vet/bot)'
        })
        
        # Setup Selenium for JS-heavy sites
        self.driver = None
    
    def _init_selenium(self):
        """Initialize Selenium WebDriver"""
        if self.driver is None:
            options = Options()
            options.add_argument('--headless')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            
            # Use Chrome driver
            self.driver = webdriver.Chrome(options=options)
    
    def _close_selenium(self):
        """Close Selenium WebDriver"""
        if self.driver:
            self.driver.quit()
            self.driver = None
    
    def extract_pdf_links(self, url: str, html: str) -> List[Tuple[str, str]]:
        """Extract PDF links from HTML"""
        soup = BeautifulSoup(html, 'html.parser')
        pdf_links = []
        
        # Common patterns for PDF links
        pdf_patterns = [
            r'\.pdf$',
            r'\.pdf\?',
            r'/pdf/',
            r'/download/pdf',
            r'type=pdf',
        ]
        
        # Find all links
        for link in soup.find_all('a', href=True):
            href = link['href']
            text = link.get_text(strip=True)
            
            # Check if it's likely a PDF
            if any(re.search(pattern, href, re.IGNORECASE) for pattern in pdf_patterns):
                full_url = urljoin(url, href)
                pdf_links.append((full_url, text))
            
            # Also check link text for PDF indicators
            elif any(keyword in text.lower() for keyword in ['pdf', 'download', 'proceedings', 'abstract']):
                full_url = urljoin(url, href)
                pdf_links.append((full_url, text))
        
        return pdf_links
    
    def crawl_with_requests(self, conference: str, config: Dict) -> List[Dict]:
        """Crawl conference site using requests"""
        results = []
        
        try:
            response = self.session.get(config['url'], timeout=30)
            response.raise_for_status()
            
            pdf_links = self.extract_pdf_links(config['url'], response.text)
            logger.info(f"Found {len(pdf_links)} potential PDFs on {conference} site")
            
            for pdf_url, title in pdf_links[:50]:  # Limit to 50 per conference
                paper_info = self.download_pdf(pdf_url, title, conference)
                if paper_info:
                    results.append(paper_info)
                time.sleep(1)  # Be polite
            
        except Exception as e:
            logger.error(f"Error crawling {conference}: {str(e)}")
        
        return results
    
    def crawl_with_selenium(self, conference: str, config: Dict) -> List[Dict]:
        """Crawl conference site using Selenium for JS-rendered content"""
        results = []
        
        try:
            self._init_selenium()
            self.driver.get(config['url'])
            
            # Wait for content to load
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # Get page source after JS execution
            html = self.driver.page_source
            
            pdf_links = self.extract_pdf_links(config['url'], html)
            logger.info(f"Found {len(pdf_links)} potential PDFs on {conference} site")
            
            for pdf_url, title in pdf_links[:50]:
                paper_info = self.download_pdf(pdf_url, title, conference)
                if paper_info:
                    results.append(paper_info)
                time.sleep(1)
            
        except Exception as e:
            logger.error(f"Error crawling {conference} with Selenium: {str(e)}")
        
        return results
    
    def download_pdf(self, url: str, title: str, conference: str) -> Optional[Dict]:
        """Download PDF and save to S3"""
        try:
            # Clean filename
            safe_title = re.sub(r'[^\w\s-]', '', title)[:100]
            safe_title = re.sub(r'[-\s]+', '-', safe_title)
            
            response = self.session.get(url, timeout=60, stream=True)
            response.raise_for_status()
            
            # Check if it's actually a PDF
            content_type = response.headers.get('content-type', '')
            if 'pdf' not in content_type.lower() and not url.endswith('.pdf'):
                logger.debug(f"Skipping non-PDF: {url}")
                return None
            
            # Generate S3 key
            timestamp = datetime.now().strftime('%Y%m%d')
            filename = f"{conference}_{timestamp}_{safe_title}.pdf"
            key = f"raw/conferences/{conference}/{filename}"
            
            # Upload to S3
            if self.s3_client and self.s3_bucket:
                self.s3_client.upload_fileobj(
                    response.raw,
                    self.s3_bucket,
                    key,
                    ExtraArgs={
                        'Metadata': {
                            'source_url': url[:255],
                            'conference': conference,
                            'title': title[:255],
                            'crawl_date': datetime.now().isoformat(),
                        }
                    }
                )
                
                logger.info(f"Downloaded: {key}")
                
                return {
                    'conference': conference,
                    'title': title,
                    'url': url,
                    's3_key': key,
                    'crawl_date': datetime.now().isoformat(),
                }
            
        except Exception as e:
            logger.error(f"Error downloading {url}: {str(e)}")
        
        return None
    
    def crawl_all_conferences(self) -> Dict:
        """Crawl all configured conferences"""
        all_results = []
        
        for conference, config in self.CONFERENCE_SOURCES.items():
            logger.info(f"Crawling {config['name']}...")
            
            if config['strategy'] == 'selenium':
                results = self.crawl_with_selenium(conference, config)
            else:
                results = self.crawl_with_requests(conference, config)
            
            all_results.extend(results)
            logger.info(f"Downloaded {len(results)} papers from {conference}")
        
        # Close Selenium if used
        self._close_selenium()
        
        # Save metadata
        if all_results and self.s3_bucket:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            metadata_key = f"metadata/conferences/conference_papers_{timestamp}.json"
            
            self.s3_client.put_object(
                Bucket=self.s3_bucket,
                Key=metadata_key,
                Body=json.dumps(all_results, indent=2),
                ContentType='application/json'
            )
            
            logger.info(f"Saved metadata to s3://{self.s3_bucket}/{metadata_key}")
        
        return {
            'total_papers': len(all_results),
            'by_conference': {
                conf: len([r for r in all_results if r['conference'] == conf])
                for conf in self.CONFERENCE_SOURCES
            }
        }
    
    def search_conference_archives(self, keywords: List[str]) -> List[Dict]:
        """Search for specific topics in conference proceedings"""
        # This could be extended to search within downloaded PDFs
        # or use conference-specific search APIs
        pass


def main():
    """Run conference crawler"""
    crawler = ConferenceCrawler(
        s3_bucket='harness-veterinary-corpus-development'
    )
    
    results = crawler.crawl_all_conferences()
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()