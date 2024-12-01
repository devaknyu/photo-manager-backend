import boto3
import json
import requests
from requests.auth import HTTPBasicAuth
from datetime import datetime

# OpenSearch endpoint and Basic Authentication credentials
OPENSEARCH_ENDPOINT = "https://search-photo-pmodvyzfu77datuuqiedipn5te.us-west-2.es.amazonaws.com"  # Replace with your OpenSearch endpoint
MASTER_USER = "admin"  # Replace with your OpenSearch master username
MASTER_PASSWORD = "Devak@2002"  # Replace with your OpenSearch master password

# Initialize AWS Rekognition and S3 clients
rekognition_client = boto3.client('rekognition', region_name='us-west-2')
s3_client = boto3.client('s3')

def lambda_handler(event, context):
    try:
        # Check if the request is from Lex or API Gateway
        is_lex_request = "sessionState" in event
        
        if is_lex_request:
            # Extract the query from Lex slots
            slots = event.get("sessionState", {}).get("intent", {}).get("slots", {})
            query = slots.get("Keywords", {}).get("value", {}).get("interpretedValue", None)
            
            if not query:
                # Return a response for missing query
                return {
                    "sessionState": {
                        "dialogAction": {
                            "type": "Close"
                        },
                        "intent": {
                            "name": event["sessionState"]["intent"]["name"],
                            "state": "Failed"
                        }
                    },
                    "messages": [
                        {
                            "contentType": "PlainText",
                            "content": "Sorry, I couldn't find anything. Please try again with different keywords."
                        }
                    ]
                }
            
            # Return a success response for Lex
            return {
                "sessionState": {
                    "dialogAction": {
                        "type": "Close"
                    },
                    "intent": {
                        "name": event["sessionState"]["intent"]["name"],
                        "state": "Fulfilled"
                    }
                },
                "messages": [
                    {
                        "contentType": "PlainText",
                        "content": f"I found photos matching your query '{query}': {search_photos_in_opensearch(query)}"
                    }
                ]
            }
        
        else:
            # Handle API Gateway requests
            query = event.get('queryStringParameters', {}).get('q', None)
            if not query:
                return {
                    'statusCode': 400,
                    'body': json.dumps({
                        'error': 'Query parameter "q" is required'
                    })
                }
            
            # Fetch the search results from OpenSearch
            search_results = search_photos_in_opensearch(query)
            if not search_results:
                return {
                    'statusCode': 404,
                    'body': json.dumps({
                        'message': f"No photos found for the query '{query}'"
                    })
                }
            
            # Return the search results
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': f"Search results for query '{query}'",
                    'results': search_results
                }),
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*',  # Or specify the allowed origin
                    'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
                    'Access-Control-Allow-Headers': 'Content-Type, X-Amz-Date, Authorization, X-Api-Key, X-Amz-Security-Token'
                }
            }
    
    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }

def search_photos_in_opensearch(query):
    """
    Search photos in OpenSearch based on the query.
    """
    # Construct OpenSearch query
    query_string = {
        "query": {
            "match": {
                "labels": query  # Search for the labels that match the query
            }
        },
        "size": 10  # Limit results to 10 per query
    }
    
    # Perform the search in OpenSearch
    response = requests.get(
        f"{OPENSEARCH_ENDPOINT}/photos/_search",
        auth=HTTPBasicAuth(MASTER_USER, MASTER_PASSWORD),
        headers={'Content-Type': 'application/json'},
        data=json.dumps(query_string)
    )

    if response.status_code != 200:
        raise Exception(f"Failed to query OpenSearch: {response.status_code}, {response.text}")

    # Extract search results
    search_results = response.json().get('hits', {}).get('hits', [])
    
    # Get unique object keys (to avoid duplicates)
    unique_results = list(set(hit['_source']['objectKey'] for hit in search_results))

    return unique_results