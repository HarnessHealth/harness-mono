"""
Harness - PubMed/PMC Crawler
Specialized crawler for veterinary papers from PubMed and PMC
"""
import os
import time
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import xml.etree.ElementTree as ET

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class PubMedCrawler:
    """Crawler for PubMed and PubMed Central veterinary papers"""
    
    BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
    PMC_FTP = "https://ftp.ncbi.nlm.nih.gov/pub/pmc/"
    
    # Veterinary-specific search terms
    SEARCH_TERMS = [
        '"veterinary"[MeSH Terms]',
        '"animal diseases"[MeSH Terms]',
        '"veterinary medicine"[MeSH Terms]',
        '"dogs"[MeSH Terms] AND ("diseases"[Title/Abstract] OR "clinical"[Title/Abstract])',
        '"cats"[MeSH Terms] AND ("diseases"[Title/Abstract] OR "clinical"[Title/Abstract])',
        '"horses"[MeSH Terms] AND ("diseases"[Title/Abstract] OR "clinical"[Title/Abstract])',
        '"cattle"[MeSH Terms] AND ("diseases"[Title/Abstract] OR "clinical"[Title/Abstract])',
        '"veterinary pathology"[Title/Abstract]',
        '"veterinary surgery"[Title/Abstract]',
        '"veterinary oncology"[Title/Abstract]',
        '"veterinary dermatology"[Title/Abstract]',
        '"veterinary cardiology"[Title/Abstract]',
    ]
    
    def __init__(self, api_key: Optional[str] = None, s3_bucket: str = None):
        self.api_key = api_key or os.environ.get('NCBI_API_KEY')
        self.s3_bucket = s3_bucket
        self.s3_client = boto3.client('s3') if s3_bucket else None
        
        # Configure session with retries
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
    
    def search_papers(self, 
                     start_date: datetime, 
                     end_date: datetime,
                     max_results: int = 10000) -> List[str]:
        """Search for veterinary papers in date range"""
        all_pmids = set()
        
        date_str = f"{start_date.strftime('%Y/%m/%d')}:{end_date.strftime('%Y/%m/%d')}[PDAT]"
        
        for term in self.SEARCH_TERMS:
            query = f"{term} AND {date_str}"
            params = {
                'db': 'pubmed',
                'term': query,
                'retmode': 'json',
                'retmax': max_results,
                'api_key': self.api_key,
            }
            
            try:
                response = self.session.get(
                    f"{self.BASE_URL}esearch.fcgi",
                    params=params,
                    timeout=30
                )
                response.raise_for_status()
                
                data = response.json()
                pmids = data.get('esearchresult', {}).get('idlist', [])
                all_pmids.update(pmids)
                
                logger.info(f"Found {len(pmids)} papers for term: {term}")
                
                # Respect NCBI rate limits
                time.sleep(0.34 if self.api_key else 1)
                
            except Exception as e:
                logger.error(f"Error searching with term {term}: {str(e)}")
        
        return list(all_pmids)
    
    def fetch_paper_metadata(self, pmids: List[str]) -> List[Dict]:
        """Fetch detailed metadata for papers"""
        metadata_list = []
        
        # Process in batches
        batch_size = 200
        for i in range(0, len(pmids), batch_size):
            batch = pmids[i:i + batch_size]
            
            params = {
                'db': 'pubmed',
                'id': ','.join(batch),
                'retmode': 'xml',
                'api_key': self.api_key,
            }
            
            try:
                response = self.session.get(
                    f"{self.BASE_URL}efetch.fcgi",
                    params=params,
                    timeout=60
                )
                response.raise_for_status()
                
                # Parse XML
                root = ET.fromstring(response.content)
                
                for article in root.findall('.//PubmedArticle'):
                    metadata = self._parse_article_xml(article)
                    if metadata:
                        metadata_list.append(metadata)
                
                time.sleep(0.34 if self.api_key else 1)
                
            except Exception as e:
                logger.error(f"Error fetching metadata batch: {str(e)}")
        
        return metadata_list
    
    def _parse_article_xml(self, article_elem) -> Dict:
        """Parse PubMed XML article element"""
        try:
            pmid = article_elem.find('.//PMID').text
            
            # Extract basic metadata
            metadata = {
                'pmid': pmid,
                'title': article_elem.find('.//ArticleTitle').text or '',
                'abstract': '',
                'authors': [],
                'journal': '',
                'pub_date': '',
                'mesh_terms': [],
                'keywords': [],
                'doi': '',
                'pmc_id': '',
            }
            
            # Abstract
            abstract_elem = article_elem.find('.//AbstractText')
            if abstract_elem is not None:
                metadata['abstract'] = abstract_elem.text or ''
            
            # Authors
            for author in article_elem.findall('.//Author'):
                last_name = author.find('LastName')
                fore_name = author.find('ForeName')
                if last_name is not None and fore_name is not None:
                    metadata['authors'].append(f"{fore_name.text} {last_name.text}")
            
            # Journal
            journal_elem = article_elem.find('.//Journal/Title')
            if journal_elem is not None:
                metadata['journal'] = journal_elem.text
            
            # Publication date
            pub_date = article_elem.find('.//PubDate')
            if pub_date is not None:
                year = pub_date.find('Year')
                month = pub_date.find('Month')
                if year is not None:
                    metadata['pub_date'] = f"{year.text}"
                    if month is not None:
                        metadata['pub_date'] += f"-{month.text}"
            
            # MeSH terms
            for mesh in article_elem.findall('.//MeshHeading/DescriptorName'):
                metadata['mesh_terms'].append(mesh.text)
            
            # Keywords
            for keyword in article_elem.findall('.//Keyword'):
                if keyword.text:
                    metadata['keywords'].append(keyword.text)
            
            # DOI
            for article_id in article_elem.findall('.//ArticleId'):
                if article_id.get('IdType') == 'doi':
                    metadata['doi'] = article_id.text
                elif article_id.get('IdType') == 'pmc':
                    metadata['pmc_id'] = article_id.text
            
            return metadata
            
        except Exception as e:
            logger.error(f"Error parsing article XML: {str(e)}")
            return None
    
    def download_full_text(self, metadata: Dict) -> Optional[str]:
        """Download full text PDF from PMC if available"""
        if not metadata.get('pmc_id'):
            return None
        
        pmc_id = metadata['pmc_id']
        pdf_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmc_id}/pdf/"
        
        try:
            response = self.session.get(pdf_url, timeout=60, stream=True)
            response.raise_for_status()
            
            # Save to S3
            if self.s3_client and self.s3_bucket:
                key = f"raw/pubmed/{metadata['pmid']}_{pmc_id}.pdf"
                
                self.s3_client.upload_fileobj(
                    response.raw,
                    self.s3_bucket,
                    key,
                    ExtraArgs={
                        'Metadata': {
                            'pmid': metadata['pmid'],
                            'pmc_id': pmc_id,
                            'doi': metadata.get('doi', ''),
                            'title': metadata.get('title', '')[:100],
                        }
                    }
                )
                
                logger.info(f"Uploaded PDF to S3: {key}")
                return key
            
        except Exception as e:
            logger.debug(f"Could not download PDF for PMC{pmc_id}: {str(e)}")
        
        return None
    
    def save_metadata(self, metadata_list: List[Dict], output_path: str):
        """Save metadata to JSON file or S3"""
        if output_path.startswith('s3://'):
            # Save to S3
            bucket = output_path.split('/')[2]
            key = '/'.join(output_path.split('/')[3:])
            
            self.s3_client.put_object(
                Bucket=bucket,
                Key=key,
                Body=json.dumps(metadata_list, indent=2),
                ContentType='application/json'
            )
        else:
            # Save locally
            with open(output_path, 'w') as f:
                json.dump(metadata_list, f, indent=2)
    
    def crawl_date_range(self, start_date: datetime, end_date: datetime) -> Dict:
        """Main crawling method for a date range"""
        logger.info(f"Crawling PubMed from {start_date} to {end_date}")
        
        # Search for papers
        pmids = self.search_papers(start_date, end_date)
        logger.info(f"Found {len(pmids)} unique papers")
        
        # Fetch metadata
        metadata_list = self.fetch_paper_metadata(pmids)
        logger.info(f"Fetched metadata for {len(metadata_list)} papers")
        
        # Download PDFs where available
        pdf_count = 0
        for metadata in metadata_list:
            pdf_key = self.download_full_text(metadata)
            if pdf_key:
                metadata['pdf_s3_key'] = pdf_key
                pdf_count += 1
        
        logger.info(f"Downloaded {pdf_count} PDFs")
        
        # Save metadata
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_path = f"s3://{self.s3_bucket}/metadata/pubmed/pubmed_{timestamp}.json"
        self.save_metadata(metadata_list, output_path)
        
        return {
            'papers_found': len(pmids),
            'metadata_fetched': len(metadata_list),
            'pdfs_downloaded': pdf_count,
            'metadata_path': output_path,
        }


def main():
    """Run PubMed crawler"""
    crawler = PubMedCrawler(
        api_key=os.environ.get('NCBI_API_KEY'),
        s3_bucket='harness-veterinary-corpus-development'
    )
    
    # Crawl last 7 days
    end_date = datetime.now()
    start_date = end_date - timedelta(days=7)
    
    results = crawler.crawl_date_range(start_date, end_date)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()