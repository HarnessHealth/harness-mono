"""
Harness - Veterinary Corpus Acquisition DAG
Crawls and processes veterinary papers from multiple sources

Data Sources:
1. PubMed/PMC - Free, no authentication required
2. Europe PMC - Free, no authentication required
3. DOAJ (Directory of Open Access Journals) - Free, no authentication required
4. CrossRef - Free, email recommended for polite use
5. bioRxiv/medRxiv - Free, no authentication required
6. arXiv - Free, no authentication required
7. IVIS (International Veterinary Information Service) - Free but requires registration

Authentication Configuration:
- For IVIS: Create an Airflow Connection named 'ivis_default' with:
  - Connection Type: HTTP
  - Host: https://www.ivis.org
  - Login: your_ivis_username
  - Password: your_ivis_password

- For sources requiring API keys (future):
  - VetMed Resource: Store API key in Airflow Variable 'vetmed_api_key'
  - Web of Science: Store credentials in Connection 'wos_default'
  - ScienceDirect/Elsevier: Store API key in Variable 'elsevier_api_key'

Note: Some sources like VetMed Resource, Web of Science, and full ScienceDirect 
access require institutional subscriptions and are not included in the free tier.
"""
from datetime import datetime, timedelta
from typing import Dict, List

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.amazon.aws.hooks.s3 import S3Hook
from airflow.providers.http.operators.http import SimpleHttpOperator
from airflow.providers.amazon.aws.operators.lambda_function import LambdaInvokeFunctionOperator
from airflow.utils.task_group import TaskGroup

default_args = {
    'owner': 'harness',
    'depends_on_past': False,
    'start_date': datetime(2024, 1, 1),
    'email_on_failure': True,
    'email_on_retry': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=5),
}

dag = DAG(
    'veterinary_corpus_acquisition',
    default_args=default_args,
    description='Acquire and process veterinary papers',
    schedule_interval='@daily',
    catchup=False,
    tags=['corpus', 'acquisition', 'veterinary'],
)


def query_pubmed(**context):
    """Query PubMed for veterinary papers"""
    import requests
    from datetime import datetime, timedelta
    
    # Get yesterday's date for incremental updates
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y/%m/%d')
    
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {
        'db': 'pubmed',
        'term': '(veterinary[MeSH Terms] OR "animal diseases"[MeSH Terms] OR (dog OR canine OR cat OR feline OR equine OR bovine)) AND ("last 1 days"[PDat])',
        'retmax': 1000,
        'retmode': 'json',
        'datetype': 'pdat',
        'mindate': yesterday,
        'maxdate': yesterday,
    }
    
    response = requests.get(base_url, params=params)
    data = response.json()
    
    pmids = data.get('esearchresult', {}).get('idlist', [])
    context['task_instance'].xcom_push(key='pmids', value=pmids)
    
    return f"Found {len(pmids)} new PubMed articles"


def query_europe_pmc(**context):
    """Query Europe PMC for veterinary papers"""
    import requests
    from datetime import datetime, timedelta
    
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    
    base_url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    params = {
        'query': 'SUBJECT:"veterinary" OR SUBJECT:"animal diseases" AND UPDATE_DATE:[{} TO {}]'.format(yesterday, yesterday),
        'format': 'json',
        'pageSize': 1000,
        'cursorMark': '*',
    }
    
    response = requests.get(base_url, params=params)
    data = response.json()
    
    articles = data.get('resultList', {}).get('result', [])
    article_ids = [article.get('id') for article in articles if article.get('id')]
    
    context['task_instance'].xcom_push(key='europe_pmc_ids', value=article_ids)
    
    return f"Found {len(article_ids)} new Europe PMC articles"


def query_doaj(**context):
    """Query Directory of Open Access Journals for veterinary papers"""
    import requests
    from datetime import datetime, timedelta
    
    # DOAJ API is free and doesn't require authentication
    base_url = "https://doaj.org/api/search/articles"
    
    # Search for veterinary articles from the last day
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    today = datetime.now().strftime('%Y-%m-%d')
    
    params = {
        'q': 'subject:veterinary OR keywords:veterinary OR abstract:veterinary',
        'from': yesterday,
        'to': today,
        'pageSize': 100,
        'page': 1,
    }
    
    all_articles = []
    
    try:
        response = requests.get(base_url, params=params)
        data = response.json()
        
        total_results = data.get('total', 0)
        articles = data.get('results', [])
        all_articles.extend(articles)
        
        # Handle pagination if needed
        total_pages = min((total_results // 100) + 1, 10)  # Limit to 10 pages
        
        for page in range(2, total_pages + 1):
            params['page'] = page
            response = requests.get(base_url, params=params)
            data = response.json()
            articles = data.get('results', [])
            all_articles.extend(articles)
    
    except Exception as e:
        print(f"Error querying DOAJ: {str(e)}")
    
    context['task_instance'].xcom_push(key='doaj_articles', value=all_articles)
    
    return f"Found {len(all_articles)} new DOAJ articles"


def query_crossref(**context):
    """Query CrossRef for veterinary papers from multiple publishers"""
    import requests
    from datetime import datetime, timedelta
    
    # CrossRef API is free, email is optional but polite
    base_url = "https://api.crossref.org/works"
    
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    today = datetime.now().strftime('%Y-%m-%d')
    
    # Target veterinary journals from Wiley, Elsevier, and others
    veterinary_journal_issns = [
        "1939-1676",  # Journal of Veterinary Internal Medicine (Wiley)
        "0891-6640",  # Journal of Veterinary Internal Medicine (print)
        "1740-8261",  # Veterinary Radiology & Ultrasound (Wiley)
        "0165-7380",  # Veterinary Research Communications (Springer)
        "1090-0233",  # The Veterinary Journal (Elsevier)
        "0034-5288",  # Research in Veterinary Science (Elsevier)
        "0378-1135",  # Veterinary Microbiology (Elsevier)
        "1532-2661",  # Journal of Veterinary Emergency and Critical Care (Wiley)
    ]
    
    all_articles = []
    
    for issn in veterinary_journal_issns:
        try:
            params = {
                'filter': f'issn:{issn},from-created-date:{yesterday},until-created-date:{today}',
                'rows': 100,
                'mailto': 'harness@example.com',  # Replace with actual email
            }
            
            response = requests.get(base_url, params=params)
            data = response.json()
            
            items = data.get('message', {}).get('items', [])
            all_articles.extend(items)
            
        except Exception as e:
            print(f"Error querying CrossRef for ISSN {issn}: {str(e)}")
    
    context['task_instance'].xcom_push(key='crossref_articles', value=all_articles)
    
    return f"Found {len(all_articles)} new CrossRef articles"


def query_biorxiv(**context):
    """Query bioRxiv and medRxiv for veterinary preprints"""
    import requests
    from datetime import datetime, timedelta
    
    # bioRxiv/medRxiv API
    base_url = "https://api.biorxiv.org/details"
    
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    today = datetime.now().strftime('%Y-%m-%d')
    
    all_preprints = []
    
    # Search both bioRxiv and medRxiv
    for server in ['biorxiv', 'medrxiv']:
        try:
            # API endpoint for new papers
            url = f"{base_url}/{server}/{yesterday}/{today}"
            
            response = requests.get(url)
            data = response.json()
            
            # Filter for veterinary-related preprints
            veterinary_keywords = ['veterinary', 'animal', 'canine', 'feline', 'equine', 'bovine']
            
            for article in data.get('collection', []):
                # Check if any veterinary keywords in title or abstract
                title = article.get('title', '').lower()
                abstract = article.get('abstract', '').lower()
                
                if any(keyword in title or keyword in abstract for keyword in veterinary_keywords):
                    all_preprints.append(article)
        
        except Exception as e:
            print(f"Error querying {server}: {str(e)}")
    
    context['task_instance'].xcom_push(key='biorxiv_preprints', value=all_preprints)
    
    return f"Found {len(all_preprints)} new preprints"


def query_arxiv(**context):
    """Query arXiv for animal science and computational veterinary papers"""
    import requests
    import xml.etree.ElementTree as ET
    from datetime import datetime, timedelta
    
    # arXiv API
    base_url = "http://export.arxiv.org/api/query"
    
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')
    today = datetime.now().strftime('%Y%m%d')
    
    # Search for veterinary and animal science papers
    search_query = '(all:veterinary OR all:"animal health" OR all:"animal disease" OR all:"computational biology" AND all:animal)'
    
    params = {
        'search_query': search_query,
        'start': 0,
        'max_results': 100,
        'sortBy': 'submittedDate',
        'sortOrder': 'descending',
    }
    
    all_papers = []
    
    try:
        response = requests.get(base_url, params=params)
        
        # Parse XML response
        root = ET.fromstring(response.content)
        ns = {'atom': 'http://www.w3.org/2005/Atom'}
        
        for entry in root.findall('atom:entry', ns):
            paper = {
                'id': entry.find('atom:id', ns).text,
                'title': entry.find('atom:title', ns).text.strip(),
                'summary': entry.find('atom:summary', ns).text.strip(),
                'published': entry.find('atom:published', ns).text,
                'authors': [author.find('atom:name', ns).text for author in entry.findall('atom:author', ns)],
                'pdf_url': None,
            }
            
            # Get PDF link
            for link in entry.findall('atom:link', ns):
                if link.get('type') == 'application/pdf':
                    paper['pdf_url'] = link.get('href')
            
            # Filter by date
            pub_date = paper['published'][:10].replace('-', '')
            if int(yesterday) <= int(pub_date) <= int(today):
                all_papers.append(paper)
    
    except Exception as e:
        print(f"Error querying arXiv: {str(e)}")
    
    context['task_instance'].xcom_push(key='arxiv_papers', value=all_papers)
    
    return f"Found {len(all_papers)} new arXiv papers"


def download_papers(**context):
    """Download PDF papers from various sources"""
    import boto3
    import requests
    import hashlib
    from urllib.parse import urlparse
    
    s3_hook = S3Hook(aws_conn_id='aws_default')
    bucket_name = 'harness-veterinary-corpus-development'
    
    # Get data from all previous tasks
    pmids = context['task_instance'].xcom_pull(task_ids='data_sources.pubmed_query', key='pmids') or []
    europe_pmc_ids = context['task_instance'].xcom_pull(task_ids='data_sources.europe_pmc_query', key='europe_pmc_ids') or []
    doaj_articles = context['task_instance'].xcom_pull(task_ids='data_sources.doaj_query', key='doaj_articles') or []
    crossref_articles = context['task_instance'].xcom_pull(task_ids='data_sources.crossref_query', key='crossref_articles') or []
    biorxiv_preprints = context['task_instance'].xcom_pull(task_ids='data_sources.biorxiv_query', key='biorxiv_preprints') or []
    arxiv_papers = context['task_instance'].xcom_pull(task_ids='data_sources.arxiv_query', key='arxiv_papers') or []
    
    downloaded_count = 0
    download_metadata = []
    
    # Download PubMed Central PDFs
    for pmid in pmids[:50]:  # Limit per source
        try:
            pmc_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmid}/pdf/"
            response = requests.get(pmc_url, stream=True)
            
            if response.status_code == 200:
                content_hash = hashlib.md5(response.content).hexdigest()
                key = f"raw/pubmed/{pmid}_{content_hash}.pdf"
                
                s3_hook.load_bytes(
                    response.content,
                    key=key,
                    bucket_name=bucket_name,
                    replace=False
                )
                downloaded_count += 1
                download_metadata.append({'source': 'pubmed', 'id': pmid, 's3_key': key})
        except Exception as e:
            print(f"Error downloading PMID {pmid}: {str(e)}")
    
    # Download DOAJ articles (many are open access)
    for article in doaj_articles[:50]:
        try:
            # DOAJ articles often have fulltext URLs
            for link in article.get('bibjson', {}).get('link', []):
                if link.get('type') == 'fulltext':
                    pdf_url = link.get('url')
                    if pdf_url and pdf_url.endswith('.pdf'):
                        response = requests.get(pdf_url, stream=True, timeout=30)
                        
                        if response.status_code == 200:
                            doi = article.get('bibjson', {}).get('identifier', [{}])[0].get('id', 'unknown')
                            safe_doi = doi.replace('/', '_').replace('.', '_')
                            content_hash = hashlib.md5(response.content).hexdigest()
                            key = f"raw/doaj/{safe_doi}_{content_hash}.pdf"
                            
                            s3_hook.load_bytes(
                                response.content,
                                key=key,
                                bucket_name=bucket_name,
                                replace=False
                            )
                            downloaded_count += 1
                            download_metadata.append({'source': 'doaj', 'doi': doi, 's3_key': key})
                            break
        except Exception as e:
            print(f"Error downloading DOAJ article: {str(e)}")
    
    # Download CrossRef articles (check for open access)
    for article in crossref_articles[:50]:
        try:
            # Check if article has open access link
            for link in article.get('link', []):
                if link.get('content-type') == 'application/pdf':
                    pdf_url = link.get('URL')
                    if pdf_url:
                        response = requests.get(pdf_url, stream=True, timeout=30)
                        
                        if response.status_code == 200:
                            doi = article.get('DOI', 'unknown')
                            safe_doi = doi.replace('/', '_').replace('.', '_')
                            content_hash = hashlib.md5(response.content).hexdigest()
                            key = f"raw/crossref/{safe_doi}_{content_hash}.pdf"
                            
                            s3_hook.load_bytes(
                                response.content,
                                key=key,
                                bucket_name=bucket_name,
                                replace=False
                            )
                            downloaded_count += 1
                            download_metadata.append({'source': 'crossref', 'doi': doi, 's3_key': key})
                            break
        except Exception as e:
            print(f"Error downloading CrossRef article: {str(e)}")
    
    # Download bioRxiv/medRxiv preprints
    for preprint in biorxiv_preprints[:50]:
        try:
            pdf_url = f"https://www.biorxiv.org/content/{preprint.get('doi')}.full.pdf"
            response = requests.get(pdf_url, stream=True, timeout=30)
            
            if response.status_code == 200:
                doi = preprint.get('doi', 'unknown')
                safe_doi = doi.replace('/', '_').replace('.', '_')
                content_hash = hashlib.md5(response.content).hexdigest()
                key = f"raw/biorxiv/{safe_doi}_{content_hash}.pdf"
                
                s3_hook.load_bytes(
                    response.content,
                    key=key,
                    bucket_name=bucket_name,
                    replace=False
                )
                downloaded_count += 1
                download_metadata.append({'source': 'biorxiv', 'doi': doi, 's3_key': key})
        except Exception as e:
            print(f"Error downloading bioRxiv preprint: {str(e)}")
    
    # Download arXiv papers
    for paper in arxiv_papers[:50]:
        try:
            pdf_url = paper.get('pdf_url')
            if pdf_url:
                response = requests.get(pdf_url, stream=True, timeout=30)
                
                if response.status_code == 200:
                    arxiv_id = paper.get('id', '').split('/')[-1]
                    content_hash = hashlib.md5(response.content).hexdigest()
                    key = f"raw/arxiv/{arxiv_id}_{content_hash}.pdf"
                    
                    s3_hook.load_bytes(
                        response.content,
                        key=key,
                        bucket_name=bucket_name,
                        replace=False
                    )
                    downloaded_count += 1
                    download_metadata.append({'source': 'arxiv', 'id': arxiv_id, 's3_key': key})
        except Exception as e:
            print(f"Error downloading arXiv paper: {str(e)}")
    
    # Push download metadata for GROBID processing
    context['task_instance'].xcom_push(key='download_metadata', value=download_metadata)
    
    return f"Downloaded {downloaded_count} papers from all sources"


def process_with_grobid(**context):
    """Trigger Lambda function for GROBID processing"""
    # This will be handled by the Lambda operator
    pass


def chunk_documents(**context):
    """Chunk processed documents for embedding"""
    import boto3
    import json
    from typing import List, Dict
    
    s3_hook = S3Hook(aws_conn_id='aws_default')
    bucket_name = 'harness-training-data-development'
    
    # This would normally process documents from GROBID output
    # For now, we'll create a placeholder
    chunks = []
    
    # Save chunks to S3
    key = f"chunks/{datetime.now().strftime('%Y%m%d')}/batch.jsonl"
    
    return f"Created {len(chunks)} document chunks"


def generate_embeddings(**context):
    """Generate embeddings for document chunks"""
    # This would use sentence-transformers to create embeddings
    # Placeholder for now
    return "Generated embeddings for document chunks"


def update_weaviate_index(**context):
    """Update Weaviate vector database with new documents"""
    # This would update the vector database
    # Placeholder for now
    return "Updated Weaviate index"


def query_ivis(**context):
    """Query International Veterinary Information Service (requires authentication)"""
    # IVIS requires registration but is free
    # This would need to be implemented with proper authentication
    # For now, returning placeholder
    
    # To implement IVIS crawling:
    # 1. Register at https://www.ivis.org and get credentials
    # 2. Store credentials in Airflow Variables or Connections
    # 3. Use selenium or requests with session handling
    # 4. Target conference proceedings and book chapters
    
    print("IVIS crawling requires authentication setup - see implementation notes")
    context['task_instance'].xcom_push(key='ivis_articles', value=[])
    return "IVIS requires authentication - skipped"


# Define task groups
with TaskGroup("data_sources", tooltip="Query data sources", dag=dag) as data_sources:
    pubmed_task = PythonOperator(
        task_id='pubmed_query',
        python_callable=query_pubmed,
        provide_context=True,
    )
    
    europe_pmc_task = PythonOperator(
        task_id='europe_pmc_query',
        python_callable=query_europe_pmc,
        provide_context=True,
    )
    
    doaj_task = PythonOperator(
        task_id='doaj_query',
        python_callable=query_doaj,
        provide_context=True,
    )
    
    crossref_task = PythonOperator(
        task_id='crossref_query',
        python_callable=query_crossref,
        provide_context=True,
    )
    
    biorxiv_task = PythonOperator(
        task_id='biorxiv_query',
        python_callable=query_biorxiv,
        provide_context=True,
    )
    
    arxiv_task = PythonOperator(
        task_id='arxiv_query',
        python_callable=query_arxiv,
        provide_context=True,
    )
    
    ivis_task = PythonOperator(
        task_id='ivis_query',
        python_callable=query_ivis,
        provide_context=True,
    )
    
    [pubmed_task, europe_pmc_task, doaj_task, crossref_task, biorxiv_task, arxiv_task, ivis_task]

download_task = PythonOperator(
    task_id='download_papers',
    python_callable=download_papers,
    provide_context=True,
    dag=dag,
)

grobid_task = LambdaInvokeFunctionOperator(
    task_id='process_with_grobid',
    function_name='harness-grobid-processor-development',
    payload='{{ task_instance.xcom_pull(task_ids="download_papers", key="download_metadata") }}',
    aws_conn_id='aws_default',
    dag=dag,
)

chunk_task = PythonOperator(
    task_id='chunk_documents',
    python_callable=chunk_documents,
    provide_context=True,
    dag=dag,
)

embedding_task = PythonOperator(
    task_id='generate_embeddings',
    python_callable=generate_embeddings,
    provide_context=True,
    dag=dag,
)

index_task = PythonOperator(
    task_id='update_weaviate_index',
    python_callable=update_weaviate_index,
    provide_context=True,
    dag=dag,
)

# Define task dependencies
data_sources >> download_task >> grobid_task >> chunk_task >> embedding_task >> index_task