"""
Harness - GROBID PDF Processing Lambda Function
Processes veterinary papers using GROBID to extract structured content
"""
import os
import json
import logging
import tempfile
from typing import Dict, List, Optional
from datetime import datetime
import hashlib
from urllib.parse import urljoin
import time

import boto3
import requests
from botocore.exceptions import ClientError

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Environment variables
GROBID_ENDPOINT = os.environ.get('GROBID_ENDPOINT', 'http://grobid.harness.internal:8070')
S3_CORPUS_BUCKET = os.environ.get('S3_CORPUS_BUCKET', 'harness-veterinary-corpus-development')
S3_TRAINING_BUCKET = os.environ.get('S3_TRAINING_BUCKET', 'harness-training-data-development')
NCBI_API_KEY = os.environ.get('NCBI_API_KEY')
CROSSREF_EMAIL = os.environ.get('CROSSREF_EMAIL')

# Initialize AWS clients
s3_client = boto3.client('s3')
sqs_client = boto3.client('sqs')


def crawl_pubmed_papers(max_papers=100):
    """Crawl papers from PubMed API"""
    import requests
    from datetime import datetime, timedelta
    
    logger.info("Starting PubMed crawl...")
    
    # Get date range for historical crawl - 1 year back
    one_year_ago = (datetime.now() - timedelta(days=365)).strftime('%Y/%m/%d')
    today = datetime.now().strftime('%Y/%m/%d')
    
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {
        'db': 'pubmed',
        'term': '(veterinary[MeSH Terms] OR "animal diseases"[MeSH Terms] OR (dog OR canine OR cat OR feline OR equine OR bovine))',
        'retmax': max_papers,
        'retmode': 'json',
        'datetype': 'pdat',
        'mindate': one_year_ago,
        'maxdate': today,
    }
    
    # Add API key if available for higher rate limits
    if NCBI_API_KEY:
        params['api_key'] = NCBI_API_KEY
        logger.info("Using NCBI API key for higher rate limits")
    
    try:
        response = requests.get(base_url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        pmids = data.get('esearchresult', {}).get('idlist', [])
        logger.info(f"Found {len(pmids)} PubMed articles")
        
        # Fetch detailed information for each PMID
        papers = []
        if pmids:
            # Process papers in batches of 200 (NCBI API limit)
            batch_size = 200
            for i in range(0, min(len(pmids), max_papers), batch_size):
                batch_pmids = pmids[i:i+batch_size]
                
                detail_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
                detail_params = {
                    'db': 'pubmed',
                    'id': ','.join(batch_pmids),
                    'retmode': 'json'
                }
                
                if NCBI_API_KEY:
                    detail_params['api_key'] = NCBI_API_KEY
                
                detail_response = requests.get(detail_url, params=detail_params, timeout=30)
                detail_response.raise_for_status()
                detail_data = detail_response.json()
                
                result = detail_data.get('result', {})
                for pmid in batch_pmids:
                    if pmid in result:
                        paper_data = result[pmid]
                        papers.append({
                            'pmid': pmid,
                            'title': paper_data.get('title', ''),
                            'authors': paper_data.get('authors', []),
                            'journal': paper_data.get('source', ''),
                            'pubdate': paper_data.get('pubdate', ''),
                            'abstract': paper_data.get('abstract', ''),
                            'source': 'pubmed'
                        })
        
        return papers
        
    except Exception as e:
        logger.error(f"Error crawling PubMed: {str(e)}")
        return []


def crawl_pmc_papers(max_papers=100):
    """Crawl papers from PubMed Central (PMC) API for open access papers"""
    import requests
    from datetime import datetime, timedelta
    
    logger.info("Starting PMC crawl...")
    
    # Get date range for historical crawl - 1 year back
    one_year_ago = (datetime.now() - timedelta(days=365)).strftime('%Y/%m/%d')
    today = datetime.now().strftime('%Y/%m/%d')
    
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {
        'db': 'pmc',  # Use PMC database instead of PubMed
        'term': '(veterinary[MeSH Terms] OR "animal diseases"[MeSH Terms] OR (dog OR canine OR cat OR feline OR equine OR bovine)) AND open access[filter]',
        'retmax': max_papers,
        'retmode': 'json',
        'datetype': 'pdat',
        'mindate': one_year_ago,
        'maxdate': today,
    }
    
    # Add API key if available for higher rate limits
    if NCBI_API_KEY:
        params['api_key'] = NCBI_API_KEY
        logger.info("Using NCBI API key for higher rate limits")
    
    try:
        response = requests.get(base_url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        pmcids = data.get('esearchresult', {}).get('idlist', [])
        logger.info(f"Found {len(pmcids)} PMC open access articles")
        
        # Fetch detailed information for each PMCID
        papers = []
        if pmcids:
            # Process papers in batches of 200 (NCBI API limit)
            batch_size = 200
            for i in range(0, min(len(pmcids), max_papers), batch_size):
                batch_pmcids = pmcids[i:i+batch_size]
                
                detail_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
                detail_params = {
                    'db': 'pmc',
                    'id': ','.join(batch_pmcids),
                    'retmode': 'json'
                }
                
                if NCBI_API_KEY:
                    detail_params['api_key'] = NCBI_API_KEY
                
                detail_response = requests.get(detail_url, params=detail_params, timeout=30)
                detail_response.raise_for_status()
                detail_data = detail_response.json()
                
                result = detail_data.get('result', {})
                for pmcid in batch_pmcids:
                    if pmcid in result:
                        paper_data = result[pmcid]
                        # PMC IDs need to be prefixed with PMC
                        pmc_id = f"PMC{pmcid}" if not pmcid.startswith('PMC') else pmcid
                        
                        # Handle authors field (can be list or dict)
                        authors = []
                        author_data = paper_data.get('authors', [])
                        if isinstance(author_data, list):
                            authors = [str(author) for author in author_data if author]
                        elif isinstance(author_data, dict):
                            authors = [author.get('name', '') for author in author_data.get('author', [])]
                        
                        # Handle article IDs 
                        pmid = ''
                        articleids = paper_data.get('articleids', {})
                        if isinstance(articleids, dict):
                            pmid = articleids.get('pubmed', '')
                        
                        papers.append({
                            'pmcid': pmc_id,
                            'pmid': pmid,
                            'title': paper_data.get('title', ''),
                            'authors': authors,
                            'journal': paper_data.get('fulljournalname', paper_data.get('source', '')),
                            'pubdate': paper_data.get('pubdate', ''),
                            'abstract': '',  # PMC summary doesn't include abstract, will get from full text
                            'source': 'pmc'
                        })
        
        return papers
        
    except Exception as e:
        logger.error(f"Error crawling PMC: {str(e)}")
        return []


def crawl_europe_pmc_papers(max_papers=50):
    """Crawl papers from Europe PMC API"""
    import requests
    from datetime import datetime, timedelta
    
    logger.info("Starting Europe PMC crawl...")
    
    one_year_ago = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
    today = datetime.now().strftime('%Y-%m-%d')
    
    base_url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    params = {
        'query': f'SUBJECT:"veterinary" OR SUBJECT:"animal diseases" AND UPDATE_DATE:[{one_year_ago} TO {today}]',
        'format': 'json',
        'pageSize': max_papers,
        'cursorMark': '*',
    }
    
    headers = {}
    if CROSSREF_EMAIL:
        headers['User-Agent'] = f'Harness/1.0 (mailto:{CROSSREF_EMAIL})'
    
    try:
        response = requests.get(base_url, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        articles = data.get('resultList', {}).get('result', [])
        logger.info(f"Found {len(articles)} Europe PMC articles")
        
        papers = []
        for article in articles:
            papers.append({
                'pmid': article.get('pmid', ''),
                'pmcid': article.get('pmcid', ''),
                'title': article.get('title', ''),
                'authors': [author.get('fullName', '') for author in article.get('authorList', {}).get('author', [])],
                'journal': article.get('journalInfo', {}).get('journal', {}).get('title', ''),
                'pubdate': article.get('firstPublicationDate', ''),
                'abstract': article.get('abstractText', ''),
                'source': 'europe_pmc'
            })
        
        return papers
        
    except Exception as e:
        logger.error(f"Error crawling Europe PMC: {str(e)}")
        return []


def get_pdf_urls(papers):
    """Get PDF download URLs for papers, optimized for PMC open access papers"""
    pdf_urls = []
    
    for paper in papers:
        potential_urls = []
        paper_id = paper.get('pmcid') or paper.get('pmid')
        
        # PMC papers - these are guaranteed open access
        if paper.get('pmcid'):
            pmcid = paper['pmcid']
            if pmcid.startswith('PMC'):
                # PMC URLs are most reliable for open access papers
                potential_urls.extend([
                    f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/pdf/",
                    f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/pdf/{pmcid}.pdf",
                    f"https://europepmc.org/articles/{pmcid}?pdf=render",
                    f"https://ftp.ncbi.nlm.nih.gov/pub/pmc/oa_pdf/{pmcid[:6]}/{pmcid}.pdf"  # PMC FTP access
                ])
        
        # For PubMed papers without PMC ID, try to find PMC version
        elif paper.get('pmid'):
            pmid = paper['pmid']
            
            # Try to find PMC version through elink API first  
            try:
                link_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/elink.fcgi"
                link_params = {
                    'dbfrom': 'pubmed',
                    'db': 'pmc',
                    'id': pmid,
                    'retmode': 'json'
                }
                if NCBI_API_KEY:
                    link_params['api_key'] = NCBI_API_KEY
                
                response = requests.get(link_url, params=link_params, timeout=10)
                if response.status_code == 200:
                    link_data = response.json()
                    linksets = link_data.get('linksets', [])
                    for linkset in linksets:
                        linksetdbs = linkset.get('linksetdbs', [])
                        for linksetdb in linksetdbs:
                            if linksetdb.get('dbto') == 'pmc':
                                pmc_ids = linksetdb.get('links', [])
                                if pmc_ids:
                                    # Found PMC ID, use multiple formats
                                    pmc_id = f"PMC{pmc_ids[0]}"
                                    potential_urls.extend([
                                        f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmc_id}/pdf/",
                                        f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmc_id}/pdf/{pmc_id}.pdf",
                                        f"https://europepmc.org/articles/{pmc_id}?pdf=render"
                                    ])
            except:
                # Fallback if elink fails
                pass
        
        # Only include papers with potential URLs
        if potential_urls:
            pdf_urls.append({
                'paper_id': paper_id,
                'pdf_urls': potential_urls,  # Multiple URLs to try
                'paper': paper
            })
    
    return pdf_urls


def download_pdf(pdf_urls, paper_id):
    """Download PDF from multiple potential URLs"""
    for i, pdf_url in enumerate(pdf_urls):
        try:
            logger.info(f"Attempting PDF download for {paper_id} from {pdf_url} (attempt {i+1}/{len(pdf_urls)})")
            
            headers = {
                'User-Agent': 'Harness/1.0 (mailto:admin@harness.health) Research Purpose'
            }
            
            response = requests.get(pdf_url, headers=headers, timeout=60, stream=True)
            
            # Check if we got a PDF
            content_type = response.headers.get('content-type', '')
            if response.status_code == 200 and 'pdf' in content_type.lower():
                logger.info(f"Successfully downloaded PDF for {paper_id} from {pdf_url}")
                return response.content
            else:
                logger.warning(f"Failed attempt {i+1} for {paper_id}: {response.status_code}, content-type: {content_type}")
                continue
                
        except Exception as e:
            logger.warning(f"Error on attempt {i+1} for {paper_id}: {str(e)}")
            continue
    
    logger.error(f"All PDF download attempts failed for {paper_id}")
    return None


def extract_text_from_pdf(pdf_content, paper_id):
    """Extract structured text directly from PDF using Python libraries"""
    try:
        logger.info(f"Processing PDF for text extraction: {paper_id}")
        
        # Use PyPDF2/pdfplumber for text extraction
        import io
        from io import BytesIO
        
        # Try to import PDF processing libraries (fallback if not available)
        try:
            import PyPDF2
            use_pypdf2 = True
        except ImportError:
            use_pypdf2 = False
            logger.warning("PyPDF2 not available, using basic text extraction")
        
        try:
            import pdfplumber
            use_pdfplumber = True
        except ImportError:
            use_pdfplumber = False
            logger.warning("pdfplumber not available")
        
        # Method 1: Try pdfplumber (best for structured extraction)
        if use_pdfplumber:
            try:
                with pdfplumber.open(BytesIO(pdf_content)) as pdf:
                    full_text = ""
                    sections = {
                        'abstract': '',
                        'introduction': '',
                        'methods': '',
                        'results': '',
                        'discussion': '',
                        'conclusion': '',
                        'references': ''
                    }
                    
                    for page_num, page in enumerate(pdf.pages):
                        page_text = page.extract_text()
                        if page_text:
                            full_text += page_text + "\n"
                            
                            # Try to identify sections based on common headers
                            page_lower = page_text.lower()
                            if 'abstract' in page_lower and not sections['abstract']:
                                sections['abstract'] = page_text[:500]  # First 500 chars
                            elif any(word in page_lower for word in ['introduction', 'background']) and not sections['introduction']:
                                sections['introduction'] = page_text[:500]
                            elif any(word in page_lower for word in ['method', 'material']) and not sections['methods']:
                                sections['methods'] = page_text[:500]
                            elif 'result' in page_lower and not sections['results']:
                                sections['results'] = page_text[:500]
                            elif 'discussion' in page_lower and not sections['discussion']:
                                sections['discussion'] = page_text[:500]
                            elif 'conclusion' in page_lower and not sections['conclusion']:
                                sections['conclusion'] = page_text[:500]
                            elif 'reference' in page_lower and not sections['references']:
                                sections['references'] = page_text[:500]
                    
                    logger.info(f"Successfully extracted {len(full_text)} chars using pdfplumber for {paper_id}")
                    return {
                        'full_text': full_text.strip(),
                        'sections': sections,
                        'extraction_method': 'pdfplumber',
                        'page_count': len(pdf.pages)
                    }
                    
            except Exception as e:
                logger.warning(f"pdfplumber extraction failed for {paper_id}: {str(e)}")
        
        # Method 2: Fallback to PyPDF2
        if use_pypdf2:
            try:
                pdf_reader = PyPDF2.PdfReader(BytesIO(pdf_content))
                full_text = ""
                
                for page_num, page in enumerate(pdf_reader.pages):
                    try:
                        page_text = page.extract_text()
                        if page_text:
                            full_text += page_text + "\n"
                    except Exception as e:
                        logger.warning(f"Failed to extract page {page_num} for {paper_id}: {str(e)}")
                
                # Basic section detection
                sections = {'note': 'Basic text extraction - sections not parsed'}
                full_text_lower = full_text.lower()
                
                # Try to find abstract
                if 'abstract' in full_text_lower:
                    abstract_start = full_text_lower.find('abstract')
                    abstract_end = full_text_lower.find('introduction', abstract_start)
                    if abstract_end == -1:
                        abstract_end = abstract_start + 1000
                    sections['abstract'] = full_text[abstract_start:abstract_end][:500]
                
                logger.info(f"Successfully extracted {len(full_text)} chars using PyPDF2 for {paper_id}")
                return {
                    'full_text': full_text.strip(),
                    'sections': sections,
                    'extraction_method': 'PyPDF2',
                    'page_count': len(pdf_reader.pages)
                }
                
            except Exception as e:
                logger.warning(f"PyPDF2 extraction failed for {paper_id}: {str(e)}")
        
        # Method 3: Basic fallback 
        logger.warning(f"All PDF extraction methods failed for {paper_id}, using basic metadata")
        return {
            'full_text': f"PDF file ({len(pdf_content)} bytes) - text extraction failed",
            'sections': {'error': 'PDF text extraction libraries not available'},
            'extraction_method': 'fallback',
            'pdf_size': len(pdf_content)
        }
            
    except Exception as e:
        logger.error(f"Error processing PDF for {paper_id}: {str(e)}")
        return None


def extract_text_from_tei(tei_xml):
    """Extract clean text from GROBID TEI-XML output"""
    try:
        # For now, we'll do basic text extraction
        # In production, you'd want proper XML parsing with lxml
        import re
        
        # Remove XML tags but preserve text content
        text = re.sub(r'<[^>]+>', ' ', tei_xml)
        
        # Clean up whitespace
        text = re.sub(r'\s+', ' ', text)
        text = text.strip()
        
        # Extract main sections if possible
        sections = {}
        
        # Try to extract abstract
        abstract_match = re.search(r'<abstract[^>]*>(.*?)</abstract>', tei_xml, re.DOTALL | re.IGNORECASE)
        if abstract_match:
            sections['abstract'] = re.sub(r'<[^>]+>', ' ', abstract_match.group(1)).strip()
        
        # Try to extract body text
        body_match = re.search(r'<body[^>]*>(.*?)</body>', tei_xml, re.DOTALL | re.IGNORECASE)
        if body_match:
            sections['body'] = re.sub(r'<[^>]+>', ' ', body_match.group(1)).strip()
        
        return {
            'full_text': text,
            'sections': sections,
            'tei_xml': tei_xml  # Keep raw TEI for advanced processing later
        }
        
    except Exception as e:
        logger.error(f"Error extracting text from TEI: {str(e)}")
        return None


def save_papers_to_s3(papers, source_name):
    """Save paper metadata to S3"""
    if not papers:
        return
    
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    key = f"metadata/{source_name}/{timestamp}.json"
    
    content = {
        'crawled_at': datetime.utcnow().isoformat(),
        'source': source_name,
        'count': len(papers),
        'papers': papers
    }
    
    try:
        s3_client.put_object(
            Bucket=S3_CORPUS_BUCKET,
            Key=key,
            Body=json.dumps(content, indent=2),
            ContentType='application/json',
            Metadata={
                'source': source_name,
                'count': str(len(papers)),
                'crawled_at': timestamp
            }
        )
        logger.info(f"Saved {len(papers)} papers to s3://{S3_CORPUS_BUCKET}/{key}")
        
    except Exception as e:
        logger.error(f"Error saving papers to S3: {str(e)}")


def save_full_text_to_s3(paper_id, paper_metadata, full_text_data, source_name):
    """Save full text content to S3"""
    try:
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        key = f"fulltext/{source_name}/{paper_id}_{timestamp}.json"
        
        content = {
            'paper_id': paper_id,
            'processed_at': datetime.utcnow().isoformat(),
            'source': source_name,
            'metadata': paper_metadata,
            'full_text': full_text_data['full_text'],
            'sections': full_text_data['sections'],
            'word_count': len(full_text_data['full_text'].split()) if full_text_data.get('full_text') else 0
        }
        
        # Also save raw TEI-XML separately for advanced processing
        if full_text_data.get('tei_xml'):
            tei_key = f"tei/{source_name}/{paper_id}_{timestamp}.xml"
            s3_client.put_object(
                Bucket=S3_CORPUS_BUCKET,
                Key=tei_key,
                Body=full_text_data['tei_xml'],
                ContentType='application/xml',
                Metadata={
                    'paper_id': paper_id,
                    'source': source_name,
                    'processed_at': timestamp
                }
            )
        
        # Save structured full text JSON
        s3_client.put_object(
            Bucket=S3_CORPUS_BUCKET,
            Key=key,
            Body=json.dumps(content, indent=2),
            ContentType='application/json',
            Metadata={
                'paper_id': paper_id,
                'source': source_name,
                'word_count': str(content['word_count']),
                'processed_at': timestamp
            }
        )
        
        logger.info(f"Saved full text for {paper_id} to s3://{S3_CORPUS_BUCKET}/{key}")
        return True
        
    except Exception as e:
        logger.error(f"Error saving full text for {paper_id} to S3: {str(e)}")
        return False


def process_papers_for_full_text(papers, source_name, max_pdfs=10):
    """Process papers to download PDFs and extract full text"""
    processed_count = 0
    failed_count = 0
    
    # Get PDF URLs for papers
    pdf_urls = get_pdf_urls(papers)
    logger.info(f"Found {len(pdf_urls)} papers with potential PDF URLs")
    
    # Limit processing to avoid Lambda timeout
    pdf_urls = pdf_urls[:max_pdfs]
    
    for pdf_info in pdf_urls:
        try:
            paper_id = pdf_info['paper_id']
            pdf_urls_list = pdf_info['pdf_urls']
            paper_metadata = pdf_info['paper']
            
            # Download PDF (try multiple URLs)
            pdf_content = download_pdf(pdf_urls_list, paper_id)
            if not pdf_content:
                failed_count += 1
                continue
            
            # Extract text directly from PDF using Python libraries
            full_text_data = extract_text_from_pdf(pdf_content, paper_id)
            if full_text_data:
                # Save the extracted text to S3
                success = save_full_text_to_s3(paper_id, paper_metadata, full_text_data, source_name)
                if success:
                    processed_count += 1
                    logger.info(f"Successfully processed and saved {paper_id} using {full_text_data.get('extraction_method', 'unknown')} method")
                else:
                    failed_count += 1
                    logger.error(f"Failed to save extracted text for {paper_id}")
            else:
                failed_count += 1
                logger.error(f"Failed to extract text from PDF for {paper_id}")
            
            # Small delay to be respectful to servers
            time.sleep(1)
            
        except Exception as e:
            logger.error(f"Error processing PDF for {paper_id}: {str(e)}")
            failed_count += 1
    
    logger.info(f"PDF processing complete: {processed_count} successful, {failed_count} failed")
    return processed_count, failed_count


def handler(event, context):
    """Main Lambda handler for paper crawling and processing"""
    logger.info(f"Received event: {json.dumps(event)}")
    
    results = {
        'crawled_papers': 0,
        'processed_documents': 0,
        'errors': []
    }
    
    # Handle different event types
    try:
        # Manual crawling trigger
        if event.get('action') == 'crawl' or event.get('test'):
            logger.info("Starting manual paper crawling...")
            
            # Crawl from different sources
            sources = event.get('sources', ['pmc', 'europe_pmc'])
            
            if 'pmc' in sources:
                pmc_papers = crawl_pmc_papers(max_papers=event.get('max_papers', 1000))
                if pmc_papers:
                    save_papers_to_s3(pmc_papers, 'pmc')
                    results['crawled_papers'] += len(pmc_papers)
                    
                    # Process PDFs if requested
                    if event.get('process_pdfs', False):
                        max_pdfs = event.get('max_pdfs', 25)  # Higher default for PMC since they're open access
                        processed, failed = process_papers_for_full_text(pmc_papers, 'pmc', max_pdfs)
                        results['processed_documents'] += processed
                        results['errors'].extend([f"Failed to process {failed} PDFs from PMC"] if failed > 0 else [])
            
            # Keep PubMed as backup option
            if 'pubmed' in sources:
                pubmed_papers = crawl_pubmed_papers(max_papers=event.get('max_papers', 1000))
                if pubmed_papers:
                    save_papers_to_s3(pubmed_papers, 'pubmed')
                    results['crawled_papers'] += len(pubmed_papers)
                    
                    # Process PDFs if requested
                    if event.get('process_pdfs', False):
                        max_pdfs = event.get('max_pdfs', 5)
                        processed, failed = process_papers_for_full_text(pubmed_papers, 'pubmed', max_pdfs)
                        results['processed_documents'] += processed
                        results['errors'].extend([f"Failed to process {failed} PDFs from PubMed"] if failed > 0 else [])
            
            if 'europe_pmc' in sources:
                emc_papers = crawl_europe_pmc_papers(max_papers=event.get('max_papers', 1000))
                if emc_papers:
                    save_papers_to_s3(emc_papers, 'europe_pmc')
                    results['crawled_papers'] += len(emc_papers)
                    
                    # Process PDFs if requested
                    if event.get('process_pdfs', False):
                        max_pdfs = event.get('max_pdfs', 5)
                        processed, failed = process_papers_for_full_text(emc_papers, 'europe_pmc', max_pdfs)
                        results['processed_documents'] += processed
                        results['errors'].extend([f"Failed to process {failed} PDFs from Europe PMC"] if failed > 0 else [])
        
        # EventBridge scheduled crawl
        elif event.get('source') == 'aws.events':
            logger.info("Starting scheduled paper crawling...")
            
            # Daily crawl - get papers from last 24 hours
            pmc_papers = crawl_pmc_papers(max_papers=200)
            if pmc_papers:
                save_papers_to_s3(pmc_papers, 'pmc')
                results['crawled_papers'] += len(pmc_papers)
            
            emc_papers = crawl_europe_pmc_papers(max_papers=100)
            if emc_papers:
                save_papers_to_s3(emc_papers, 'europe_pmc')
                results['crawled_papers'] += len(emc_papers)
        
        # S3 events for PDF processing (original GROBID functionality)
        elif 'Records' in event:
            for record in event['Records']:
                if 's3' in record:
                    s3_event = {
                        'bucket': record['s3']['bucket']['name'],
                        'key': record['s3']['object']['key']
                    }
                    # Note: GROBID processing would go here
                    # For now, just log the event
                    logger.info(f"Would process PDF: s3://{s3_event['bucket']}/{s3_event['key']}")
                    results['processed_documents'] += 1
        
        logger.info(f"Crawling completed. Results: {results}")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'success': True,
                'results': results,
                'message': f"Crawled {results['crawled_papers']} papers, processed {results['processed_documents']} documents"
            })
        }
        
    except Exception as e:
        error_msg = f"Lambda execution error: {str(e)}"
        logger.error(error_msg)
        
        return {
            'statusCode': 500,
            'body': json.dumps({
                'success': False,
                'error': error_msg,
                'results': results
            })
        }


# For local testing
if __name__ == "__main__":
    test_event = {
        'action': 'crawl',
        'test': True,
        'sources': ['pmc', 'europe_pmc'],
        'max_papers': 10,
        'process_pdfs': True,
        'max_pdfs': 5
    }
    
    result = handler(test_event, None)
    print(json.dumps(result, indent=2))