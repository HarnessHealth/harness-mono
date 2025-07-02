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

# Initialize AWS clients
s3_client = boto3.client('s3')
sqs_client = boto3.client('sqs')


class GROBIDProcessor:
    """Process PDFs using GROBID service"""
    
    def __init__(self, grobid_endpoint: str):
        self.grobid_endpoint = grobid_endpoint.rstrip('/')
        self.session = requests.Session()
    
    def process_pdf(self, pdf_content: bytes) -> Dict:
        """Process PDF through GROBID and return structured data"""
        
        # Full text processing endpoint
        url = f"{self.grobid_endpoint}/api/processFulltextDocument"
        
        files = {
            'input': ('document.pdf', pdf_content, 'application/pdf')
        }
        
        data = {
            'consolidateHeader': '1',
            'consolidateCitations': '1',
            'includeRawCitations': '1',
            'includeRawAffiliations': '1',
            'teiCoordinates': 'ref,figure,formula,s',
        }
        
        try:
            response = self.session.post(
                url,
                files=files,
                data=data,
                timeout=120  # 2 minutes timeout
            )
            response.raise_for_status()
            
            # Parse TEI XML response
            tei_xml = response.text
            structured_data = self.parse_tei_xml(tei_xml)
            
            return {
                'success': True,
                'data': structured_data,
                'tei_xml': tei_xml,
            }
            
        except requests.exceptions.Timeout:
            logger.error("GROBID timeout processing PDF")
            return {'success': False, 'error': 'GROBID timeout'}
        except Exception as e:
            logger.error(f"GROBID processing error: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def parse_tei_xml(self, tei_xml: str) -> Dict:
        """Parse GROBID TEI XML to extract structured content"""
        import xml.etree.ElementTree as ET
        
        # Define TEI namespace
        ns = {'tei': 'http://www.tei-c.org/ns/1.0'}
        
        try:
            root = ET.fromstring(tei_xml)
            
            # Extract metadata
            title = self._extract_text(root, './/tei:titleStmt/tei:title', ns)
            abstract = self._extract_text(root, './/tei:abstract/tei:p', ns)
            
            # Extract authors
            authors = []
            for author in root.findall('.//tei:author', ns):
                name_parts = []
                forename = author.find('.//tei:forename', ns)
                surname = author.find('.//tei:surname', ns)
                if forename is not None:
                    name_parts.append(forename.text)
                if surname is not None:
                    name_parts.append(surname.text)
                if name_parts:
                    authors.append(' '.join(name_parts))
            
            # Extract sections
            sections = []
            for div in root.findall('.//tei:body//tei:div', ns):
                section = {
                    'title': self._extract_text(div, './tei:head', ns),
                    'content': []
                }
                
                for p in div.findall('.//tei:p', ns):
                    text = self._extract_all_text(p)
                    if text:
                        section['content'].append(text)
                
                if section['content']:
                    sections.append(section)
            
            # Extract references
            references = []
            for bibl in root.findall('.//tei:listBibl/tei:biblStruct', ns):
                ref = {
                    'title': self._extract_text(bibl, './/tei:title[@level="a"]', ns),
                    'authors': [],
                    'journal': self._extract_text(bibl, './/tei:title[@level="j"]', ns),
                    'year': self._extract_text(bibl, './/tei:date[@type="published"]', ns),
                }
                
                # Reference authors
                for author in bibl.findall('.//tei:author', ns):
                    name_parts = []
                    forename = author.find('.//tei:forename', ns)
                    surname = author.find('.//tei:surname', ns)
                    if forename is not None:
                        name_parts.append(forename.text)
                    if surname is not None:
                        name_parts.append(surname.text)
                    if name_parts:
                        ref['authors'].append(' '.join(name_parts))
                
                references.append(ref)
            
            return {
                'title': title,
                'abstract': abstract,
                'authors': authors,
                'sections': sections,
                'references': references,
                'num_sections': len(sections),
                'num_references': len(references),
            }
            
        except Exception as e:
            logger.error(f"Error parsing TEI XML: {str(e)}")
            return {}
    
    def _extract_text(self, element, xpath: str, namespaces: Dict) -> str:
        """Extract text from XML element"""
        found = element.find(xpath, namespaces)
        return found.text if found is not None and found.text else ""
    
    def _extract_all_text(self, element) -> str:
        """Extract all text from element and children"""
        texts = []
        if element.text:
            texts.append(element.text)
        for child in element:
            texts.append(self._extract_all_text(child))
            if child.tail:
                texts.append(child.tail)
        return ' '.join(texts).strip()


def download_from_s3(bucket: str, key: str) -> bytes:
    """Download file from S3"""
    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)
        return response['Body'].read()
    except ClientError as e:
        logger.error(f"Error downloading from S3: {str(e)}")
        raise


def upload_to_s3(bucket: str, key: str, content: str, metadata: Dict = None):
    """Upload content to S3"""
    try:
        args = {
            'Bucket': bucket,
            'Key': key,
            'Body': content,
            'ContentType': 'application/json',
        }
        
        if metadata:
            args['Metadata'] = {k: str(v)[:255] for k, v in metadata.items()}
        
        s3_client.put_object(**args)
        logger.info(f"Uploaded to s3://{bucket}/{key}")
        
    except ClientError as e:
        logger.error(f"Error uploading to S3: {str(e)}")
        raise


def process_document(s3_event: Dict) -> Dict:
    """Process a single document from S3 event"""
    bucket = s3_event['bucket']
    key = s3_event['key']
    
    logger.info(f"Processing document: s3://{bucket}/{key}")
    
    # Download PDF
    pdf_content = download_from_s3(bucket, key)
    
    # Generate document ID
    doc_hash = hashlib.md5(pdf_content).hexdigest()
    
    # Process with GROBID
    processor = GROBIDProcessor(GROBID_ENDPOINT)
    result = processor.process_pdf(pdf_content)
    
    if result['success']:
        # Prepare processed data
        processed_data = {
            'source_bucket': bucket,
            'source_key': key,
            'doc_hash': doc_hash,
            'processed_at': datetime.utcnow().isoformat(),
            'grobid_result': result['data'],
        }
        
        # Extract metadata from S3 object
        try:
            obj_metadata = s3_client.head_object(Bucket=bucket, Key=key)
            processed_data['source_metadata'] = obj_metadata.get('Metadata', {})
        except:
            pass
        
        # Save processed data
        output_key = f"processed/grobid/{doc_hash}.json"
        upload_to_s3(
            S3_TRAINING_BUCKET,
            output_key,
            json.dumps(processed_data, indent=2),
            metadata={
                'source_key': key,
                'doc_hash': doc_hash,
                'title': result['data'].get('title', '')[:100],
            }
        )
        
        # Save TEI XML
        tei_key = f"processed/tei/{doc_hash}.xml"
        s3_client.put_object(
            Bucket=S3_TRAINING_BUCKET,
            Key=tei_key,
            Body=result['tei_xml'],
            ContentType='application/xml',
        )
        
        return {
            'success': True,
            'doc_hash': doc_hash,
            'output_key': output_key,
            'tei_key': tei_key,
            'num_sections': result['data'].get('num_sections', 0),
            'num_references': result['data'].get('num_references', 0),
        }
    else:
        return {
            'success': False,
            'error': result.get('error', 'Unknown error'),
            'source_key': key,
        }


def lambda_handler(event, context):
    """Main Lambda handler"""
    logger.info(f"Received event: {json.dumps(event)}")
    
    results = []
    
    # Handle S3 events
    if 'Records' in event:
        for record in event['Records']:
            # S3 event
            if 's3' in record:
                s3_event = {
                    'bucket': record['s3']['bucket']['name'],
                    'key': record['s3']['object']['key']
                }
                result = process_document(s3_event)
                results.append(result)
            
            # SQS event
            elif 'body' in record:
                try:
                    body = json.loads(record['body'])
                    if 'bucket' in body and 'key' in body:
                        result = process_document(body)
                        results.append(result)
                except Exception as e:
                    logger.error(f"Error processing SQS message: {str(e)}")
    
    # Direct invocation
    elif 'bucket' in event and 'key' in event:
        result = process_document(event)
        results.append(result)
    
    # Batch processing
    elif 'documents' in event:
        for doc in event['documents']:
            result = process_document(doc)
            results.append(result)
    
    # Summary
    successful = sum(1 for r in results if r.get('success', False))
    failed = len(results) - successful
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'processed': len(results),
            'successful': successful,
            'failed': failed,
            'results': results,
        })
    }


# For local testing
if __name__ == "__main__":
    test_event = {
        'bucket': 'harness-veterinary-corpus-development',
        'key': 'raw/pubmed/test.pdf'
    }
    
    result = lambda_handler(test_event, None)
    print(json.dumps(result, indent=2))