"""
Harness - Unpaywall Open Access Crawler
Fetches open access veterinary papers from Unpaywall
"""
import os
import time
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import boto3

logger = logging.getLogger(__name__)


class UnpaywallCrawler:
    """Crawler for open access veterinary papers via Unpaywall"""
    
    BASE_URL = "https://api.unpaywall.org/v2"
    
    # Veterinary journal ISSNs
    VETERINARY_JOURNALS = {
        "0042-4900": "Veterinary Record",
        "1746-6148": "BMC Veterinary Research",
        "0165-7380": "Veterinary Research Communications",
        "1297-9716": "Veterinary Research",
        "0378-1135": "Veterinary Microbiology",
        "0304-4017": "Veterinary Parasitology",
        "1090-0233": "The Veterinary Journal",
        "0034-5288": "Research in Veterinary Science",
        "1532-2661": "Journal of Veterinary Emergency and Critical Care",
        "0891-6640": "Journal of Veterinary Internal Medicine",
        "1939-1676": "Journal of Veterinary Internal Medicine (online)",
        "1740-8261": "Veterinary Radiology & Ultrasound",
        "0275-6382": "Veterinary Clinical Pathology",
        "1939-165X": "Journal of the American Veterinary Medical Association",
        "2042-7670": "Journal of Feline Medicine and Surgery",
        "1466-7523": "Journal of Small Animal Practice",
        "2044-3862": "Equine Veterinary Journal",
        "1751-0813": "Australian Veterinary Journal",
    }
    
    def __init__(self, email: str, s3_bucket: str = None):
        self.email = email  # Required by Unpaywall API
        self.s3_bucket = s3_bucket
        self.s3_client = boto3.client('s3') if s3_bucket else None
        
        # Configure session
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
    
    def search_by_doi(self, doi: str) -> Optional[Dict]:
        """Get open access info for a specific DOI"""
        url = f"{self.BASE_URL}/{doi}"
        params = {'email': self.email}
        
        try:
            response = self.session.get(url, params=params, timeout=30)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            
            data = response.json()
            
            # Check if it's open access
            if data.get('is_oa'):
                return {
                    'doi': data.get('doi'),
                    'title': data.get('title'),
                    'journal_name': data.get('journal_name'),
                    'journal_issn': data.get('journal_issn_l'),
                    'published_date': data.get('published_date'),
                    'oa_status': data.get('oa_status'),
                    'best_oa_location': data.get('best_oa_location'),
                    'authors': [
                        f"{author.get('given', '')} {author.get('family', '')}"
                        for author in data.get('z_authors', [])
                    ],
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error fetching DOI {doi}: {str(e)}")
            return None
    
    def get_oa_url(self, paper_data: Dict) -> Optional[str]:
        """Extract best open access URL from paper data"""
        best_location = paper_data.get('best_oa_location', {})
        
        # Prefer PDF URL
        pdf_url = best_location.get('url_for_pdf')
        if pdf_url:
            return pdf_url
        
        # Fall back to landing page URL
        return best_location.get('url')
    
    def download_paper(self, paper_data: Dict) -> Optional[str]:
        """Download open access paper"""
        oa_url = self.get_oa_url(paper_data)
        if not oa_url:
            return None
        
        try:
            response = self.session.get(oa_url, timeout=60, stream=True)
            response.raise_for_status()
            
            # Determine file extension
            content_type = response.headers.get('content-type', '')
            if 'pdf' in content_type:
                ext = 'pdf'
            elif 'xml' in content_type:
                ext = 'xml'
            else:
                ext = 'html'
            
            # Save to S3
            if self.s3_client and self.s3_bucket:
                doi_safe = paper_data['doi'].replace('/', '_').replace('.', '_')
                key = f"raw/unpaywall/{doi_safe}.{ext}"
                
                self.s3_client.upload_fileobj(
                    response.raw,
                    self.s3_bucket,
                    key,
                    ExtraArgs={
                        'Metadata': {
                            'doi': paper_data['doi'],
                            'title': paper_data.get('title', '')[:100],
                            'journal': paper_data.get('journal_name', ''),
                            'oa_status': paper_data.get('oa_status', ''),
                        }
                    }
                )
                
                logger.info(f"Downloaded paper to S3: {key}")
                return key
                
        except Exception as e:
            logger.error(f"Error downloading paper {paper_data['doi']}: {str(e)}")
        
        return None
    
    def search_journal_papers(self, issn: str, days_back: int = 30) -> List[Dict]:
        """Search for recent papers from a specific journal"""
        # Note: Unpaywall doesn't have a direct journal search API
        # This would need to be combined with another source like Crossref
        # For now, returning empty list as placeholder
        logger.info(f"Journal search for ISSN {issn} not implemented yet")
        return []
    
    def process_doi_batch(self, dois: List[str]) -> List[Dict]:
        """Process a batch of DOIs in parallel"""
        results = []
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_doi = {
                executor.submit(self.search_by_doi, doi): doi 
                for doi in dois
            }
            
            for future in as_completed(future_to_doi):
                doi = future_to_doi[future]
                try:
                    paper_data = future.result()
                    if paper_data:
                        # Download the paper
                        pdf_key = self.download_paper(paper_data)
                        if pdf_key:
                            paper_data['pdf_s3_key'] = pdf_key
                        results.append(paper_data)
                        
                except Exception as e:
                    logger.error(f"Error processing DOI {doi}: {str(e)}")
                
                # Rate limiting
                time.sleep(0.1)
        
        return results
    
    def enrich_with_crossref_data(self, issn: str, days_back: int = 7) -> List[str]:
        """Get recent DOIs from Crossref for a journal"""
        # This would integrate with Crossref API to get recent papers
        # then check them against Unpaywall
        crossref_url = "https://api.crossref.org/works"
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        
        params = {
            'filter': f'issn:{issn},from-pub-date:{start_date.strftime("%Y-%m-%d")},until-pub-date:{end_date.strftime("%Y-%m-%d")}',
            'rows': 1000,
            'mailto': self.email,
        }
        
        try:
            response = self.session.get(crossref_url, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            items = data.get('message', {}).get('items', [])
            
            dois = [item.get('DOI') for item in items if item.get('DOI')]
            return dois
            
        except Exception as e:
            logger.error(f"Error querying Crossref: {str(e)}")
            return []
    
    def crawl_veterinary_journals(self, days_back: int = 7) -> Dict:
        """Main method to crawl veterinary journals for OA papers"""
        all_papers = []
        
        for issn, journal_name in self.VETERINARY_JOURNALS.items():
            logger.info(f"Checking {journal_name} (ISSN: {issn})")
            
            # Get recent DOIs from Crossref
            dois = self.enrich_with_crossref_data(issn, days_back)
            logger.info(f"Found {len(dois)} recent papers in {journal_name}")
            
            if dois:
                # Check Unpaywall for OA versions
                oa_papers = self.process_doi_batch(dois)
                all_papers.extend(oa_papers)
                logger.info(f"Found {len(oa_papers)} OA papers in {journal_name}")
        
        # Save metadata
        if all_papers and self.s3_bucket:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_path = f"s3://{self.s3_bucket}/metadata/unpaywall/unpaywall_{timestamp}.json"
            
            self.s3_client.put_object(
                Bucket=self.s3_bucket,
                Key=f"metadata/unpaywall/unpaywall_{timestamp}.json",
                Body=json.dumps(all_papers, indent=2),
                ContentType='application/json'
            )
            
            logger.info(f"Saved metadata to {output_path}")
        
        return {
            'total_papers_checked': sum(len(self.enrich_with_crossref_data(issn, days_back)) 
                                       for issn in self.VETERINARY_JOURNALS),
            'oa_papers_found': len(all_papers),
            'pdfs_downloaded': len([p for p in all_papers if 'pdf_s3_key' in p]),
        }


def main():
    """Run Unpaywall crawler"""
    crawler = UnpaywallCrawler(
        email="harness@example.com",  # Replace with actual email
        s3_bucket='harness-veterinary-corpus-development'
    )
    
    results = crawler.crawl_veterinary_journals(days_back=7)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()