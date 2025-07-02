"""
Harness - IVIS (International Veterinary Information Service) Crawler
Crawls conference proceedings and books from IVIS with authentication
"""
import os
import re
import time
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple

import requests
from bs4 import BeautifulSoup
import boto3
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

logger = logging.getLogger(__name__)


class IVISCrawler:
    """Crawler for IVIS veterinary resources with authentication"""
    
    BASE_URL = "https://www.ivis.org"
    LOGIN_URL = "https://www.ivis.org/user/login"
    
    # Key sections to crawl
    SECTIONS = {
        'proceedings': '/library/proceedings',
        'books': '/library/books',
        'advances': '/library/advances-in-veterinary-medicine',
        'clinical_updates': '/library/clinical-updates',
    }
    
    def __init__(self, username: str, password: str, s3_bucket: str = None):
        self.username = username
        self.password = password
        self.s3_bucket = s3_bucket
        self.s3_client = boto3.client('s3') if s3_bucket else None
        self.session = requests.Session()
        self.logged_in = False
        
    def login_with_requests(self) -> bool:
        """Login to IVIS using requests session"""
        try:
            # Get login page to retrieve CSRF token
            login_page = self.session.get(self.LOGIN_URL)
            soup = BeautifulSoup(login_page.text, 'html.parser')
            
            # Find CSRF token (adjust selector based on actual form)
            csrf_token = None
            csrf_input = soup.find('input', {'name': 'csrf_token'}) or \
                        soup.find('input', {'name': '_csrf_token'}) or \
                        soup.find('input', {'name': 'authenticity_token'})
            
            if csrf_input:
                csrf_token = csrf_input.get('value')
            
            # Prepare login data
            login_data = {
                'name': self.username,  # or 'email' depending on form
                'pass': self.password,  # or 'password'
                'form_id': 'user_login_form',  # adjust based on actual form
                'op': 'Log in',
            }
            
            if csrf_token:
                login_data['csrf_token'] = csrf_token
            
            # Submit login
            headers = {
                'User-Agent': 'Mozilla/5.0 (compatible; HarnessBot/1.0)',
                'Referer': self.LOGIN_URL,
            }
            
            response = self.session.post(
                self.LOGIN_URL,
                data=login_data,
                headers=headers,
                allow_redirects=True
            )
            
            # Check if login successful
            if response.status_code == 200 and 'logout' in response.text.lower():
                self.logged_in = True
                logger.info("Successfully logged in to IVIS")
                return True
            else:
                logger.error("Failed to login to IVIS")
                return False
                
        except Exception as e:
            logger.error(f"Error during IVIS login: {str(e)}")
            return False
    
    def login_with_selenium(self, driver) -> bool:
        """Alternative login method using Selenium for JavaScript-heavy sites"""
        try:
            driver.get(self.LOGIN_URL)
            
            # Wait for login form
            wait = WebDriverWait(driver, 10)
            
            # Find and fill username
            username_field = wait.until(
                EC.presence_of_element_located((By.NAME, "name"))
            )
            username_field.send_keys(self.username)
            
            # Find and fill password
            password_field = driver.find_element(By.NAME, "pass")
            password_field.send_keys(self.password)
            
            # Submit form
            submit_button = driver.find_element(By.ID, "edit-submit")
            submit_button.click()
            
            # Wait for redirect/login success
            time.sleep(3)
            
            # Check if logged in
            if 'logout' in driver.page_source.lower():
                self.logged_in = True
                
                # Transfer cookies to requests session
                for cookie in driver.get_cookies():
                    self.session.cookies.set(cookie['name'], cookie['value'])
                
                logger.info("Successfully logged in to IVIS via Selenium")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error during Selenium login: {str(e)}")
            return False
    
    def crawl_proceedings(self, limit: int = 50) -> List[Dict]:
        """Crawl conference proceedings"""
        if not self.logged_in:
            if not self.login_with_requests():
                return []
        
        proceedings = []
        
        try:
            url = f"{self.BASE_URL}{self.SECTIONS['proceedings']}"
            response = self.session.get(url)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find proceedings listings (adjust selectors based on actual HTML)
            # This is an example - actual selectors will vary
            for item in soup.find_all('div', class_='views-row')[:limit]:
                title_elem = item.find('h3') or item.find('h2')
                if not title_elem:
                    continue
                
                title = title_elem.get_text(strip=True)
                link_elem = title_elem.find('a')
                
                if link_elem:
                    relative_url = link_elem.get('href')
                    full_url = f"{self.BASE_URL}{relative_url}" if relative_url.startswith('/') else relative_url
                    
                    # Extract additional metadata
                    date_elem = item.find('span', class_='date')
                    date = date_elem.get_text(strip=True) if date_elem else ''
                    
                    conference_elem = item.find('span', class_='conference')
                    conference = conference_elem.get_text(strip=True) if conference_elem else ''
                    
                    proceedings.append({
                        'title': title,
                        'url': full_url,
                        'date': date,
                        'conference': conference,
                        'type': 'proceedings',
                        'source': 'IVIS',
                    })
            
            logger.info(f"Found {len(proceedings)} proceedings")
            
        except Exception as e:
            logger.error(f"Error crawling proceedings: {str(e)}")
        
        return proceedings
    
    def crawl_books(self, limit: int = 20) -> List[Dict]:
        """Crawl veterinary books"""
        if not self.logged_in:
            if not self.login_with_requests():
                return []
        
        books = []
        
        try:
            url = f"{self.BASE_URL}{self.SECTIONS['books']}"
            response = self.session.get(url)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract book listings
            for item in soup.find_all('div', class_='book-item')[:limit]:
                title = item.find('h3').get_text(strip=True) if item.find('h3') else ''
                
                # Get book chapters or sections
                chapters = []
                for chapter in item.find_all('li', class_='chapter'):
                    chapter_title = chapter.get_text(strip=True)
                    chapter_link = chapter.find('a')
                    if chapter_link:
                        chapters.append({
                            'title': chapter_title,
                            'url': f"{self.BASE_URL}{chapter_link.get('href')}",
                        })
                
                if title:
                    books.append({
                        'title': title,
                        'chapters': chapters,
                        'type': 'book',
                        'source': 'IVIS',
                    })
            
            logger.info(f"Found {len(books)} books")
            
        except Exception as e:
            logger.error(f"Error crawling books: {str(e)}")
        
        return books
    
    def download_resource(self, resource: Dict) -> Optional[str]:
        """Download a specific resource (PDF, etc.)"""
        if not self.logged_in:
            return None
        
        try:
            url = resource.get('url')
            if not url:
                return None
            
            # Check if it's a PDF link
            response = self.session.head(url, allow_redirects=True)
            content_type = response.headers.get('content-type', '')
            
            if 'pdf' not in content_type:
                # Try to find PDF link on the page
                page_response = self.session.get(url)
                soup = BeautifulSoup(page_response.text, 'html.parser')
                
                # Look for PDF download link
                pdf_link = soup.find('a', {'class': 'pdf-download'}) or \
                          soup.find('a', href=re.compile(r'\.pdf'))
                
                if pdf_link:
                    pdf_url = pdf_link.get('href')
                    if pdf_url.startswith('/'):
                        pdf_url = f"{self.BASE_URL}{pdf_url}"
                    url = pdf_url
                else:
                    return None
            
            # Download the PDF
            response = self.session.get(url, stream=True)
            response.raise_for_status()
            
            # Generate filename
            title_safe = re.sub(r'[^\w\s-]', '', resource.get('title', 'unknown'))[:100]
            title_safe = re.sub(r'[-\s]+', '-', title_safe)
            timestamp = datetime.now().strftime('%Y%m%d')
            filename = f"IVIS_{timestamp}_{title_safe}.pdf"
            
            # Upload to S3
            if self.s3_client and self.s3_bucket:
                key = f"raw/ivis/{filename}"
                
                self.s3_client.upload_fileobj(
                    response.raw,
                    self.s3_bucket,
                    key,
                    ExtraArgs={
                        'Metadata': {
                            'source': 'IVIS',
                            'title': resource.get('title', '')[:255],
                            'type': resource.get('type', 'unknown'),
                            'url': url[:255],
                            'crawl_date': datetime.now().isoformat(),
                        }
                    }
                )
                
                logger.info(f"Downloaded: {key}")
                return key
            
        except Exception as e:
            logger.error(f"Error downloading resource: {str(e)}")
        
        return None
    
    def crawl_all(self, download_pdfs: bool = True) -> Dict:
        """Crawl all IVIS resources"""
        results = {
            'proceedings': [],
            'books': [],
            'downloaded': [],
        }
        
        # Login first
        if not self.login_with_requests():
            logger.error("Failed to login to IVIS")
            return results
        
        # Crawl proceedings
        proceedings = self.crawl_proceedings()
        results['proceedings'] = proceedings
        
        # Crawl books
        books = self.crawl_books()
        results['books'] = books
        
        # Download PDFs if requested
        if download_pdfs:
            # Download proceedings
            for proc in proceedings[:20]:  # Limit downloads
                pdf_key = self.download_resource(proc)
                if pdf_key:
                    results['downloaded'].append({
                        'resource': proc,
                        's3_key': pdf_key,
                    })
                time.sleep(2)  # Be polite
            
            # Download book chapters
            for book in books[:5]:  # Limit downloads
                for chapter in book.get('chapters', [])[:3]:
                    pdf_key = self.download_resource(chapter)
                    if pdf_key:
                        results['downloaded'].append({
                            'resource': chapter,
                            's3_key': pdf_key,
                        })
                    time.sleep(2)
        
        # Save metadata
        if self.s3_bucket:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            metadata_key = f"metadata/ivis/ivis_crawl_{timestamp}.json"
            
            self.s3_client.put_object(
                Bucket=self.s3_bucket,
                Key=metadata_key,
                Body=json.dumps(results, indent=2),
                ContentType='application/json'
            )
            
            logger.info(f"Saved metadata to s3://{self.s3_bucket}/{metadata_key}")
        
        return results


def main():
    """Run IVIS crawler"""
    # Get credentials from environment or Airflow
    username = os.environ.get('IVIS_USERNAME')
    password = os.environ.get('IVIS_PASSWORD')
    
    if not username or not password:
        logger.error("IVIS credentials not found in environment")
        return
    
    crawler = IVISCrawler(
        username=username,
        password=password,
        s3_bucket='harness-veterinary-corpus-development'
    )
    
    results = crawler.crawl_all(download_pdfs=True)
    
    print(f"Crawled {len(results['proceedings'])} proceedings")
    print(f"Crawled {len(results['books'])} books")
    print(f"Downloaded {len(results['downloaded'])} PDFs")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()