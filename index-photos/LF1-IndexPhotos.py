import boto3
import json
import os
import base64
from datetime import datetime
import requests
import magic  # Python library to identify file type by content

# OpenSearch endpoint and Basic Authentication credentials
OPENSEARCH_ENDPOINT = "https://search-photo-pmodvyzfu77datuuqiedipn5te.us-west-2.es.amazonaws.com"  # Replace with your OpenSearch endpoint
MASTER_USER = "admin"  # Replace with your master username
MASTER_PASSWORD = "Devak@2002"  # Replace with your master password

# Initialize AWS clients
rekognition_client = boto3.client('rekognition', region_name='us-west-2')
s3_client = boto3.client('s3')

def lambda_handler(event, context):
    try:
        # Log the event to see its structure
        print("Received event:", json.dumps(event))

        # Parse S3 event to extract bucket name and object key
        if 'Records' in event and len(event['Records']) > 0:
            bucket_name = event['Records'][0]['s3']['bucket']['name']
            object_key = event['Records'][0]['s3']['object']['key']
            print(f"Object Key: {object_key}")  # Log the exact object key
        else:
            raise ValueError("Invalid S3 event structure")

        # Check the file format using magic (library for file type identification)
        file_extension = get_file_extension_from_s3(bucket_name, object_key)
        print(f"File extension: {file_extension}")

        # Check if the file extension is supported
        supported_extensions = [".jpg", ".jpeg", ".png", ".tiff"]
        if file_extension not in supported_extensions:
            raise ValueError(f"Unsupported file format: {file_extension}")

        # Download the image from S3 to Lambda's /tmp directory
        local_file_path = f"/tmp/{os.path.basename(object_key)}"
        print(f"Downloading file from S3: {bucket_name}/{object_key}")
        s3_client.download_file(bucket_name, object_key, local_file_path)
        print(f"File downloaded to: {local_file_path}")

        # Read the image as bytes
        with open(local_file_path, "rb") as image_file:
            image_bytes = image_file.read()

        # Call Rekognition to detect labels
        print("Calling Rekognition to detect labels...")
        rekognition_response = rekognition_client.detect_labels(
            Image={'Bytes': image_bytes},
            MaxLabels=10
        )

        # Extract labels
        labels = [label['Name'] for label in rekognition_response['Labels']]
        print(f"Detected labels: {labels}")

        # Fetch custom labels from S3 object metadata
        s3_head_response = s3_client.head_object(Bucket=bucket_name, Key=object_key)
        custom_labels = s3_head_response.get('Metadata', {}).get('x-amz-meta-customlabels', "")
        custom_labels_list = custom_labels.split(",") if custom_labels else []
        print(f"Custom labels: {custom_labels_list}")

        # Combine Rekognition and custom labels
        all_labels = list(set(labels + custom_labels_list))  # Remove duplicates
        print(f"All labels: {all_labels}")

        # Prepare document for OpenSearch
        document = {
            "objectKey": object_key,
            "bucket": bucket_name,
            "createdTimestamp": datetime.utcnow().isoformat(),
            "labels": all_labels
        }
        print(f"Document to index: {document}")

        # Index document in OpenSearch
        index_document_in_opensearch(document)

        # Return success response
        return {
            'statusCode': 200,
            'body': json.dumps({
                'bucket': bucket_name,
                'objectKey': object_key,
                'labels': all_labels
            })
        }

    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }

def get_file_extension_from_s3(bucket_name, object_key):
    """
    Helper function to get the file extension from S3 using 'magic' library
    to check the file type based on content.
    """
    file_extension = os.path.splitext(object_key)[-1].lower() if object_key else ""
    if file_extension:  # If the extension is found, return it
        return file_extension
    
    # If the extension is not found, check the file type based on content
    local_file_path = f"/tmp/{os.path.basename(object_key)}"
    s3_client.download_file(bucket_name, object_key, local_file_path)
    
    file_type = magic.from_file(local_file_path, mime=True)  # Get mime type using magic library
    print(f"Detected MIME type: {file_type}")
    
    # Map MIME type to file extension
    mime_to_extension = {
        'image/jpeg': '.jpg',
        'image/png': '.png',
        'image/tiff': '.tiff'
    }
    
    return mime_to_extension.get(file_type, ".jpg")  # Default to .jpg if unknown

def index_document_in_opensearch(document):
    """
    Index a document into OpenSearch using Basic Authentication.
    """
    try:
        index_url = f"{OPENSEARCH_ENDPOINT}/photos/_doc"
        headers = {"Content-Type": "application/json"}
        print(f"Indexing document in OpenSearch: {index_url}")

        # Use Basic Authentication with master username and password
        response = requests.post(
            index_url,
            auth=(MASTER_USER, MASTER_PASSWORD),
            headers=headers,
            json=document
        )

        if response.status_code not in [200, 201]:
            raise Exception(f"Failed to index document. Status: {response.status_code}, Response: {response.text}")
        print(f"Document indexed successfully: {response.json()}")

    except Exception as e:
        print(f"Failed to index document in OpenSearch: {str(e)}")
        raise
