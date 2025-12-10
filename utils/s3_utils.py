import boto3
import os
import uuid
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

# AWS Configuration
AWS_ACCESS_KEY = os.getenv('AWS_ACCESS_KEY', '')
AWS_SECRET_KEY = os.getenv('AWS_SECRET_KEY', '')
AWS_REGION = os.getenv('AWS_REGION', '')
S3_BUCKET_NAME = os.getenv('S3_BUCKET_NAME', '')
CLOUDFRONT_URL = os.getenv('CLOUDFRONT_URL', '')

# Initialize S3 client
s3_client = boto3.client(
    's3',
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY,
    region_name=AWS_REGION
)

def upload_image_to_s3(file_path, user_id, file_extension='jpg'):
    """
    Upload image to S3 bucket and return the CloudFront URL
    """
    try:
        unique_filename = f"{user_id}-{uuid.uuid4().hex}.{file_extension}"
        s3_key = f"tractor-images/{user_id}/{unique_filename}"
        
        s3_client.upload_file(
            file_path,
            S3_BUCKET_NAME,
            s3_key,
            ExtraArgs={
                'ContentType': f'image/{file_extension}'
            }
        )
        
        cloudfront_url = f"{CLOUDFRONT_URL}/{s3_key}"
        print(f"[S3 SUCCESS] Uploaded: {cloudfront_url}")
        return cloudfront_url
        
    except ClientError as e:
        print(f"[S3 ERROR] Failed to upload {file_path}: {e}")
        return None
    except Exception as e:
        print(f"[S3 ERROR] Unexpected error uploading {file_path}: {e}")
        return None


def upload_multiple_images_to_s3(file_paths, user_id):
    """
    Upload multiple images to S3 and return their URLs
    
    Args:
        file_paths (list): List of local file paths
        user_id (str): User ID for organizing files
    
    Returns:
        list: List of CloudFront URLs for successfully uploaded images
    """
    uploaded_urls = []
    
    for file_path in file_paths:
        # Get file extension
        file_extension = file_path.split('.')[-1].lower()
        if file_extension not in ['jpg', 'jpeg', 'png', 'webp']:
            file_extension = 'jpg'  # Default fallback
        
        url = upload_image_to_s3(file_path, user_id, file_extension)
        if url:
            uploaded_urls.append(url)
    
    return uploaded_urls

def delete_image_from_s3(cloudfront_url):
    """
    Delete image from S3 bucket using CloudFront URL
    
    Args:
        cloudfront_url (str): CloudFront URL of the image to delete
    
    Returns:
        bool: True if deletion successful, False otherwise
    """
    try:
        # Extract S3 key from CloudFront URL
        s3_key = cloudfront_url.replace(f"{CLOUDFRONT_URL}/", "")
        
        # Delete from S3
        s3_client.delete_object(Bucket=S3_BUCKET_NAME, Key=s3_key)
        print(f"[S3 SUCCESS] Deleted: {cloudfront_url}")
        return True
        
    except ClientError as e:
        print(f"[S3 ERROR] Failed to delete {cloudfront_url}: {e}")
        return False
    except Exception as e:
        print(f"[S3 ERROR] Unexpected error deleting {cloudfront_url}: {e}")
        return False
