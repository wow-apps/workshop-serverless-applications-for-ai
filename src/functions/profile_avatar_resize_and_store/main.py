import os
import boto3
from PIL import Image
import tempfile

def handler(event, context):
    # Get bucket and key from event
    record = event['Records'][0]
    src_bucket = record['s3']['bucket']['name']
    src_key = record['s3']['object']['key']
    dst_bucket = os.environ.get('PUBLIC_BUCKET')

    s3 = boto3.client('s3')

    # Download image to temp file
    with tempfile.NamedTemporaryFile() as tmp_file:
        s3.download_file(src_bucket, src_key, tmp_file.name)
        img = Image.open(tmp_file.name)

        # Resize so max dimension is 1000
        max_size = 1000
        img.thumbnail((max_size, max_size), Image.LANCZOS)

        # Center crop to 500x500
        crop_size = 500
        width, height = img.size
        left = (width - crop_size) // 2
        top = (height - crop_size) // 2
        right = left + crop_size
        bottom = top + crop_size
        img = img.crop((left, top, right, bottom))

        # Save processed image to temp file
        with tempfile.NamedTemporaryFile(suffix='.jpg') as out_file:
            img.save(out_file.name, format='JPEG')
            # Upload to public bucket
            dst_key = src_key  # or modify as needed
            s3.upload_file(out_file.name, dst_bucket, dst_key)
