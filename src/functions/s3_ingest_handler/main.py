import json
import boto3
import uuid
from datetime import datetime
from urllib.parse import unquote_plus


def handler(event, context):
    """
    S3 event handler that triggers when audio files are uploaded.
    Starts the transcription pipeline via Step Functions.
    """
    
    stepfunctions = boto3.client('stepfunctions')
    
    try:
        for record in event['Records']:
            # Parse S3 event
            bucket = record['s3']['bucket']['name']
            key = unquote_plus(record['s3']['object']['key'])
            
            # Extract position_name from path (e.g., "python_senior/1.m4a" -> "python_senior")
            path_parts = key.split('/')
            if len(path_parts) < 2:
                print(f"Invalid path structure: {key}")
                continue
                
            position_name = path_parts[0]
            filename = path_parts[-1]
            
            # Check if it's an audio file
            if not filename.lower().endswith(('.mp3', '.m4a', '.wav', '.flac')):
                print(f"Skipping non-audio file: {filename}")
                continue
            
            # Generate unique interview ID
            interview_id = str(uuid.uuid4())
            
            # Prepare Step Functions input
            sf_input = {
                "bucket": bucket,
                "key": key,
                "position_name": position_name,
                "interview_id": interview_id,
                "filename": filename,
                "created_at": datetime.utcnow().isoformat()
            }
            
            # Start Step Functions execution
            import os
            state_machine_arn = os.environ.get('STATE_MACHINE_ARN')
            if not state_machine_arn:
                raise ValueError("STATE_MACHINE_ARN environment variable not set")
            
            response = stepfunctions.start_execution(
                stateMachineArn=state_machine_arn,
                name=f"interview-{interview_id}",
                input=json.dumps(sf_input)
            )
            
            print(f"Started Step Functions execution: {response['executionArn']}")
            
    except Exception as e:
        print(f"Error processing S3 event: {str(e)}")
        raise
    
    return {
        'statusCode': 200,
        'body': json.dumps('Successfully processed S3 events')
    }