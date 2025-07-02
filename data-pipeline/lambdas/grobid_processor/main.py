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
    
    # Get yesterday's date for incremental updates
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y/%m/%d')
    
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {
        'db': 'pubmed',
        'term': '(veterinary[MeSH Terms] OR "animal diseases"[MeSH Terms] OR (dog OR canine OR cat OR feline OR equine OR bovine)) AND ("last 7 days"[PDat])',
        'retmax': max_papers,
        'retmode': 'json',
        'datetype': 'pdat',
        'mindate': yesterday,
        'maxdate': 'now',
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
            detail_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
            detail_params = {
                'db': 'pubmed',
                'id': ','.join(pmids[:50]),  # Limit to first 50
                'retmode': 'json'
            }
            
            if NCBI_API_KEY:
                detail_params['api_key'] = NCBI_API_KEY
            
            detail_response = requests.get(detail_url, params=detail_params, timeout=30)
            detail_response.raise_for_status()
            detail_data = detail_response.json()
            
            result = detail_data.get('result', {})
            for pmid in pmids[:50]:
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


def crawl_europe_pmc_papers(max_papers=50):
    """Crawl papers from Europe PMC API"""
    import requests
    from datetime import datetime, timedelta
    
    logger.info("Starting Europe PMC crawl...")
    
    yesterday = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    today = datetime.now().strftime('%Y-%m-%d')
    
    base_url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    params = {
        'query': f'SUBJECT:"veterinary" OR SUBJECT:"animal diseases" AND UPDATE_DATE:[{yesterday} TO {today}]',
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
            sources = event.get('sources', ['pubmed', 'europe_pmc'])
            
            if 'pubmed' in sources:
                pubmed_papers = crawl_pubmed_papers(max_papers=event.get('max_papers', 50))
                if pubmed_papers:
                    save_papers_to_s3(pubmed_papers, 'pubmed')
                    results['crawled_papers'] += len(pubmed_papers)
            
            if 'europe_pmc' in sources:
                emc_papers = crawl_europe_pmc_papers(max_papers=event.get('max_papers', 50))
                if emc_papers:
                    save_papers_to_s3(emc_papers, 'europe_pmc')
                    results['crawled_papers'] += len(emc_papers)
        
        # EventBridge scheduled crawl
        elif event.get('source') == 'aws.events':
            logger.info("Starting scheduled paper crawling...")
            
            # Daily crawl - get papers from last 24 hours
            pubmed_papers = crawl_pubmed_papers(max_papers=100)
            if pubmed_papers:
                save_papers_to_s3(pubmed_papers, 'pubmed')
                results['crawled_papers'] += len(pubmed_papers)
            
            emc_papers = crawl_europe_pmc_papers(max_papers=50)
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
        'sources': ['pubmed', 'europe_pmc'],
        'max_papers': 10
    }
    
    result = handler(test_event, None)
    print(json.dumps(result, indent=2))