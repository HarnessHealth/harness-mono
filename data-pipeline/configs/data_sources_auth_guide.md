# Veterinary Data Sources Authentication Guide

This guide explains how to configure authentication for various veterinary research databases used by Harness.

## Free Sources (No Authentication Required)

### 1. PubMed/PMC
- **Access**: Completely free
- **API**: E-utilities API
- **Rate Limit**: 3 requests/second without API key, 10/second with key
- **Setup**: Optional - get API key at https://www.ncbi.nlm.nih.gov/account/

### 2. Europe PMC
- **Access**: Completely free
- **API**: RESTful Web Service
- **Rate Limit**: Reasonable use expected
- **Setup**: None required

### 3. DOAJ (Directory of Open Access Journals)
- **Access**: Completely free
- **API**: Public API v3
- **Rate Limit**: No strict limits, be reasonable
- **Setup**: None required

### 4. CrossRef
- **Access**: Free
- **API**: REST API
- **Rate Limit**: 50/second with email
- **Setup**: Include email in requests for better rate limits

### 5. bioRxiv/medRxiv
- **Access**: Free
- **API**: Public API
- **Rate Limit**: Be reasonable
- **Setup**: None required

### 6. arXiv
- **Access**: Free
- **API**: OAI-PMH and API
- **Rate Limit**: 3 requests/second
- **Setup**: None required

## Free with Registration

### 7. IVIS (International Veterinary Information Service)
- **Access**: Free with registration
- **Setup**:
  1. Register at https://www.ivis.org/user/register
  2. Verify email
  3. In Airflow, create HTTP connection:
     ```
     Connection ID: ivis_default
     Connection Type: HTTP
     Host: https://www.ivis.org
     Login: your_email
     Password: your_password
     ```

## Paid/Institutional Access Sources

### VetMed Resource (CAB Direct)
- **Access**: Institutional subscription required
- **Coverage**: 3+ million veterinary records
- **Setup** (if you have access):
  1. Get API credentials from your institution
  2. In Airflow Variables:
     ```
     Key: vetmed_api_key
     Value: your_api_key
     ```
  3. Optional - IP authentication if on institutional network

### Web of Science
- **Access**: Institutional subscription required
- **API**: Web of Science Web Services
- **Setup** (if you have access):
  1. Request API access through your institution
  2. In Airflow, create connection:
     ```
     Connection ID: wos_default
     Connection Type: HTTP
     Host: https://wos-api.clarivate.com
     Extra: {"api_key": "your_api_key"}
     ```

### ScienceDirect (Elsevier)
- **Access**: Mixed (some open access, most requires subscription)
- **API**: Elsevier Developer API
- **Setup**:
  1. Register at https://dev.elsevier.com
  2. Create API key (free tier available with limits)
  3. In Airflow Variables:
     ```
     Key: elsevier_api_key
     Value: your_api_key
     ```
  4. For institutional access, add:
     ```
     Key: elsevier_inst_token
     Value: your_institutional_token
     ```

### Wiley Online Library
- **Access**: Mixed (some open access)
- **API**: Primarily through CrossRef
- **Setup**: Use CrossRef API to access metadata, direct PDF access requires subscription

## Implementation Notes

### Adding New Authenticated Sources

To add a new authenticated source to the DAG:

1. **Store Credentials Securely**:
   - Use Airflow Connections for username/password
   - Use Airflow Variables for API keys
   - Never hardcode credentials in DAG files

2. **Create Query Function**:
   ```python
   def query_authenticated_source(**context):
       from airflow.hooks.base import BaseHook
       from airflow.models import Variable
       
       # Get credentials
       conn = BaseHook.get_connection('source_default')
       api_key = Variable.get('source_api_key', default_var=None)
       
       # Use credentials in API calls
       headers = {'Authorization': f'Bearer {api_key}'}
       # ... rest of implementation
   ```

3. **Handle Authentication Errors**:
   - Gracefully skip if credentials not configured
   - Log clear error messages
   - Don't fail the entire DAG

### Rate Limiting Best Practices

1. **Respect Rate Limits**: Each source has different limits
2. **Use Exponential Backoff**: For retries
3. **Cache Results**: Avoid redundant API calls
4. **Batch Requests**: When APIs support it
5. **Monitor Usage**: Track API calls in logs

### Legal Considerations

1. **Terms of Service**: Always comply with each source's ToS
2. **Purpose**: Ensure usage aligns with research/educational purposes
3. **Attribution**: Properly cite all sources
4. **Storage**: Don't publicly redistribute copyrighted content
5. **Access**: Only use sources you have legitimate access to

## Monitoring and Alerts

Set up Airflow alerts for:
- Authentication failures
- Rate limit exceeded
- Sources returning no results
- Unusual download volumes

## Future Enhancements

1. **Proxy Support**: For institutional access
2. **OAuth Support**: For modern APIs
3. **Token Refresh**: Automatic token renewal
4. **VPN Integration**: For IP-based authentication
5. **Federated Access**: SAML/Shibboleth support